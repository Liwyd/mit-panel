import json
import httpx

from backend.schema._input import ClientInput, ClientUpdateInput


class APIService:
    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.token = token

        self.client = httpx.AsyncClient(
            base_url=self.url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def test_connection(self) -> bool:
        try:
            response = await self.client.get("/panel/api/server/status")
            if response.status_code != 200:
                return False

            data = response.json()

            if not data.get("success"):
                return False

            return True

        except Exception:
            return False

    async def get_clients(self):
        response = await self.client.get(
            "/panel/api/clients/list"
        )

        response.raise_for_status()

        data = response.json()

        return data.get("obj", [])

    async def get_all_online_clients(self):
        response = await self.client.post(
            "/panel/api/clients/lastOnline"
        )

        response.raise_for_status()

        data = response.json()

        return data.get("obj", [])

    async def add_client(
        self,
        inbound_id: list[int],
        inbound_flow: str,
        client: ClientInput,
    ):

        payload = {
            "client": {
                "id": client.id,
                "email": client.email,
                "enable": client.enable,
                "expiryTime": int(client.expiry_time),
                "totalGB": int(client.total),
                "flow": inbound_flow if inbound_flow else client.flow,
                "subId": client.sub_id,
            },
            "inboundIds": inbound_id,
        }

        response = await self.client.post(
            "/panel/api/clients/add",
            json=payload,
        )
        response.raise_for_status()

        return response.json()

    async def get_client_by_email(self, email: str):
        response = await self.client.get(
            f"/panel/api/clients/get/{email}"
        )

        response.raise_for_status()

        data = response.json()

        return data.get("obj")

    async def update_client(
        self,
        uuid: str,
        inbound_flow: str,
        client: ClientUpdateInput
    ):

        payload = {
            "email": client.email,
            "enable": client.enable,
            "expiryTime": int(client.expiry_time),
            "totalGB": int(client.total),
            "flow": inbound_flow if inbound_flow else client.flow,
            "subId": client.sub_id,
        }

        response = await self.client.post(
            f"/panel/api/clients/update/{client.email}",
            json=payload,
        )


        response.raise_for_status()

        return response.json()

    async def set_client_enable(self, client: dict, enable: bool) -> bool:
        """Turn one client on or off, keeping its own expiry, volume and sub id.

        `client` is the client as get_clients returned it. update_client would
        go through ClientUpdateInput, which refuses an unlimited (0) volume.
        """
        payload = {
            "email": client.get("email"),
            "enable": bool(enable),
            "expiryTime": int(client.get("expiryTime") or 0),
            "totalGB": int(client.get("totalGB") or 0),
            "flow": client.get("flow") or "",
            "subId": client.get("subId") or "",
        }
        response = await self.client.post(
            f"/panel/api/clients/update/{client.get('email')}",
            json=payload,
        )
        response.raise_for_status()
        try:
            data = response.json()
        except ValueError:
            return True
        return bool(data.get("success", True)) if isinstance(data, dict) else True

    async def reset_client_usage(
        self,
        email: str
    ):

        response = await self.client.post(
            f"/panel/api/clients/resetTraffic/{email}"
        )

        response.raise_for_status()

        return response.json()

    async def delete_client(
        self,
        email: str
    ):

        response = await self.client.post(
            f"/panel/api/clients/del/{email}"
        )

        response.raise_for_status()

        return response.json()

    async def close(self):
        await self.client.aclose()