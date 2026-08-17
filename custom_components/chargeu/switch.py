"""Switch platform for CHARGEU."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import ChargeuApi, ChargeuApiError
from .const import DOMAIN
from .coordinator import ChargeuCoordinator
from .entity import ChargeuEntity


@dataclass(frozen=True, kw_only=True)
class ChargeuSwitchDescription(SwitchEntityDescription):
    """Describes a CHARGEU switch."""

    value_fn: Callable[[dict[str, Any]], bool | None]
    set_fn: Callable[[ChargeuApi, bool], Awaitable[None]]


SWITCHES: tuple[ChargeuSwitchDescription, ...] = (
    ChargeuSwitchDescription(
        key="available",
        translation_key="available",
        icon="mdi:ev-station",
        # Prefer the live "/" page (fast) and fall back to the /pass form state.
        value_fn=lambda d: (
            (not d["locked"]) if d.get("locked") is not None else d.get("available")
        ),
        set_fn=lambda api, on: api.async_set_available(on),
    ),
    ChargeuSwitchDescription(
        key="single_session",
        translation_key="single_session",
        icon="mdi:numeric-1-circle-outline",
        value_fn=lambda d: d.get("single_session"),
        set_fn=lambda api, on: api.async_set_single_session(on),
    ),
    ChargeuSwitchDescription(
        key="ground_check",
        translation_key="ground_check",
        icon="mdi:power-plug",
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("ground_on"),
        set_fn=lambda api, on: api.async_set_ground(on),
    ),
    ChargeuSwitchDescription(
        key="led",
        translation_key="led",
        icon="mdi:lightbulb",
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("led_on"),
        set_fn=lambda api, on: api.async_set_led(on),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: ChargeuCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SwitchEntity] = [
        ChargeuSwitch(coordinator, entry.entry_id, description)
        for description in SWITCHES
    ]
    entities.append(ChargeuTimerSwitch(coordinator, entry.entry_id))
    async_add_entities(entities)


class ChargeuSwitch(ChargeuEntity, SwitchEntity):
    """A toggle backed by one of the charger's POST forms."""

    entity_description: ChargeuSwitchDescription

    def __init__(
        self,
        coordinator: ChargeuCoordinator,
        entry_id: str,
        description: ChargeuSwitchDescription,
    ) -> None:
        super().__init__(coordinator, entry_id, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data or {})

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set(False)

    async def _async_set(self, state: bool) -> None:
        try:
            await self.entity_description.set_fn(self.coordinator.api, state)
        except ChargeuApiError as err:
            raise HomeAssistantError(
                f"Failed to set {self.entity_description.key}: {err}"
            ) from err
        # The charger applies changes instantly; refresh now instead of waiting
        # for the next poll so the UI does not visibly bounce back.
        await self.coordinator.async_refresh_after_command()


class ChargeuTimerSwitch(ChargeuEntity, SwitchEntity):
    """Enable or disable the built-in timer.

    Unlike the other switches this one submits the whole timer form (the device
    accepts it only atomically), so it goes through the coordinator rather than
    a single API call. Toggling the timer resets the current session counters,
    and enabling it will start charging once the unlock time is reached.
    """

    _attr_translation_key = "timer_enabled"
    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator: ChargeuCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "timer_enabled")

    @property
    def is_on(self) -> bool | None:
        return self._value("timer_enabled")

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_apply_timer(enabled=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_apply_timer(enabled=False)
