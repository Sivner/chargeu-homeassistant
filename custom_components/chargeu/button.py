"""Button platform for CHARGEU: clock synchronisation."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import ChargeuApiError
from .const import DOMAIN
from .coordinator import ChargeuCoordinator
from .entity import ChargeuEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: ChargeuCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ChargeuSyncClockButton(coordinator, entry.entry_id)])


class ChargeuSyncClockButton(ChargeuEntity, ButtonEntity):
    """Push Home Assistant's local time to the charger.

    The station has no NTP; its clock drifts and the built-in timer depends on
    it, so this is worth running periodically.
    """

    _attr_translation_key = "sync_clock"
    _attr_icon = "mdi:clock-check-outline"

    def __init__(self, coordinator: ChargeuCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "sync_clock")

    async def async_press(self) -> None:
        try:
            await self.coordinator.api.async_sync_clock(dt_util.now())
        except ChargeuApiError as err:
            raise HomeAssistantError(f"Failed to sync clock: {err}") from err
        await self.coordinator.async_refresh_after_command()
