"""Unit tests for the CHARGEU HTML parser.

Fixtures are real markup captured from a live CHARGEU base 32A, including the
charging-under-timer state and all three UI languages.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "chargeu"))

from parser import parse_main, parse_pass, parse_setup  # noqa: E402

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
#  Main page
# --------------------------------------------------------------------------- #


def test_charging_under_timer():
    """The tricky real-world case: charging while the timer counts down to LOCK."""
    data = parse_main(load("main_charging_timer_ru.html"))

    assert data["state"] == "ЗАРЯЖАЮ"
    assert data["current"] == 9.77
    assert data["voltage"] == 224.0
    assert data["max_current"] == 10.0
    assert data["session_energy"] == 9.36
    assert data["session_duration"] == "04:28:36"
    assert data["rcd_on"] is True
    assert data["ground_on"] is False

    # Charging must be detected, and the station must NOT be reported as locked
    # even though a timer countdown is present.
    assert data["charging"] is True
    assert data["locked"] is False

    # Countdown runs towards LOCK in this mode.
    assert data["timer_countdown"] == "5:16:20"
    assert data["timer_target"] == "lock"


def test_locked_waiting_for_timer():
    data = parse_main(load("main_locked_timer_ru.html"))

    assert data["state"] == "ЗАБЛОКИРОВАНА"
    assert data["locked"] is True
    assert data["charging"] is False
    assert data["current"] == 0.0
    assert data["timer_countdown"] == "14:04:23"
    assert data["timer_target"] == "unlock"


@pytest.mark.parametrize(
    ("fixture", "state"),
    [
        ("main_locked_timer_ru.html", "ЗАБЛОКИРОВАНА"),
        ("main_locked_timer_en.html", "LOCKED"),
        ("main_locked_timer_ua.html", "ЗАБЛОКОВАНА"),
    ],
)
def test_all_languages_parse_identically(fixture: str, state: str):
    """Switching the station language must not break parsing."""
    data = parse_main(load(fixture))

    assert data["state"] == state
    assert data["locked"] is True
    assert data["charging"] is False
    assert data["max_current"] == 10.0
    assert data["voltage"] == 216.0
    assert data["session_energy"] == 2.82
    assert data["session_duration"] == "01:24:35"
    # RCD enabled, ground check disabled -- in every language.
    assert data["rcd_on"] is True
    assert data["ground_on"] is False
    assert data["timer_target"] == "unlock"
    assert data["timer_countdown"] is not None


def test_missing_timer_block_is_tolerated():
    """With the timer off the countdown block disappears entirely."""
    html = load("main_locked_timer_ru.html")
    start = html.index("<div class=out style=")
    end = html.index("<br>", start) + len("<br>")
    data = parse_main(html[:start] + html[end:])

    assert data["timer_countdown"] is None
    assert data["timer_target"] == "none"
    # Everything else still parses.
    assert data["state"] == "ЗАБЛОКИРОВАНА"
    assert data["locked"] is True


def test_garbage_input_does_not_raise():
    data = parse_main("<html><body>Not found: /wifi</body></html>")

    assert data["state"] is None
    assert data["current"] is None
    assert data["charging"] is False
    assert data["locked"] is None


# --------------------------------------------------------------------------- #
#  /setup
# --------------------------------------------------------------------------- #


def test_setup_counters_and_toggles():
    data = parse_setup(load("setup_ru.html"))

    assert data["meter"] == 1001.60
    assert data["total_energy"] == 10829.91
    assert data["setup_max_current"] == 10.0

    # Toggle state is inferred by inverting the OFFERED command:
    # offering "$GROUND 1" means ground is currently OFF.
    assert data["ground_on"] is False
    # offering "$LED 0" means the LED is currently ON.
    assert data["led_on"] is True


# --------------------------------------------------------------------------- #
#  /pass
# --------------------------------------------------------------------------- #


def test_pass_availability_and_timer():
    data = parse_pass(load("pass_ru.html"))

    # Offering "$AVAIL 1" (lock it) means the station is currently available.
    assert data["available"] is True
    # Offering "$TEMPS 1" means one-shot session is currently off.
    assert data["single_session"] is False

    # Hidden timer field carries the value that WOULD be submitted, so 0 means
    # the timer is currently enabled.
    assert data["timer_enabled"] is True
    assert data["timer_begin"] == "08:45"
    assert data["timer_end"] == "18:30"
    assert data["timer_amps"] == 10.0


def test_timer_field_not_confused_with_timerb():
    """name=timer must not accidentally match name=timerb / timerbc / timerec."""
    data = parse_pass(load("pass_ru.html"))

    # timerbc/timerec are both value=1; if they leaked in, timer_enabled would
    # flip to False.
    assert data["timer_enabled"] is True
