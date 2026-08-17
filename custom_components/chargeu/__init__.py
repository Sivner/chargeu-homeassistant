"""The CHARGEU EV charger integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ChargeuApi, ChargeuApiError
from .const import (
    ATTR_AMPS,
    ATTR_BEGIN,
    ATTR_ENABLED,
    ATTR_END,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_AMPS,
    MIN_AMPS,
    SERVICE_RESET_METER,
    SERVICE_SET_TIMER,
)
from .coordinator import ChargeuCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
]

_TIME_RE = r"^\d{1,2}:\d{2}$"

SET_TIMER_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_BEGIN): cv.matches_regex(_TIME_RE),
        vol.Required(ATTR_END): cv.matches_regex(_TIME_RE),
        vol.Required(ATTR_AMPS): vol.All(vol.Coerce(int), vol.Range(min=MIN_AMPS, max=MAX_AMPS)),
        vol.Required(ATTR_ENABLED): cv.boolean,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up CHARGEU from a config entry."""
    session = async_get_clientsession(hass)
    api = ChargeuApi(entry.data[CONF_HOST], session)

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = ChargeuCoordinator(hass, api, scan_interval)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN, None)
            for service in (SERVICE_SET_TIMER, SERVICE_RESET_METER):
                hass.services.async_remove(DOMAIN, service)
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _coordinators(hass: HomeAssistant) -> list[ChargeuCoordinator]:
    return list(hass.data.get(DOMAIN, {}).values())


def _async_register_services(hass: HomeAssistant) -> None:
    """Register domain-level services once."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_TIMER):
        return

    async def _set_timer(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass):
            try:
                await coordinator.api.async_set_timer(
                    begin=call.data[ATTR_BEGIN],
                    end=call.data[ATTR_END],
                    amps=call.data[ATTR_AMPS],
                    enabled=call.data[ATTR_ENABLED],
                )
            except ChargeuApiError as err:
                raise HomeAssistantError(f"Failed to set timer: {err}") from err
            await coordinator.async_refresh_after_command()

    async def _reset_meter(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass):
            try:
                await coordinator.api.async_reset_meter()
            except ChargeuApiError as err:
                raise HomeAssistantError(f"Failed to reset meter: {err}") from err
            await coordinator.async_refresh_after_command()

    hass.services.async_register(DOMAIN, SERVICE_SET_TIMER, _set_timer, SET_TIMER_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_RESET_METER, _reset_meter)
