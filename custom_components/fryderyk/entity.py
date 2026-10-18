"""Base entity for Fryderyk."""

from __future__ import annotations

from homeassistant.const import CONF_USERNAME
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FryderykCoordinator


class FryderykEntity(CoordinatorEntity[FryderykCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: FryderykCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Fryderyk {entry.data[CONF_USERNAME]}",
            manufacturer="Fryderyk e-dziennik",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=coordinator.api.base,
        )
