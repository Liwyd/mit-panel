import time
import json
import requests

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
