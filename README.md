# CHARGEU EV Charger — Home Assistant integration

<p align="center">
  <img src="docs/images/chargeu-station.jpg" alt="CHARGEU portable EV charging stations" width="640">
</p>
<p align="center"><sub>CHARGEU portable charging stations. Photo © <a href="https://chargeu.eu">chargeu.eu</a>.</sub></p>

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

## Getting Home Assistant onto the charger's network

This is the part that trips people up, so read it before installing.

The station has **no station/client Wi-Fi mode** — it is *only* a Wi-Fi
**access point**. It broadcasts its own SSID and serves its web interface at a
fixed `192.168.4.1`. It cannot join your home Wi-Fi, and it knows nothing about
any other subnet, so it has **no return route** back to a device on your LAN.

That means Home Assistant can't reach it directly (HA has to stay on your home
network). The reliable fix is a cheap intermediate router that bridges the two
networks:

```
   CHARGEU station                Intermediate router                Home network
   (Wi-Fi access point)           (client/WISP + NAT)                (your LAN)

  ┌──────────────────┐          ┌───────────────────────┐         ┌──────────────┐
  │                  │  Wi-Fi   │ Wi-Fi STA: 192.168.4.x │  LAN /  │ Home router  │
  │  SSID: CHARGEU   │◄─────────┤   ▲ masquerade (NAT)   │  eth    │ 192.168.1.1  │
  │  192.168.4.1     │  client  │   │                    ├────────►│              │
  │  (AP only)       │          │ LAN: 192.168.1.50      │         └──────┬───────┘
  │  192.168.4.0/24  │          └───────────────────────┘                │
  └──────────────────┘                                            ┌──────┴───────┐
                                                                  │ Home         │
      static route on the home router:                            │ Assistant    │
      192.168.4.0/24  ──►  192.168.1.50                           │ 192.168.1.10 │
                                                                  └──────────────┘
```

**Why a plain Wi-Fi bridge/repeater is not enough:** the charger only ever
replies to addresses it believes are on its own `192.168.4.0/24`. A packet from
`192.168.1.10` (Home Assistant) would reach it, but the reply would be dropped —
the charger has no gateway to send it back through. So the intermediate router
must **NAT (masquerade)** everything leaving its client interface. From the
charger's point of view, every request then comes from a single neighbour on its
own subnet, and the reply goes straight back to the router, which un-NATs it and
forwards it to Home Assistant.

**Setup on the intermediate router** (any OpenWRT / GL.iNet / DD-WRT travel
router works; it's a ~€20 box):

1. Put its **Wi-Fi in client / WISP / repeater mode** and join the charger's
   SSID. It gets (or is given a static) address on `192.168.4.0/24`.
2. **Enable NAT/masquerade on that client (WAN) interface.** On most travel
   routers "WISP mode" does this for you; on stock OpenWRT the `wwan` zone is
   masqueraded by default.
3. Connect its **LAN/Ethernet to your home network** with a static address on
   your LAN (e.g. `192.168.1.50`). Disable its DHCP server so it doesn't fight
   your home router.
4. Add **one static route** on your home router so the rest of the LAN can find
   the charger:
   `192.168.4.0/24` → gateway `192.168.1.50` (the intermediate router).
   *(If you can't add a route on the home router, add it on the HA host instead,
   or route only the single host `192.168.4.1/32`.)*

After that, Home Assistant reaches the charger at its normal `192.168.4.1` — the
integration's default — and you never have to touch the address it uses.

> **Tip:** verify the path before adding the integration. From a machine on your
> LAN, `curl http://192.168.4.1/` should return the charger's HTML. If that
> works, the config flow will too.

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
over the network first — see
[Getting Home Assistant onto the charger's network](#getting-home-assistant-onto-the-chargers-network)
above. The polling interval (default 15 s) can be changed in the integration's
options.

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
