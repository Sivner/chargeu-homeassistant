"""Number platform for CHARGEU: the maximum charging current."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfElectricCurrent
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import ChargeuApiError
from .const import DOMAIN, MAX_AMPS, MIN_AMPS
from .coordinator import ChargeuCoordinator
from .entity import ChargeuEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: ChargeuCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ChargeuMaxCurrent(coordinator, entry.entry_id)])


class ChargeuMaxCurrent(ChargeuEntity, NumberEntity):
    """Maximum charging current, 6..32 A in 1 A steps."""

    _attr_translation_key = "max_current"
    _attr_device_class = NumberDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_native_min_value = float(MIN_AMPS)
    _attr_native_max_value = float(MAX_AMPS)
    _attr_native_step = 1.0
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: ChargeuCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "max_current_control")

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data or {}
        # "/" is polled most often, so prefer it; /setup is the fallback.
        value = data.get("max_current")
        if value is None:
            value = data.get("setup_max_current")
        return value

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.coordinator.api.async_set_current(int(value))
        except ChargeuApiError as err:
            raise HomeAssistantError(f"Failed to set charging current: {err}") from err
        await self.coordinator.async_refresh_after_command()
