"""Thin async client for the CHARGEU web interface.

The charger exposes no API -- only HTML pages and POST forms. Commands are sent
exactly the way the built-in web UI sends them, as
``application/x-www-form-urlencoded`` bodies. aiohttp encodes a dict the same
way a browser does (``$`` -> ``%24``, space -> ``+``), which is what the
firmware expects.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import aiohttp

_LOGGER = logging.getLogger(__name__)


class ChargeuApiError(Exception):
    """Raised when the charger cannot be reached or answers unexpectedly."""


class ChargeuApi:
    """Talks to a single CHARGEU charging station."""

    def __init__(
        self,
        host: str,
        session: aiohttp.ClientSession,
        timeout: int = 10,
    ) -> None:
        self._host = host.strip().rstrip("/")
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        # The embedded web server is single-threaded and easily overwhelmed;
        # serialise every request to it.
        self._lock = asyncio.Lock()

    @property
    def host(self) -> str:
        return self._host

    def _url(self, path: str) -> str:
        return f"http://{self._host}{path}"

    async def _request(
        self,
        method: str,
        path: str,
        data: dict[str, str] | None = None,
    ) -> str:
        async with self._lock:
            try:
                async with self._session.request(
                    method, self._url(path), data=data, timeout=self._timeout
                ) as response:
                    response.raise_for_status()
                    # The firmware does not always declare a charset; decode
                    # leniently rather than raising on stray bytes.
                    raw = await response.read()
                    return raw.decode("utf-8", errors="replace")
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                raise ChargeuApiError(
                    f"{method} {path} failed for {self._host}: {err}"
                ) from err

    # ---- reads ----------------------------------------------------------- #

    async def async_get_main(self) -> str:
        return await self._request("GET", "/")

    async def async_get_setup(self) -> str:
        return await self._request("GET", "/setup")

    async def async_get_pass(self) -> str:
        return await self._request("GET", "/pass")

    # ---- commands: /setup ------------------------------------------------- #

    async def async_set_current(self, amps: int) -> None:
        """Set the maximum charging current (6..32 A)."""
        await self._request("POST", "/setup", {"change": f"$AMPS {int(amps)}"})

    async def async_set_ground(self, enabled: bool) -> None:
        await self._request("POST", "/setup", {"change": f"$GROUND {1 if enabled else 0}"})

    async def async_set_led(self, enabled: bool) -> None:
        await self._request("POST", "/setup", {"change": f"$LED {1 if enabled else 0}"})

    async def async_set_language(self, lang: str) -> None:
        """Set UI language: ``E``, ``U`` or ``R``."""
        await self._request("POST", "/setup", {"change": f"$LANG {lang}"})

    async def async_reset_meter(self) -> None:
        """Reset the lifetime energy meter. Destructive: data is not recoverable."""
        await self._request("POST", "/setup", {"emreset": "1"})

    # ---- commands: /pass -------------------------------------------------- #

    async def async_set_available(self, available: bool) -> None:
        """Unlock (make available) or lock the station.

        Note the inverted argument: ``$AVAIL 0`` means "make available".
        Unlocking with a car plugged in starts charging immediately.
        """
        await self._request("POST", "/pass", {"change1": f"$AVAIL {0 if available else 1}"})

    async def async_set_single_session(self, enabled: bool) -> None:
        """Enable/disable the one-shot charging session.

        Enabling this also unlocks the station and starts charging a plugged-in car.
        """
        await self._request("POST", "/pass", {"change1": f"$TEMPS {1 if enabled else 0}"})

    async def async_sync_clock(self, now: datetime) -> None:
        await self._request(
            "POST", "/pass", {"newtime": now.strftime("%Y-%m-%dT%H:%M:%S")}
        )

    async def async_set_timer(
        self, begin: str, end: str, amps: int, enabled: bool
    ) -> None:
        """Configure the built-in timer.

        ``begin``/``end`` are ``HH:MM``. Changing the timer resets the current
        session counters (the lifetime meter is unaffected).
        """
        await self._request(
            "POST",
            "/pass",
            {
                "timerb": begin,
                "timerbc": "1",
                "timere": end,
                "timerec": "1",
                "timeramps": str(int(amps)),
                "timer": "1" if enabled else "0",
            },
        )
