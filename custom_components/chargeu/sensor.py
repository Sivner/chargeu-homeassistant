"""Sensor platform for CHARGEU."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ChargeuCoordinator
from .entity import ChargeuEntity


@dataclass(frozen=True, kw_only=True)
class ChargeuSensorDescription(SensorEntityDescription):
    """Describes a CHARGEU sensor."""

    value_fn: Callable[[dict[str, Any]], Any]


def _power(data: dict[str, Any]) -> float | None:
    current = data.get("current")
    voltage = data.get("voltage")
    if current is None or voltage is None:
        return None
    return round(current * voltage, 1)


SENSORS: tuple[ChargeuSensorDescription, ...] = (
    ChargeuSensorDescription(
        key="state",
        translation_key="state",
        icon="mdi:ev-station",
        value_fn=lambda d: d.get("state"),
    ),
    ChargeuSensorDescription(
        key="current",
        translation_key="current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        value_fn=lambda d: d.get("current"),
    ),
    ChargeuSensorDescription(
        key="max_current",
        translation_key="max_current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        value_fn=lambda d: d.get("max_current"),
    ),
    ChargeuSensorDescription(
        key="voltage",
        translation_key="voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        value_fn=lambda d: d.get("voltage"),
    ),
    ChargeuSensorDescription(
        key="power",
        translation_key="power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        value_fn=_power,
    ),
    ChargeuSensorDescription(
        key="session_energy",
        translation_key="session_energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda d: d.get("session_energy"),
    ),
    ChargeuSensorDescription(
        key="session_duration",
        translation_key="session_duration",
        icon="mdi:timer-outline",
        value_fn=lambda d: d.get("session_duration"),
    ),
    ChargeuSensorDescription(
        key="timer_countdown",
        translation_key="timer_countdown",
        icon="mdi:timer-lock-outline",
        value_fn=lambda d: d.get("timer_countdown"),
    ),
    ChargeuSensorDescription(
        key="timer_target",
        translation_key="timer_target",
        icon="mdi:timer-cog-outline",
        device_class=SensorDeviceClass.ENUM,
        options=["unlock", "lock", "none"],
        value_fn=lambda d: d.get("timer_target"),
    ),
    ChargeuSensorDescription(
        key="meter",
        translation_key="meter",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda d: d.get("meter"),
    ),
    ChargeuSensorDescription(
        key="total_energy",
        translation_key="total_energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda d: d.get("total_energy"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: ChargeuCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        ChargeuSensor(coordinator, entry.entry_id, description)
        for description in SENSORS
    )


class ChargeuSensor(ChargeuEntity, SensorEntity):
    """A single parsed value from the charger."""

    entity_description: ChargeuSensorDescription

    def __init__(
        self,
        coordinator: ChargeuCoordinator,
        entry_id: str,
        description: ChargeuSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data or {})
