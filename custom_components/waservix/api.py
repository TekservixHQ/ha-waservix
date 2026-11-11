"""Small async client for the WAservix API (no Home Assistant imports, so it can be tested alone)."""

from __future__ import annotations

import hmac
import json
from typing import Any

import aiohttp

from .const import DEFAULT_BASE_URL


class WAservixError(Exception):
    """The API answered with an error (status 0 when it was not reached; 503 = number reconnecting)."""

    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


class WAservixApi:
    """Calls the WAservix API with the API key of the customer's number."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str, base_url: str = DEFAULT_BASE_URL) -> None:
        if not api_key:
            raise ValueError("WAservix: an API key is required (Devices in the WAservix dashboard)")
        self._session = session
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    async def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        """Call any documented endpoint and return its `data`."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "User-Agent": "waservix-homeassistant/1.0.0",
        }
        try:
            async with self._session.request(
                method, self._base_url + path, json=body, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                text = await resp.text()
                status = resp.status
        except (aiohttp.ClientError, TimeoutError) as err:
            raise WAservixError(f"request failed ({err})") from err
        try:
            data = json.loads(text) if text else None
        except ValueError:
            data = None
        if status >= 400 or (isinstance(data, dict) and data.get("success") is False):
            message = data.get("message") if isinstance(data, dict) and isinstance(data.get("message"), str) else f"HTTP {status}"
            raise WAservixError(message, status)
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        return data

    async def send_message(self, to: str, fields: dict[str, Any]) -> Any:
        """Send any message type to a number or a group JID (...@g.us)."""
        if not to:
            raise ValueError('send_message: "to" is required (international number or group JID)')
        body = {k: v for k, v in fields.items() if v not in (None, "")}
        body["to"] = to
        return await self.request("POST", "/send-message", body)

    async def get_status(self) -> Any:
        """Connection status of the number (also used to check the key)."""
        return await self.request("GET", "/status")


def verify_signature(signature: str | None, secret: str) -> bool:
    """X-Webhook-Signature must equal the number's webhook secret (constant-time compare)."""
    if not signature or not secret:
        return False
    return hmac.compare_digest(signature, secret)
