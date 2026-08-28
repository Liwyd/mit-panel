import time
import json
import requests
from datetime import datetime, timedelta, timezone

from backend.schema._input import ClientInput, ClientUpdateInput


class APIService:
    _username: str | None = None
    _cached_token: str | None = None
    _cached_url: str | None = None
    _token_time: float | None = None
    _token_ttl = 300

    def __init__(
        self, url: str, username: str, password: str, inbounds: dict | str | None = None
    ):
        self.url = url if url.endswith("/") else url + "/"
        self.username = username
        self.password = password
        self.token: str | None = None
        self.session = requests.Session()
        self.headers: dict[str, str] | None = None

        if isinstance(inbounds, str):
            try:
                self.inbounds = json.loads(inbounds)
            except (json.JSONDecodeError, TypeError):
                self.inbounds = {}
        else:
            self.inbounds = inbounds or {}

    async def _login(self):
        now = time.time()

        if (
            APIService._username == self.username
            and
            APIService._cached_token
            and APIService._cached_url == self.url
            and APIService._token_time
            and now - APIService._token_time < APIService._token_ttl
        ):
            self.token = APIService._cached_token
            self.headers = {"Authorization": f"Bearer {self.token}"}
            return

        token = (
            requests.post(
                f"{self.url}api/admin/token",
                data={
                    "username": self.username,
                    "password": self.password,
                },
            )
            .json()
            .get("access_token")
        )

        APIService._cached_token = token
        APIService._cached_url = self.url
        APIService._token_time = now
        self.token = token
        self.headers = {"Authorization": f"Bearer {self.token}"}

    async def test_connection(self) -> bool:
        try:
            token = (
                requests.post(
                    f"{self.url}api/admin/token",
                    data={
                        "username": self.username,
                        "password": self.password,
                    },
                )
                .json()
                .get("access_token")
            )
            return True if token else False
        except Exception:
            return False

    async def get_users(self):
        await self._login()
        url = f"{self.url}api/users"
        response = self.session.get(url, headers=self.headers).json()
        return response

    async def get_user(self, username: str) -> dict | bool:
        token = (
            requests.post(
                f"{self.url}api/admin/token",
                data={
                    "username": self.username,
                    "password": self.password,
                },
            )
            .json()
            .get("access_token")
        )

        user = requests.get(
            f"{self.url}api/user/{username}",
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        return user

    async def get_inbounds(self) -> dict:
        token = (
            requests.post(
                f"{self.url}api/admin/token",
                data={
                    "username": self.username,
                    "password": self.password,
                },
            )
            .json()
            .get("access_token")
        )
        url = f"{self.url}api/inbounds"

        response = self.session.get(url, headers={"Authorization": f"Bearer {token}"})

        # Transform to list of tags for each protocol
        inbounds = response.json()
        for protocol in inbounds:
            inbounds[protocol] = [item["tag"] for item in inbounds[protocol]]

        return inbounds

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
        )
        return response.status_code

    async def reset_user_traffic(self, username: str) -> int:
        await self._login()
        response = self.session.post(
            f"{self.url}api/user/{username}/reset",
            headers=self.headers,
        )
        return response.status_code

    async def delete_user(self, username: str) -> int:
        await self._login()
        response = self.session.delete(
            f"{self.url}api/user/{username}",
            headers=self.headers,
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
        )
        return response.status_code

    async def get_system_stats(self) -> dict:
        """Marzban's own /api/system snapshot: user counts, lifetime bandwidth
        and the CPU/RAM of the host Marzban itself runs on."""
        await self._login()
        response = self.session.get(f"{self.url}api/system", headers=self.headers)
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
        )
        if response.status_code != 200:
            return []
        return response.json().get("usages", [])

    async def count_online_users(self, window_seconds: int = 180) -> int:
        """Marzban exposes no online counter, so the user list is scanned for
        an online_at inside the window. Callers should cache this."""
        await self._login()
        response = self.session.get(f"{self.url}api/users", headers=self.headers)
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
        response = self.session.get(f"{self.url}api/admins", headers=self.headers)
        if response.status_code != 200:
            return []
        return response.json()
