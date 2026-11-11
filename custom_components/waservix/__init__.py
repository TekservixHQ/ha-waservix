"""WAservix for Home Assistant: send WhatsApp messages from your own number and react to incoming ones."""

from __future__ import annotations

import json
import logging
import secrets

import voluptuous as vol
from aiohttp import web

from homeassistant.components import persistent_notification, webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import NoURLAvailableError
from homeassistant.helpers.typing import ConfigType

from .api import WAservixApi, WAservixError, verify_signature
from .const import (
    CONF_WEBHOOK_ID,
    CONF_WEBHOOK_SECRET,
    DOMAIN,
    EVENT_MESSAGE_RECEIVED,
    EVENT_OTHER,
    SERVICE_SEND_MESSAGE,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.NOTIFY]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
RECEIVED_EVENTS = {"messages.received", "messages-personal.received", "messages-group.received"}

SEND_SCHEMA = vol.Schema(
    {
        vol.Required("to"): cv.string,
        vol.Optional("message"): cv.string,
        vol.Optional("image_url"): cv.string,
        vol.Optional("document_url"): cv.string,
        vol.Optional("file_name"): cv.string,
    }
)

type WAservixConfigEntry = ConfigEntry[WAservixApi]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the waservix.send_message action."""

    async def send_message(call: ServiceCall) -> ServiceResponse:
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries:
            raise HomeAssistantError("WAservix is not set up")
        fields = {
            "text": call.data.get("message"),
            "imageUrl": call.data.get("image_url"),
            "documentUrl": call.data.get("document_url"),
            "fileName": call.data.get("file_name"),
        }
        if not any(fields[k] for k in ("text", "imageUrl", "documentUrl")):
            raise HomeAssistantError("WAservix: give a message, image_url or document_url")
        try:
            result = await entries[0].runtime_data.send_message(call.data["to"], fields)
        except (WAservixError, ValueError) as err:
            raise HomeAssistantError(f"WAservix: {err}") from err
        return result if isinstance(result, dict) else {"result": result}

    hass.services.async_register(
        DOMAIN, SERVICE_SEND_MESSAGE, send_message, schema=SEND_SCHEMA, supports_response=SupportsResponse.OPTIONAL
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: WAservixConfigEntry) -> bool:
    """Set up WAservix from a config entry."""
    entry.runtime_data = WAservixApi(async_get_clientsession(hass), entry.data[CONF_API_KEY])

    webhook_id = entry.data.get(CONF_WEBHOOK_ID)
    first_time = not webhook_id
    if first_time:
        webhook_id = secrets.token_hex(16)
        hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_WEBHOOK_ID: webhook_id})
    webhook.async_register(hass, DOMAIN, "WAservix", webhook_id, _handle_webhook, allowed_methods=["POST"])

    if first_time:
        # The number's webhook is set in the WAservix dashboard, so show the URL to paste there.
        try:
            url = webhook.async_generate_url(hass, webhook_id, allow_internal=False)
        except NoURLAvailableError:
            url = None
        persistent_notification.async_create(
            hass,
            (
                f"To receive WhatsApp messages in Home Assistant, paste this URL as the webhook of your number "
                f"in the WAservix dashboard (Devices → your number → Webhook):\n\n`{url}`"
                if url
                else "Home Assistant has no external URL, so incoming WhatsApp events are off. "
                "Set one (Settings → System → Network) and reload the integration to get the webhook URL. "
                "Sending messages works without it."
            ),
            title="WAservix webhook",
            notification_id=f"{DOMAIN}_{entry.entry_id}_webhook",
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WAservixConfigEntry) -> bool:
    """Unload a config entry."""
    if entry.data.get(CONF_WEBHOOK_ID):
        webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _handle_webhook(hass: HomeAssistant, webhook_id: str, request: web.Request) -> web.Response:
    """Check the secret and fire waservix_message_received / waservix_event."""
    entry = next(
        (e for e in hass.config_entries.async_entries(DOMAIN) if e.data.get(CONF_WEBHOOK_ID) == webhook_id), None
    )
    if entry is None:
        return web.Response(status=404)
    secret = entry.data.get(CONF_WEBHOOK_SECRET)
    if secret and not verify_signature(request.headers.get("X-Webhook-Signature"), secret):
        return web.Response(status=401, text="bad signature")
    try:
        event = json.loads(await request.read())
    except ValueError:
        return web.Response(status=400)
    name = event.get("event", "")
    data = event.get("data") or {}
    if name in RECEIVED_EVENTS:
        msg = data.get("messages") or {}
        key = msg.get("key") or {}
        hass.bus.async_fire(
            EVENT_MESSAGE_RECEIVED,
            {
                "event": name,
                "from": key.get("cleanedSenderPn") or key.get("remoteJid"),
                "message": msg.get("messageBody"),
                "group": name == "messages-group.received" or str(key.get("remoteJid", "")).endswith("@g.us"),
                "raw": data,
            },
        )
    else:
        hass.bus.async_fire(EVENT_OTHER, {"event": name, "data": data})
    return web.Response(text="ok")
