"""Config flow for WAservix: asks for the number's API key, webhook secret and default recipient."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import WAservixApi, WAservixError
from .const import CONF_RECIPIENT, CONF_WEBHOOK_SECRET, DOMAIN

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
        vol.Optional(CONF_RECIPIENT, default=""): str,
        vol.Optional(CONF_WEBHOOK_SECRET, default=""): str,
    }
)


class WAservixConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up WAservix from the UI."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            api = WAservixApi(async_get_clientsession(self.hass), user_input[CONF_API_KEY])
            try:
                status = await api.get_status()
            except WAservixError as err:
                errors["base"] = "invalid_auth" if err.status in (401, 403) else "cannot_connect"
            else:
                await self.async_set_unique_id(user_input[CONF_API_KEY][-12:])
                self._abort_if_unique_id_configured()
                connected = isinstance(status, dict) and status.get("status") == "connected"
                return self.async_create_entry(
                    title="WAservix" if connected else "WAservix (not connected yet)",
                    data={
                        CONF_API_KEY: user_input[CONF_API_KEY],
                        CONF_RECIPIENT: (user_input.get(CONF_RECIPIENT) or "").strip() or None,
                        CONF_WEBHOOK_SECRET: user_input.get(CONF_WEBHOOK_SECRET) or "",
                    },
                )
        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors)
