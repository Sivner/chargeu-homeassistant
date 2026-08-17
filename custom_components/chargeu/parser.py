"""Pure-python parsing of the CHARGEU web interface.

This module deliberately has NO Home Assistant imports so it can be unit-tested
standalone against captured HTML fixtures.

Design notes (derived from probing a live CHARGEU base 32A):

* The device has no API. Every page is server-rendered HTML in the shape
  ``<div class=out>LABEL<div class=ins>VALUE</div></div>``. Attributes are
  written WITHOUT quotes (``class=ins``), so regexes must not rely on quoting.
* The UI language is switchable (RU / EN / UA) and rewrites every label and
  status word. Numbers are language-independent.
* Toggle buttons always offer the OPPOSITE of the current state. That makes the
  offered command token the most reliable, language-independent way to read the
  current state of a toggle -- far better than matching translated words.
"""

from __future__ import annotations

import re
from typing import Any

# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #

# Matches the opening <div class=ins ...> that holds a value, quoted or not.
_INS = r"<div[^>]*>"

# Status words meaning "off" / "on" in the three supported UI languages.
# "off" is checked first: no "on" word is a substring of an "off" word, but
# checking the negative first is the safer habit.
_OFF_WORDS = ("ВЫКЛ", "ВИМК", "DISABLED")
_ON_WORDS = ("ВКЛ", "ВВІМК", "ENABLED")

# Words meaning the station is locked, in the three languages.
_LOCKED_WORDS = ("ЗАБЛОК", "LOCKED")


def _search(html: str, pattern: str) -> str | None:
    """Return the first capture group of ``pattern`` in ``html``, else None."""
    match = re.search(pattern, html)
    if not match:
        return None
    return match.group(1).strip()


def _labelled(labels: tuple[str, ...], value_re: str) -> str:
    """Build a regex matching any of ``labels`` followed by a .ins value."""
    return "(?:" + "|".join(labels) + ")" + _INS + "(?:\\s*<br>\\s*)?(" + value_re + ")"


def _to_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _tristate(raw: str | None) -> bool | None:
    """Map a translated ENABLED/DISABLED word to a bool."""
    if not raw:
        return None
    text = raw.upper()
    if any(word in text for word in _OFF_WORDS):
        return False
    if any(word in text for word in _ON_WORDS):
        return True
    return None


def _offered(html: str, token: str) -> int | None:
    """Return N from an offered ``$TOKEN N`` command, if present.

    Toggle forms render the command that WOULD be applied if pressed, i.e. the
    opposite of the current state. Language-independent.
    """
    match = re.search(r"\$" + token + r"\s+([01])", html)
    if not match:
        return None
    return int(match.group(1))


def _state_from_offer(html: str, token: str) -> bool | None:
    """Current state of a toggle, inferred by inverting the offered command.

    For ``$GROUND`` / ``$LED`` / ``$TEMPS`` the argument 1 means "switch on", so
    being offered ``1`` means the feature is currently OFF.

    ``$AVAIL`` is the exception: its argument is inverted relative to the others
    (``$AVAIL 0`` = "make available"/unlock, ``$AVAIL 1`` = lock). Use
    :func:`_available_from_offer` for it instead.
    """
    offer = _offered(html, token)
    if offer is None:
        return None
    return offer == 0  # offering "turn off" means it is currently on


def _available_from_offer(html: str) -> bool | None:
    """Whether the station is currently available (unlocked).

    ``$AVAIL 0`` is offered while locked (button: "make available"), and
    ``$AVAIL 1`` while available (button: "lock").
    """
    offer = _offered(html, "AVAIL")
    if offer is None:
        return None
    return offer == 1


# --------------------------------------------------------------------------- #
#  Label tables (RU / EN / UA)
# --------------------------------------------------------------------------- #

_L_STATE = ("Текущее состояние", "Current status", "Поточний стан")
_L_MAX_CURRENT = (
    "Максимальный ток заряда",
    "Maximum charge current",
    "Максимальний зарядний струм",
)
_L_CURRENT = (
    "Текущий ток заряда",
    "Current charge current",
    "Поточний зарядний струм",
)
_L_VOLTAGE = ("Текущее напряжение", "Current voltage", "Поточна напруга")
_L_SESSION_ENERGY = (
    "Переданная мощность в сессии",
    "Transmitted power in session",
    "Передана потужність в сесії",
)
_L_SESSION_DURATION = (
    "Длительность сессии",
    "Duration of session",
    "Тривалість сесії",
)
_L_RCD = (
    "Защита от удара током",
    "Protection against electric shock",
    "Захист від ураження струмом",
)
_L_GROUND = ("Проверка заземления", "Ground check", "Перевірка заземлення")

# The timer block counts down either to UNLOCK (station waiting) or to LOCK
# (charging now, window about to close). Both must be recognised.
_TIMER_UNLOCK = ("разблокирует станцию через", "unlock the station in", "розблокує станцію через")
_TIMER_LOCK = ("заблокирует станцию через", "lock the station in", "заблокує станцію через")

_L_METER = ("Энергометр", "Energy meter", "Енергометр")
_L_TOTAL = (
    "Переданная мощность всего",
    "Total transmitted power",
    "Передана потужність всього",
)


# --------------------------------------------------------------------------- #
#  Page parsers
# --------------------------------------------------------------------------- #


def parse_main(html: str) -> dict[str, Any]:
    """Parse the live telemetry page ``/``."""
    state = _search(html, _labelled(_L_STATE, r"[^<]+"))
    current = _to_float(_search(html, _labelled(_L_CURRENT, r"[\d.]+")))

    # Timer countdown: direction matters, so match each variant separately.
    countdown = _search(html, _labelled(_TIMER_UNLOCK, r"[\d:]+"))
    target: str | None = "unlock" if countdown else None
    if countdown is None:
        countdown = _search(html, _labelled(_TIMER_LOCK, r"[\d:]+"))
        target = "lock" if countdown else None

    locked: bool | None = None
    if state:
        locked = any(word in state.upper() for word in _LOCKED_WORDS)

    return {
        # e.g. "CHARGEU base 32A" -- used as the device model in HA.
        "model": _search(html, r"<h1>([^<]+)</h1>"),
        "state": state,
        "max_current": _to_float(_search(html, _labelled(_L_MAX_CURRENT, r"[\d.]+"))),
        "current": current,
        "voltage": _to_float(_search(html, _labelled(_L_VOLTAGE, r"[\d.]+"))),
        "session_energy": _to_float(
            _search(html, _labelled(_L_SESSION_ENERGY, r"[\d.]+"))
        ),
        "session_duration": _search(html, _labelled(_L_SESSION_DURATION, r"[\d:]+")),
        "rcd_on": _tristate(_search(html, _labelled(_L_RCD, r"[^<]+"))),
        "ground_on": _tristate(_search(html, _labelled(_L_GROUND, r"[^<]+"))),
        "timer_countdown": countdown,
        "timer_target": target or "none",
        "locked": locked,
        # Language-independent: the only trustworthy "is it charging" signal.
        "charging": (current or 0.0) > 0.1,
    }


def parse_setup(html: str) -> dict[str, Any]:
    """Parse ``/setup``: lifetime counters and the ground/LED toggles."""
    # Lifetime counters are followed by an explanatory "(updated after session)"
    # note before the value, hence the lazy gap.
    meter = _search(
        html, "(?:" + "|".join(_L_METER) + r")[\s\S]*?([\d.]+)\s*(?:кВт|kW)"
    )
    total = _search(
        html, "(?:" + "|".join(_L_TOTAL) + r")[\s\S]*?([\d.]+)\s*(?:кВт|kW)"
    )

    # The firmware writes ``<option selected value='$AMPS 10'>`` but the language
    # select uses the opposite attribute order, so accept both.
    selected_amps = _search(html, r"<option[^>]*selected[^>]*value='\$AMPS (\d+)'")
    if selected_amps is None:
        selected_amps = _search(html, r"<option[^>]*value='\$AMPS (\d+)'[^>]*selected")

    return {
        "meter": _to_float(meter),
        "total_energy": _to_float(total),
        # Toggle states inferred from the offered (opposite) command token.
        "ground_on": _state_from_offer(html, "GROUND"),
        "led_on": _state_from_offer(html, "LED"),
        "setup_max_current": _to_float(selected_amps),
    }


def parse_pass(html: str) -> dict[str, Any]:
    """Parse ``/pass``: availability, one-shot session and timer settings."""
    # Real markup: ``<input name=timer value=0 type=hidden>``. The trailing \s is
    # essential -- without it this would also match name=timerb / timerbc /
    # timere / timerec, which are different fields.
    timer_hidden = _search(html, r"name=timer\s+value='?([01])'?")

    timer_enabled: bool | None = None
    if timer_hidden is not None:
        # The form submits the opposite of the current timer state.
        timer_enabled = timer_hidden == "0"

    # Real markup: ``<option selected value='10'>``.
    amps = _search(html, r"<option[^>]*selected[^>]*value='(\d+)'")
    if amps is None:
        amps = _search(html, r"<option[^>]*value='(\d+)'[^>]*selected")

    return {
        # $AVAIL 0 offered => currently locked; $AVAIL 1 offered => available.
        "available": _available_from_offer(html),
        "single_session": _state_from_offer(html, "TEMPS"),
        "timer_enabled": timer_enabled,
        "timer_begin": _search(html, r"name=timerb\s+type=time\s+value='([\d:]+)'"),
        "timer_end": _search(html, r"name=timere\s+type=time\s+value='([\d:]+)'"),
        "timer_amps": _to_float(amps),
    }
