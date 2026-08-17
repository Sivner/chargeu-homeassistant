# AGENTS.md

Guidance for AI coding agents working on this repository.

## What this project is

A Home Assistant custom integration for **CHARGEU** EV charging stations
(firmware ~2015–2018). The hardware has **no API** — only HTML pages and POST
forms. Everything this integration does is scraping those pages and submitting
the same forms the built-in web UI submits.

That single fact drives most of the design decisions below. Read them before
changing parsing or command code.

## Safety rules — read first

This integration controls a device that delivers **32 A of mains power to a
car**. When working against a real station:

- **Never send a POST command to a live charger without explicit human
  confirmation for that specific command.** Reads (`GET /`, `/setup`, `/pass`)
  are safe.
- **Unlocking starts charging.** `$AVAIL 0` and `$TEMPS 1` immediately begin
  charging a plugged-in car. There is no "unlock but stay idle" state.
- **`emreset=1` is irreversible.** It zeroes the lifetime energy meter. It is
  exposed as a service (`chargeu.reset_energy_meter`), never as a button, on
  purpose. Do not "improve" this by adding a button entity.
- **Changing the timer resets the current session counters.** The lifetime meter
  is unaffected. Do not call `async_set_timer` casually in tests or examples.

Prefer working against the fixtures in `tests/fixtures/` instead of live
hardware. They cover every state we have observed.

## Layout

```
custom_components/chargeu/
  parser.py        Pure-python HTML parsing. NO Home Assistant imports.
  api.py           Async HTTP client. One method per device command.
  coordinator.py   DataUpdateCoordinator: fast "/" poll + slow /setup,/pass.
  entity.py        Base entity (device info, availability).
  sensor.py binary_sensor.py switch.py number.py button.py
  config_flow.py   UI setup (host) + options (poll interval).
  const.py         Domain, defaults, service names, amp limits.
  services.yaml    Service schemas shown in the UI.
  strings.json     English strings (duplicate of translations/en.json).
  translations/    en.json, ru.json
tests/
  test_parser.py   Parser tests.
  fixtures/        Real HTML captured from a live CHARGEU base 32A.
docs/
  interface-map.md Full reverse-engineered device documentation.
```

## Architecture

`coordinator` polls `/` every cycle (default 15 s) and `/setup` + `/pass` every
5 minutes. Results are parsed into one flat dict, which every entity reads from.

Merge precedence: values from `/` (live) override the cached slow-page values,
**but only where `/` actually produced a non-`None` value**. Some keys (e.g.
`ground_on`) appear on both pages; the live page wins. Do not change this to a
plain `dict.update()` — that would wipe good cached values with `None`.

After any command, entities call `coordinator.async_refresh_after_command()`,
which resets the slow-page timer and refreshes immediately. **Every new command
must do this**, otherwise the UI visibly bounces back to the old state for up to
15 seconds.

All HTTP requests are serialised through an `asyncio.Lock` in `api.py`. The
device's embedded web server is single-threaded and falls over under concurrent
requests. Do not remove the lock or add parallel fetches.

## Hardware quirks that will bite you

These were all discovered by probing a live unit. They are not obvious from the
markup.

1. **UI language rewrites every label and status word** (RU / EN / UA). Parsing
   matches all three. Never rely on a single language, and never rely on a
   status *word* for logic when a language-independent signal exists.

2. **Charging is detected from measured current (`> 0.1 A`)**, not from the
   status text. This works in every language and every firmware mode.

3. **Toggle buttons render the _opposite_ of the current state.** The form shows
   the command that *would* be applied. So the offered token tells you the
   current state by inversion: being offered `$GROUND 1` means ground check is
   currently **off**. This is exact and language-independent — prefer it over
   parsing translated words.

4. **`$AVAIL` is inverted relative to every other token.** `$AVAIL 0` means
   *make available* (unlock); `$AVAIL 1` means lock. `$GROUND`/`$LED`/`$TEMPS`
   all use 1 = on. There is a dedicated `_available_from_offer()` for this;
   do not route `AVAIL` through the generic `_state_from_offer()`.

5. **`name=timer` needs a trailing `\s` in regexes.** The page also contains
   `name=timerb`, `name=timerbc`, `name=timere`, `name=timerec`. A sloppy
   pattern matches those and silently inverts the timer state. There is a
   regression test for exactly this.

6. **HTML attributes are unquoted** (`<div class=ins>`), and quoting is
   inconsistent between fields (`<option selected value='...'>` vs
   `<option value='...' selected>`). Match with `<div[^>]*>` and accept both
   attribute orders. Never assume quotes.

7. **The timer countdown block is optional and bidirectional.** It is absent
   when the timer is off; it counts down to *unlock* when waiting and to *lock*
   while charging. Both label variants must be recognised — an early version
   only handled "will unlock" and silently lost the countdown during charging.

8. **The station has no NTP.** Its clock drifts and the timer depends on it.

9. **Unknown paths return `Not found: /...` with HTTP 200-ish behaviour.** Do
   not treat "got a response" as "it's a CHARGEU". `config_flow` validates by
   checking that the status block or `<h1>` actually parsed.

## Running checks

```bash
pip install pytest
python -m pytest tests/ -v
```

Tests import `parser.py` directly, without Home Assistant. **Keep `parser.py`
free of `homeassistant` imports** — if you add one, the whole test suite dies
and the parsing logic becomes untestable.

There is no HA instance in CI; `hassfest` and the HACS action validate metadata
only. Logic correctness comes from the parser tests, so new parsing behaviour
needs a new fixture and test.

## How to add a sensor

1. Add a `ChargeuSensorDescription` to `SENSORS` in `sensor.py` with a
   `translation_key`.
2. If it needs new data, add the field in `parser.py` and a test for it.
3. Add the name to **all three** of `strings.json`, `translations/en.json`,
   `translations/ru.json` under `entity.sensor.<translation_key>`.

`strings.json` and `translations/en.json` are intentionally identical. If you
edit one, edit the other.

For an enum sensor, the `options=[...]` list in `sensor.py` must exactly match
the `state` keys in both translation files.

## How to add a command

1. Add a method to `ChargeuApi`. Pass a plain dict as `data=` — aiohttp encodes
   it exactly like a browser (`$` → `%24`, space → `+`), which is what the
   firmware expects. Do not hand-build the body string.
2. Wrap `ChargeuApiError` into `HomeAssistantError` at the entity layer.
3. Call `await self.coordinator.async_refresh_after_command()` afterwards.
4. If it is destructive or starts charging, document it in the README and keep
   it out of the default dashboard (service, or
   `entity_registry_enabled_default=False`).

## Supporting a new model or language

The parser is label-driven. To add a language, extend the `_L_*` tuples and the
`_ON_WORDS` / `_OFF_WORDS` / `_LOCKED_WORDS` lists in `parser.py`, then add a
fixture in that language and extend the parametrised language test.

When a user reports "my model doesn't parse", ask for the raw HTML of `/` and
add it as a fixture before changing any regex.

## Conventions

- Type hints everywhere; `from __future__ import annotations` at the top.
- Entity descriptions (frozen dataclasses) over per-entity subclasses.
- Unique IDs are `f"{entry_id}_{key}"` — never change the `key` of a shipped
  entity, it orphans users' entity registry entries and their history.
- `_attr_has_entity_name = True`; names come from translations, not hardcoded.
- Comments explain *why* (especially the quirks above), not *what*.

## Before committing

- `python -m pytest tests/ -v` passes.
- Any new `translation_key` exists in `strings.json`, `en.json` and `ru.json`.
- Any new service is in `services.yaml`, registered in `__init__.py`, and
  present in both translation files under `services`.
- Any new platform is added to `PLATFORMS` in `__init__.py` and has an
  `async_setup_entry`.
- `manifest.json` version bumped for a release.
