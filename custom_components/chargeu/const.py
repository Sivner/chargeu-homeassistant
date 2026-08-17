"""Constants for the CHARGEU integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "chargeu"

CONF_SCAN_INTERVAL: Final = "scan_interval"

# The charger's own web UI reloads every 4 s; 15 s is a good balance between
# responsiveness and not hammering a 2015-era embedded web server.
DEFAULT_SCAN_INTERVAL: Final = 15
MIN_SCAN_INTERVAL: Final = 5
MAX_SCAN_INTERVAL: Final = 300

# /setup and /pass change rarely, so they are polled on a slower cycle and
# refreshed immediately after any command.
SLOW_INTERVAL: Final = 300

DEFAULT_HOST: Final = "192.168.4.1"

MIN_AMPS: Final = 6
MAX_AMPS: Final = 32

SERVICE_SET_TIMER: Final = "set_timer"
SERVICE_RESET_METER: Final = "reset_energy_meter"

ATTR_BEGIN: Final = "begin"
ATTR_END: Final = "end"
ATTR_AMPS: Final = "amps"
ATTR_ENABLED: Final = "enabled"
