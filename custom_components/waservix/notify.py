"""WAservix notify entity: sends a WhatsApp message to the default recipient."""

from __future__ import annotations

from homeassistant.components.notify import NotifyEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import WAservixConfigEntry
from .api import WAservixError
from .const import CONF_RECIPIENT, DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: WAservixConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([WAservixNotifyEntity(entry)])


class WAservixNotifyEntity(NotifyEntity):
    """notify.send_message target that messages the default number or group on WhatsApp."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, entry: WAservixConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_notify"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="WAservix",
            manufacturer="Tekservix",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://tekservix.com/waservix/app/",
        )

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        recipient = self._entry.data.get(CONF_RECIPIENT)
        if not recipient:
            raise HomeAssistantError("WAservix: add a default recipient in the integration, or use the waservix.send_message action")
        text = f"*{title}*\n{message}" if title else message
        try:
            await self._entry.runtime_data.send_message(recipient, {"text": text})
        except WAservixError as err:
            raise HomeAssistantError(f"WAservix: {err}") from err
