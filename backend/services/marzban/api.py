import time
import json
import asyncio
import requests
from datetime import datetime, timedelta, timezone

from backend.schema._input import ClientInput, ClientUpdateInput

# Every call below is synchronous code running inside an async handler, so an
# unbounded wait would freeze the whole event loop (bot and dashboard alike)
# for as long as the panel stays unreachable.
REQUEST_TIMEOUT = 10


class MarzbanAPIError(Exception):
    """A panel call failed in a way the caller must not silently absorb."""


class APIService:
    # Per-(url, username) token cache.  Keys are "(url, username)" strings so
    # that different panels or different admin accounts never overwrite each
    # other's cached token.
    _token_cache: dict[str, tuple[str, float]] = {}
    _token_ttl = 300
    # Lock serialises concurrent logins for the *same* (url, username) to
    # avoid flooding the panel with parallel token requests.
    _login_locks: dict[str, asyncio.Lock] = {}

    def __init__(
        self, url: str, username: str, password: str, inbounds: dict | str | None = None
    ):
        self.url = url if url.endswith("/") else url + "/"
        self.username = username
        self.password = password
        self.token: str | None = None
        self.session = requests.Session()
        self.headers: dict[str, str] | None = None
        self._cache_key = f"{self.url}|{self.username}"

        if isinstance(inbounds, str):
            try:
                self.inbounds = json.loads(inbounds)
            except (json.JSONDecodeError, TypeError):
                self.inbounds = {}
        else:
            self.inbounds = inbounds or {}

    def _get_lock(self) -> asyncio.Lock:
        if self._cache_key not in APIService._login_locks:
            APIService._login_locks[self._cache_key] = asyncio.Lock()
        return APIService._login_locks[self._cache_key]

    async def _login(self):
        now = time.time()
        cached = APIService._token_cache.get(self._cache_key)

        if cached and now - cached[1] < APIService._token_ttl:
            self.token = cached[0]
            self.headers = {"Authorization": f"Bearer {self.token}"}
            return

        lock = self._get_lock()
        async with lock:
            # Double-check after acquiring the lock
            cached = APIService._token_cache.get(self._cache_key)
            if cached and now - cached[1] < APIService._token_ttl:
                self.token = cached[0]
                self.headers = {"Authorization": f"Bearer {self.token}"}
                return

            token = (
                requests.post(
                    f"{self.url}api/admin/token",
                    data={
                        "username": self.username,
                        "password": self.password,
                    },
                    timeout=REQUEST_TIMEOUT,
                )
                .json()
                .get("access_token")
            )

            # Only a usable token is worth caching: caching a failed login
            # would pin every later attempt to that failure for the TTL.
            if token:
                APIService._token_cache[self._cache_key] = (token, time.time())
            self.token = token
            self.headers = {"Authorization": f"Bearer {token}"}

    async def test_connection(self) -> bool:
        try:
            await self._login()
            return bool(self.token)
        except Exception:
            return False

    async def get_users(self):
        await self._login()
        url = f"{self.url}api/users"
        response = self.session.get(url, headers=self.headers, timeout=REQUEST_TIMEOUT)
        return response.json()

    async def get_users_page(self, offset: int = 0, limit: int = 500) -> tuple[list[dict], int | None]:
        """One page of /api/users, returning (users, total).

        `total` is Marzban's own count for the query and is what makes an
        incomplete read detectable: callers must not act on a partial list,
        or a short page would look like every user having been deleted.
        """
        await self._login()
        response = self.session.get(
            f"{self.url}api/users",
            headers=self.headers,
            params={"offset": offset, "limit": limit},
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code != 200:
            raise MarzbanAPIError(
                f"Marzban returned status {response.status_code} for /api/users"
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise MarzbanAPIError("Unexpected /api/users payload")
        users = payload.get("users")
        if not isinstance(users, list):
            raise MarzbanAPIError("/api/users payload has no user list")
        total = payload.get("total")
        return users, int(total) if isinstance(total, int) else None

    async def get_all_users_paginated(self, page_size: int = 500) -> list[dict]:
        """Every user on the panel. Aborts rather than returning a partial read."""
        collected: list[dict] = []
        offset = 0
        total: int | None = None
        seen_first: str | None = None

        while True:
            page, page_total = await self.get_users_page(offset, page_size)
            if page_total is not None:
                total = page_total
            if not page:
                break

            first = str(page[0].get("username"))
            # A server that ignores `offset` hands back the same first page
            # forever; without this the loop would never end.
            if offset > 0 and first == seen_first:
                raise MarzbanAPIError("Marzban ignored the pagination offset")
            seen_first = first

            collected.extend(page)
            if total is not None:
                if len(collected) >= total:
                    break
            elif len(page) < page_size:
                break
            offset += len(page)
            if len(collected) > 500_000:
                raise MarzbanAPIError("Refusing to page past 500k users")

        if total is not None and len(collected) < total:
            raise MarzbanAPIError(
                f"Incomplete user read: got {len(collected)} of {total}"
            )
        return collected

    async def get_user(self, username: str) -> dict | bool:
        await self._login()

        user = requests.get(
            f"{self.url}api/user/{username}",
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=REQUEST_TIMEOUT,
        ).json()
        return user

    async def get_inbounds(self, retries: int = 3) -> dict:
        """Protocol -> tags, exactly what Marzban accepts as a user's inbounds.

        Retried because an empty result here is not "no inbounds exist", it is
        a failed read: callers persist this as the panel's inbound set, and a
        silently empty set produces configs that connect to nothing.
        """
        await self._login()
        url = f"{self.url}api/inbounds"
        last_error: Exception | None = None

        for attempt in range(max(1, retries)):
            try:
                response = self.session.get(
                    url,
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=REQUEST_TIMEOUT,
                )
                if response.status_code != 200:
                    raise MarzbanAPIError(
                        f"Marzban returned status {response.status_code} for /api/inbounds"
                    )
                payload = response.json()
                if not isinstance(payload, dict):
                    raise MarzbanAPIError("Unexpected /api/inbounds payload")

                # Transform to list of tags for each protocol
                inbounds: dict = {}
                for protocol, items in payload.items():
                    if not isinstance(items, list):
                        raise MarzbanAPIError(
                            f"Unexpected inbound list for protocol {protocol}"
                        )
                    inbounds[protocol] = [item["tag"] for item in items]

                if not inbounds or not any(inbounds.values()):
                    raise MarzbanAPIError("Panel reported no inbounds at all")
                return inbounds
            except Exception as exc:
                last_error = exc
                if attempt + 1 < retries:
                    await asyncio.sleep(0.5 * (attempt + 1))

        raise MarzbanAPIError(f"Could not read inbounds from panel: {last_error}")

    async def create_user(self, user: ClientInput) -> int:
        await self._login()
        proxies = {k: {} for k in self.inbounds}
        expire_ts = user.expiry_time // 1000 if user.expiry_time else 0
        data_limit = int(user.total) if user.total is not None else 0

        data = {
            "username": user.email,
            "status": "active",
            "expire": expire_ts,
            "data_limit": data_limit,
            "data_limit_reset_strategy": "no_reset",
            "inbounds": self.inbounds,
            "proxies": proxies,
            "note": "",
            "on_hold_expire_duration": 0,
            "on_hold_timeout": None,
        }

        response = self.session.post(
            f"{self.url}api/user",
            headers=self.headers,
            json=data,
            timeout=REQUEST_TIMEOUT,
        )
        return response.status_code

    async def update_user(self, username: str, user_data: ClientUpdateInput) -> int:
        await self._login()
        expire_ts = user_data.expiry_time // 1000 if user_data.expiry_time else 0
        data_limit = int(user_data.total) if user_data.total is not None else 0

        update_data = {
            "status": "active" if user_data.enable else "disabled",
            "data_limit": data_limit,
            "expire": expire_ts,
            "data_limit_reset_strategy": "no_reset",
            "proxies": {},
            "inbounds": {},
            "note": "",
        }

        response = self.session.put(
            f"{self.url}api/user/{username}",
            headers=self.headers,
            json=update_data,
            timeout=REQUEST_TIMEOUT,
        )
        return response.status_code

    async def reset_user_traffic(self, username: str) -> int:
        await self._login()
        response = self.session.post(
            f"{self.url}api/user/{username}/reset",
            headers=self.headers,
            timeout=REQUEST_TIMEOUT,
        )
        return response.status_code

    async def delete_user(self, username: str) -> int:
        await self._login()
        response = self.session.delete(
            f"{self.url}api/user/{username}",
            headers=self.headers,
            timeout=REQUEST_TIMEOUT,
        )
        return response.status_code

    async def update_admin_password(self, admin_username: str, new_password: str) -> int:
        """Change another Marzban admin's password. Requires this APIService to be
        logged in as a sudo admin (self.username/self.password) — Marzban rejects
        this call from a non-sudo admin, even one modifying its own account.

        Marzban's AdminModify body requires `is_sudo`, so a password-only payload
        is rejected with 422. The admin's current record is read first and its
        flags echoed back unchanged: guessing `is_sudo` here would silently
        promote or demote the account being edited.
        """
        await self._login()

        current = next(
            (a for a in await self.get_admins() if a.get("username") == admin_username), None
        )
        if current is None:
            return 404

        payload = {"password": new_password, "is_sudo": bool(current.get("is_sudo"))}
        for field in ("telegram_id", "discord_webhook"):
            if current.get(field) is not None:
                payload[field] = current[field]

        response = self.session.put(
            f"{self.url}api/admin/{admin_username}",
            headers=self.headers,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        return response.status_code

    async def get_system_stats(self) -> dict:
        """Marzban's own /api/system snapshot: user counts, lifetime bandwidth
        and the CPU/RAM of the host Marzban itself runs on."""
        await self._login()
        response = self.session.get(
            f"{self.url}api/system", headers=self.headers, timeout=REQUEST_TIMEOUT
        )
        if response.status_code != 200:
            return {}
        return response.json()

    async def get_nodes_usage(self, start: str, end: str) -> list[dict]:
        """Per-node traffic for a window. Marzban wants naive ISO timestamps."""
        await self._login()
        response = self.session.get(
            f"{self.url}api/nodes/usage",
            headers=self.headers,
            params={"start": start, "end": end},
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code != 200:
            return []
        return response.json().get("usages", [])

    async def count_online_users(self, window_seconds: int = 180) -> int:
        """Marzban exposes no online counter, so the user list is scanned for
        an online_at inside the window. Callers should cache this."""
        await self._login()
        response = self.session.get(
            f"{self.url}api/users", headers=self.headers, timeout=REQUEST_TIMEOUT
        )
        if response.status_code != 200:
            return 0

        users = response.json().get("users", [])
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
        online = 0
        for user in users:
            seen = user.get("online_at")
            if not seen:
                continue
            try:
                stamp = datetime.fromisoformat(str(seen).replace("Z", "+00:00"))
            except ValueError:
                continue
            # Marzban reports naive UTC; attach the timezone before comparing.
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            if stamp >= cutoff:
                online += 1
        return online

    async def get_admins(self) -> list[dict]:
        """List every admin as Marzban itself has them recorded (username,
        telegram_id, is_sudo, ...). Requires sudo credentials."""
        await self._login()
        response = self.session.get(
            f"{self.url}api/admins", headers=self.headers, timeout=REQUEST_TIMEOUT
        )
        if response.status_code != 200:
            return []
        return response.json()

    async def create_admin(
        self, username: str, password: str, telegram_id: int | None = None
    ) -> tuple[int, str]:
        """Create a non-sudo admin in Marzban. Requires sudo credentials.

        Returns (status_code, detail) so the caller can report Marzban's own
        reason -- most often a duplicate username -- instead of a bare number.
        """
        await self._login()
        payload = {"username": username, "password": password, "is_sudo": False}
        if telegram_id:
            payload["telegram_id"] = telegram_id

        response = self.session.post(
            f"{self.url}api/admin",
            headers=self.headers,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        detail = ""
        if response.status_code != 200:
            try:
                detail = str(response.json().get("detail", response.text))
            except Exception:
                detail = response.text
        return response.status_code, detail
