# CLAUDE.md

Instructions for Claude Code and other AI agents working in this repository.

**The full guidance lives in [AGENTS.md](AGENTS.md).** It is kept in one place so
that every agent reads the same rules. Read it before making changes.

## The short version

This is a Home Assistant integration for CHARGEU EV chargers. The device has no
API — the integration scrapes HTML pages and submits the device's own POST forms.

Non-negotiables:

- **Never POST a command to a live charger without explicit human confirmation.**
  Unlocking the station immediately starts charging a real car.
  `chargeu.reset_energy_meter` irreversibly zeroes the lifetime meter.
- **`parser.py` must not import `homeassistant`.** The test suite imports it
  directly; an HA import makes the parsing logic untestable.
- **Work against `tests/fixtures/`, not live hardware.** They are real captures
  covering charging-under-timer, locked, all three UI languages, and edge cases.
- Run `python -m pytest tests/ -v` before committing.

Device quirks that have already caused real bugs — `$AVAIL` is inverted relative
to the other command tokens, `name=timer` regexes collide with `name=timerb`,
toggle buttons show the *opposite* of the current state, and the UI language
rewrites every label. All of these are explained in
[AGENTS.md](AGENTS.md#hardware-quirks-that-will-bite-you) and documented in
detail in [docs/interface-map.md](docs/interface-map.md).
