"""Config flow, actions, notify entity and webhook events."""

import json
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from custom_components.waservix.api import WAservixApi, WAservixError, verify_signature
from custom_components.waservix.const import (
    CONF_RECIPIENT,
    CONF_WEBHOOK_ID,
    CONF_WEBHOOK_SECRET,
    DOMAIN,
    EVENT_MESSAGE_RECEIVED,
)

API = "custom_components.waservix.api.WAservixApi"


async def test_config_flow_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    with patch(f"{API}.get_status", AsyncMock(return_value={"status": "connected"})):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_KEY: "wpk_test_123456789", CONF_RECIPIENT: " +1555 ", CONF_WEBHOOK_SECRET: "s"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "WAservix"
    assert result["data"][CONF_RECIPIENT] == "+1555"


async def test_config_flow_invalid_key(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    with patch(f"{API}.get_status", AsyncMock(side_effect=WAservixError("Unauthorized", 401))):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: "bad"})
    assert result["errors"] == {"base": "invalid_auth"}


async def _setup(hass: HomeAssistant, **data) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_API_KEY: "wpk_test", CONF_RECIPIENT: "+1999", **data})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_send_message_action(hass: HomeAssistant) -> None:
    await _setup(hass)
    with patch(f"{API}.send_message", AsyncMock(return_value={"msgId": 58213})) as send:
        response = await hass.services.async_call(
            DOMAIN, "send_message", {"to": "+1555", "message": "Door opened", "image_url": "https://x/cam.jpg"},
            blocking=True, return_response=True,
        )
    send.assert_awaited_once_with(
        "+1555", {"text": "Door opened", "imageUrl": "https://x/cam.jpg", "documentUrl": None, "fileName": None}
    )
    assert response == {"msgId": 58213}


async def test_notify_entity(hass: HomeAssistant) -> None:
    await _setup(hass)
    entity_id = next(s.entity_id for s in hass.states.async_all("notify"))
    with patch(f"{API}.send_message", AsyncMock(return_value={"msgId": 1})) as send:
        await hass.services.async_call(
            "notify", "send_message", {"entity_id": entity_id, "title": "Alarm", "message": "Motion"}, blocking=True
        )
    send.assert_awaited_once_with("+1999", {"text": "*Alarm*\nMotion"})


async def test_webhook_fires_event(hass: HomeAssistant, hass_client_no_auth) -> None:
    await _setup(hass, **{CONF_WEBHOOK_ID: "wh1", CONF_WEBHOOK_SECRET: "abc"})
    events = async_capture_events(hass, EVENT_MESSAGE_RECEIVED)
    client = await hass_client_no_auth()
    body = json.dumps({
        "event": "messages-personal.received",
        "data": {"messages": {"key": {"cleanedSenderPn": "15551234567"}, "messageBody": "STATUS"}},
    })
    assert (await client.post("/api/webhook/wh1", data=body, headers={"X-Webhook-Signature": "nope"})).status == 401
    assert (await client.post("/api/webhook/wh1", data=body, headers={"X-Webhook-Signature": "abc"})).status == 200
    await hass.async_block_till_done()
    assert len(events) == 1
    assert events[0].data["from"] == "15551234567"
    assert events[0].data["message"] == "STATUS"
    assert events[0].data["group"] is False


async def test_api_client(hass: HomeAssistant, aioclient_mock) -> None:
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    aioclient_mock.post("https://example.test/api/send-message", json={"success": True, "data": {"msgId": 7}})
    aioclient_mock.get("https://example.test/api/status", status=503, json={"success": False, "message": "Device reconnecting"})
    api = WAservixApi(async_get_clientsession(hass), "wpk_test", "https://example.test/api")
    assert await api.send_message("+1", {"text": "hi", "imageUrl": None}) == {"msgId": 7}
    assert aioclient_mock.mock_calls[0][2] == {"text": "hi", "to": "+1"}
    try:
        await api.get_status()
        raise AssertionError("expected an error")
    except WAservixError as err:
        assert err.status == 503
        assert str(err) == "Device reconnecting"


def test_verify_signature() -> None:
    assert verify_signature("abc", "abc")
    assert not verify_signature("abd", "abc")
    assert not verify_signature(None, "abc")
