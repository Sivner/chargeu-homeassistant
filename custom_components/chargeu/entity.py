"""Base entity for CHARGEU."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ChargeuCoordinator


class ChargeuEntity(CoordinatorEntity[ChargeuCoordinator]):
    """Common device info and availability handling."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ChargeuCoordinator, entry_id: str, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            manufacturer="CHARGEU",
            model=(coordinator.data or {}).get("model") or "CHARGEU",
            name="CHARGEU",
            configuration_url=f"http://{coordinator.api.host}/",
        )

    @property
    def available(self) -> bool:
        return super().available and bool(self.coordinator.data)

    def _value(self, key: str):
        return (self.coordinator.data or {}).get(key)
