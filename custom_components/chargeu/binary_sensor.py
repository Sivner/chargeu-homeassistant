"""Binary sensor platform for CHARGEU."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ChargeuCoordinator
from .entity import ChargeuEntity


@dataclass(frozen=True, kw_only=True)
class ChargeuBinaryDescription(BinarySensorEntityDescription):
    """Describes a CHARGEU binary sensor."""

    value_fn: Callable[[dict[str, Any]], bool | None]


BINARY_SENSORS: tuple[ChargeuBinaryDescription, ...] = (
    ChargeuBinaryDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        # Derived from measured current, so it works regardless of UI language.
        value_fn=lambda d: d.get("charging"),
    ),
    ChargeuBinaryDescription(
        key="locked",
        translation_key="locked",
        icon="mdi:lock",
        # Deliberately NOT BinarySensorDeviceClass.LOCK: that class inverts the
        # meaning (on = unlocked), which would be confusing here.
        value_fn=lambda d: d.get("locked"),
    ),
    ChargeuBinaryDescription(
        key="ground_check",
        translation_key="ground_check",
        icon="mdi:power-plug",
        value_fn=lambda d: d.get("ground_on"),
    ),
    ChargeuBinaryDescription(
        key="rcd",
        translation_key="rcd",
        icon="mdi:shield-flash",
        value_fn=lambda d: d.get("rcd_on"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: ChargeuCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        ChargeuBinarySensor(coordinator, entry.entry_id, description)
        for description in BINARY_SENSORS
    )


class ChargeuBinarySensor(ChargeuEntity, BinarySensorEntity):
    """A boolean state derived from the charger's pages."""

    entity_description: ChargeuBinaryDescription

    def __init__(
        self,
        coordinator: ChargeuCoordinator,
        entry_id: str,
        description: ChargeuBinaryDescription,
    ) -> None:
        super().__init__(coordinator, entry_id, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data or {})
