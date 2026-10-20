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


def test_pass_without_one_shot_block():
    """Timer mode inside the unlock window: the one-shot block is not rendered.

    Captured live while the station was charging under the timer. The firmware
    only renders "Разовая зарядная сессия" in some modes -- here the whole block
    is missing, so there is no $TEMPS to invert and the state is genuinely
    unknown. The timer fields on the same page must still parse.
    """
    html = load("pass_timer_ru.html")
    assert "$TEMPS" not in html  # guards the fixture itself

    data = parse_pass(html)

    assert data["single_session"] is None

    # Everything else on the page is unaffected by the missing block.
    assert data["timer_enabled"] is True
    assert data["timer_begin"] == "08:45"
    assert data["timer_end"] == "18:30"
    assert data["timer_amps"] == 10.0


def test_pass_available_reflects_the_manual_flag_not_reality():
    """`$AVAIL` on /pass is the manual availability flag, not the live state.

    The same capture was taken while the station was unlocked by the timer and
    actively charging, yet /pass still offers "$AVAIL 0" (make available)
    because the manual flag stayed off. Consumers must prefer `locked` from "/".
    """
    assert parse_pass(load("pass_timer_ru.html"))["available"] is False


def test_main_car_charged_while_unlocked():
    """Session finished: the station is still unlocked, but current has dropped.

    A state no other fixture covers -- "ЭЛЕКТРОМОБИЛЬ ЗАРЯЖЕН" with the timer
    still holding the station open. `charging` must follow the current, not the
    lock state, or a full battery would keep reporting as charging.
    """
    data = parse_main(load("main_charged_ru.html"))

    assert data["state"] == "ЭЛЕКТРОМОБИЛЬ ЗАРЯЖЕН"
    assert data["current"] == 0.0
    assert data["charging"] is False
    assert data["locked"] is False

    # The counters keep the finished session's totals.
    assert data["session_energy"] == 14.79
    assert data["session_duration"] == "06:59:48"

    # Timer still counts down to LOCK even though nothing is charging.
    assert data["timer_target"] == "lock"
    assert data["timer_countdown"] == "2:35:05"


# --------------------------------------------------------------------------- #
#  /pass: station clock
# --------------------------------------------------------------------------- #


def test_pass_clock_not_set_hides_the_timer_form():
    """After a power loss the clock reads "НЕ УСТАНОВЛЕНО" and the timer form goes.

    Captured live after the station had lost its clock (no NTP, no RTC battery).
    Only a bare "Таймер: ВЫКЛЮЧЕН" line is left -- no timerb / timere / amps
    select / toggle -- so every timer field is unknown, not merely "off".
    """
    html = load("pass_noclock_ru.html")
    assert "НЕ УСТАНОВЛЕНО" in html and "name=timerb" not in html  # guards the fixture

    data = parse_pass(html)

    assert data["clock_set"] is False
    assert data["timer_enabled"] is None
    assert data["timer_begin"] is None
    assert data["timer_end"] is None
    assert data["timer_amps"] is None
    # The rest of the page is unaffected.
    assert data["available"] is False
    assert data["single_session"] is False


def test_pass_timer_form_returns_after_clock_sync():
    """The same station seconds after "Sync clock": the timer form is back.

    The firmware kept the stored timer values through the power loss; it only
    hid them while the clock was unset.
    """
    data = parse_pass(load("pass_locked_ru.html"))

    assert data["clock_set"] is True
    assert data["timer_enabled"] is False
    assert data["timer_begin"] == "08:45"
    assert data["timer_end"] == "18:30"
    assert data["timer_amps"] == 10.0


@pytest.mark.parametrize(
    "fixture",
    # pass_ru renders the time itself, the other two an empty sttime placeholder.
    ["pass_ru.html", "pass_timer_ru.html", "pass_locked_ru.html"],
)
def test_pass_clock_set(fixture: str):
    assert parse_pass(load(fixture))["clock_set"] is True


def test_pass_clock_unknown_without_clock_block():
    assert parse_pass("<html><body>Not found: /pass</body></html>")["clock_set"] is None


def test_one_shot_block_hidden_only_while_the_timer_is_in_control():
    """The one-shot block is missing only with timer ON and manual flag OFF.

    pass_ru.html          flag on,  timer on  -> block present
    pass_timer_ru.html    flag off, timer on  -> block absent
    pass_locked_ru.html   flag off, timer off -> block present (this capture)

    Neither condition hides it alone: it goes while the timer is the thing
    holding the station.
    """
    data = parse_pass(load("pass_locked_ru.html"))

    assert data["available"] is False  # offers "$AVAIL 0": manual flag is off
    assert data["timer_enabled"] is False
    assert data["single_session"] is False  # block present, offers "$TEMPS 1"

    on_flag_on_timer = parse_pass(load("pass_ru.html"))
    assert on_flag_on_timer["available"] is True
    assert on_flag_on_timer["timer_enabled"] is True
    assert on_flag_on_timer["single_session"] is False

    off_flag_on_timer = parse_pass(load("pass_timer_ru.html"))
    assert off_flag_on_timer["available"] is False
    assert off_flag_on_timer["timer_enabled"] is True
    assert off_flag_on_timer["single_session"] is None
