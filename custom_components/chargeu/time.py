"""Time platform for CHARGEU: the built-in timer's unlock/lock times."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from homeassistant.components.time import TimeEntity, TimeEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ChargeuCoordinator
from .entity import ChargeuEntity


@dataclass(frozen=True, kw_only=True)
class ChargeuTimeDescription(TimeEntityDescription):
    """Describes a CHARGEU timer time field."""

    field: str  # which async_apply_timer keyword this entity controls


TIMES: tuple[ChargeuTimeDescription, ...] = (
    ChargeuTimeDescription(
        key="timer_begin",
        translation_key="timer_begin",
        icon="mdi:timer-play-outline",
        field="begin",
    ),
    ChargeuTimeDescription(
        key="timer_end",
        translation_key="timer_end",
        icon="mdi:timer-stop-outline",
        field="end",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: ChargeuCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        ChargeuTime(coordinator, entry.entry_id, description) for description in TIMES
    )


class ChargeuTime(ChargeuEntity, TimeEntity):
    """One edge of the timer window (unlock or lock time)."""

    entity_description: ChargeuTimeDescription

    def __init__(
        self,
        coordinator: ChargeuCoordinator,
        entry_id: str,
        description: ChargeuTimeDescription,
    ) -> None:
        super().__init__(coordinator, entry_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> time | None:
        raw = self._value(self.entity_description.key)  # "HH:MM"
        if not raw:
            return None
        try:
            hour, minute = (int(part) for part in raw.split(":")[:2])
            return time(hour, minute)
        except ValueError:
            return None

    async def async_set_value(self, value: time) -> None:
        # Changing the timer resets the current session counters; that is a
        # device behaviour, not something we can avoid here.
        await self.coordinator.async_apply_timer(
            **{self.entity_description.field: value.strftime("%H:%M")}
        )
