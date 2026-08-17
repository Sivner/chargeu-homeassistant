"""Update coordinator for CHARGEU.

The live page ``/`` is polled on every cycle. ``/setup`` and ``/pass`` change
rarely and are polled on a slow cycle -- but they are refreshed immediately
after any command so the UI reflects reality without waiting.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from time import monotonic
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ChargeuApi, ChargeuApiError
from .const import DOMAIN, SLOW_INTERVAL
from .parser import parse_main, parse_pass, parse_setup

_LOGGER = logging.getLogger(__name__)


class ChargeuCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches and parses the charger's pages."""

    def __init__(self, hass: HomeAssistant, api: ChargeuApi, scan_interval: int) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.api = api
        self._slow_cache: dict[str, Any] = {}
        self._slow_due_at: float = 0.0

    async def async_refresh_after_command(self) -> None:
        """Force a full refresh (including the slow pages) right after a command."""
        self._slow_due_at = 0.0
        await self.async_request_refresh()

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            main_html = await self.api.async_get_main()
        except ChargeuApiError as err:
            raise UpdateFailed(str(err)) from err

        data = parse_main(main_html)

        if monotonic() >= self._slow_due_at:
            try:
                setup_html = await self.api.async_get_setup()
                pass_html = await self.api.async_get_pass()
            except ChargeuApiError as err:
                # A failure on the secondary pages must not invalidate the live
                # telemetry we already have; keep serving the previous values.
                _LOGGER.debug("Slow-cycle refresh failed, keeping cache: %s", err)
            else:
                self._slow_cache = {**parse_setup(setup_html), **parse_pass(pass_html)}
                self._slow_due_at = monotonic() + SLOW_INTERVAL

        # Live values from "/" win over the cached ones, but only where the live
        # page actually produced a value (e.g. ground state is on both pages).
        merged = dict(self._slow_cache)
        for key, value in data.items():
            if value is not None or key not in merged:
                merged[key] = value
        return merged
