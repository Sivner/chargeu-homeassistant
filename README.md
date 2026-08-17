# CHARGEU EV Charger — Home Assistant integration

Local, cloud-free integration for **CHARGEU** EV charging stations
(`chargeu.eu`, firmware ~2015–2018, e.g. *CHARGEU base 32A*).

These stations expose **no API** — only a small HTML web interface. This
integration talks to that interface the same way a browser does: it reads the
rendered pages and submits the same POST forms the built-in UI submits.

> **Status:** developed and tested against a live *CHARGEU base 32A*. If you have
> a different model, please open an issue with the HTML of your `/` page — the
> parser is label-driven and easy to extend.

## Features

**Sensors**

| Entity | Notes |
|---|---|
| Status | raw station status text |
| Charging current / Voltage / Power | power is computed as I × U |
| Maximum current | configurable, see below |
| Session energy / Session duration | resets each session |
| Energy meter / Total energy delivered | lifetime counters, suitable for the Energy dashboard |
| Timer countdown | time until the timer acts |
| Timer action | `unlock` / `lock` / `none` — what the countdown leads to |

**Binary sensors:** Charging, Locked, Ground check, Shock protection (RCD).

**Controls:** Station available (unlock/lock), One-shot session, Maximum
charging current (6–32 A), Ground check, Light indication, Sync clock.

**Services:** `chargeu.set_timer`, `chargeu.reset_energy_meter`.

## Installation

### HACS (recommended)

1. HACS → Integrations → ⋮ → **Custom repositories**
2. Add this repository's URL, category **Integration**
3. Install **CHARGEU EV Charger**, then restart Home Assistant
4. Settings → Devices & Services → **Add Integration** → *CHARGEU*

### Manual

Copy `custom_components/chargeu` into your `<config>/custom_components/`, restart
Home Assistant, then add the integration from the UI.

## Configuration

Only the host is required — by default `192.168.4.1`, which is the address of
the station's own Wi-Fi access point. Home Assistant must be able to reach it
directly. The polling interval (default 15 s) can be changed in the
integration's options.

## Important behaviour notes

These are properties of the hardware, discovered while probing a live unit:

- **Unlocking starts charging.** Turning on *Station available* (or *One-shot
  session*) with a car plugged in begins charging immediately.
- **Changing the timer resets the current session counters.** The lifetime
  energy meter is unaffected.
- **`reset_energy_meter` is irreversible.** It zeroes the station's lifetime
  meter; there is no undo. It is exposed as a service rather than a button on
  purpose.
- The station has **no NTP**; its clock drifts and the timer depends on it. The
  *Sync clock* button pushes Home Assistant's time to the station — worth
  automating occasionally.

## How it works

The device renders every value as
`<div class=out>LABEL<div class=ins>VALUE</div></div>`, with **unquoted HTML
attributes**, and each page carries a 4-second `<meta refresh>`.

Two details make naive scraping fragile, and this integration handles both:

1. **The UI language (RU / EN / UA) rewrites every label and status word.** The
   parser matches all three languages, and derives the important states from
   language-independent signals: charging is detected from measured current
   (> 0.1 A), not from a translated word.
2. **Toggle buttons render the _opposite_ of the current state.** So the offered
   command token is used to read the current state — e.g. being offered
   `$GROUND 1` means the ground check is currently *off*. This is
   language-independent and exact. Note that `$AVAIL` is inverted relative to
   the other tokens (`$AVAIL 0` means *make available*).

`/` is polled every cycle; `/setup` and `/pass` are polled every 5 minutes and
refreshed immediately after any command, so the UI does not visibly bounce back.
All requests to the charger are serialised — its embedded web server is easily
overwhelmed.

A full description of the device's interface, including every command token, is
in [`docs/interface-map.md`](docs/interface-map.md).

## Development

```bash
pip install pytest
python -m pytest tests/ -v
```

Tests run the parser against real HTML captured from a live station, covering
charging-under-timer, locked-waiting-for-timer, all three UI languages, a
missing timer block, and malformed input.

## License

MIT
