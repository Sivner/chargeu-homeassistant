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
    async_add_entities(
        [
            ChargeuMaxCurrent(coordinator, entry.entry_id),
            ChargeuTimerAmps(coordinator, entry.entry_id),
        ]
    )


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
        # Value we just wrote, shown until the device's pages report it back.
        self._optimistic: float | None = None

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data or {}
        # "/" is polled most often, so prefer it; /setup is the fallback.
        value = data.get("max_current")
        if value is None:
            value = data.get("setup_max_current")

        # The command POSTs to /setup, which reports the new maximum instantly,
        # but the "/" page mirrors it a poll or two later. Since "/" wins the
        # merge, the freshly-set value would otherwise be masked by the stale
        # "/" reading and the slider would bounce back for up to one poll. Show
        # the value we set until the reported value catches up to it.
        if self._optimistic is not None:
            if value == self._optimistic:
                self._optimistic = None
            else:
                return self._optimistic
        return value

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.coordinator.api.async_set_current(int(value))
        except ChargeuApiError as err:
            raise HomeAssistantError(f"Failed to set charging current: {err}") from err
        self._optimistic = value
        self.async_write_ha_state()
        await self.coordinator.async_refresh_after_command()


class ChargeuTimerAmps(ChargeuEntity, NumberEntity):
    """Charging current used inside the timer window, 6..32 A."""

    _attr_translation_key = "timer_amps"
    _attr_icon = "mdi:timer-cog-outline"
    _attr_device_class = NumberDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_native_min_value = float(MIN_AMPS)
    _attr_native_max_value = float(MAX_AMPS)
    _attr_native_step = 1.0
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: ChargeuCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "timer_amps")

    @property
    def native_value(self) -> float | None:
        return self._value("timer_amps")

    async def async_set_native_value(self, value: float) -> None:
        # Applying the timer resets the current session counters (device quirk).
        await self.coordinator.async_apply_timer(amps=int(value))
