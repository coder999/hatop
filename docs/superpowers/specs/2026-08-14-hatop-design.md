# hatop — design spec

Date: 2026-08-14
Status: approved, pending implementation plan

## Overview

`btop`-style live terminal dashboard for Home Assistant sensor data published
over MQTT. Companion to (not a replacement for) `ha_summary`
(`/usr/local/bin/ha_summary` on nexus — see
`/home/mark/projects/serverconfig/nexus.md`, "Login Banner + MQTT + Home
Assistant Summary" section), which remains the quick one-shot snapshot;
`hatop` is the full-screen, continuously-live view.

Distributed as a generic, reusable open-source tool
(`github.com/coder999/hatop`, public repo) — it ships no household-specific
data. A user's real entity list, labels, and MQTT credentials live entirely
in a local, gitignored config file.

## Requirements (from brainstorming)

- **Live**, not polled: persistent MQTT subscription, panels update the
  moment a value changes — not a redraw-on-timer snapshot.
- Built with **Python + Textual** (`paho-mqtt` for MQTT, `pyyaml` for config).
- **Sparkline history** for numeric sensors (temps, gauges), in-memory only
  (resets on restart — no persistence requirement).
- **Config-driven** entity list (slug/label/unit/group/kind), not hardcoded
  in source — mirrors and generalizes `ha_summary`'s hardcoded groups
  (Temperatures/Water/Energy/Environment/Security).
- Packaged as a **pip-installable console script** (`hatop` command),
  mimicking how `btop` installs as a single command — not a wrapper script
  around a venv.
- **Public repo, private config**: the repo contains only generic/example
  data; the real config (household entity labels, MQTT credentials) stays
  local at `~/.config/hatop/config.yaml`, gitignored.

## Repo layout

```
hatop/
  pyproject.toml          # [project.scripts] hatop = "hatop.__main__:main"
  README.md                # usage docs, config schema, screenshot
  LICENSE
  .gitignore               # ignores real config, .venv, __pycache__
  config.example.yaml      # generic/fake sensor names, safe to publish
  docs/superpowers/specs/  # this file
  src/hatop/
    __init__.py
    __main__.py            # entry point
    config.py              # loads ~/.config/hatop/config.yaml (XDG), validates schema
    mqtt_client.py          # paho-mqtt background client; parses "<value>|<epoch>" payloads, posts updates to the app
    state.py                # pure data model: per-sensor value/timestamp/history ring buffer, staleness calc
    app.py                  # Textual App: layout, header (connection status), panels
    widgets.py              # grid-cell, gauge/bar, enum-status, sparkline widgets
  tests/
    test_config.py
    test_state.py           # payload parsing, staleness, sparkline windowing
```

## Data source

Same wire format `ha_summary` already uses: retained MQTT messages under
`<topic_prefix>/<slug>` (default `nexus/ha/<slug>`), payload
`<value>|<unix-epoch-seconds-published>`. Subscribing to `<topic_prefix>/#`
causes the broker to deliver every currently-retained message immediately on
subscribe (MQTT retained-message semantics) — this alone satisfies both
"show current state on startup" and "live updates thereafter" with one
subscription, no separate poll step.

## Config schema

`~/.config/hatop/config.yaml` (XDG config dir), mode 600 recommended, never
committed:

```yaml
mqtt:
  host: 192.168.1.10
  port: 1883
  username: nexus
  password: "..."
  topic_prefix: "nexus/ha"
stale_seconds: 21600       # 6h, same default as ha_summary
sparkline_points: 120       # ring buffer size per sensor
groups:
  - name: Temperatures
    layout: grid            # 3-col grid, like ha_summary's temp block
    sensors:
      - {slug: weather_temp, label: Weather, kind: temp, unit: "F"}
  - name: Water
    sensors:
      - {slug: home_water_pressure, label: Home Water Pressure, kind: gauge, unit: PSI}
  - name: Energy
    sensors:
      - {slug: energy_load_home, label: Home Load, kind: gauge, unit: W}
      - {slug: energy_cumulative, label: Cumulative Use, kind: counter, unit: kWh, scale: 0.001}
  - name: Security
    sensors:
      - {slug: alarm_state, label: Security System, kind: enum, good: [disarmed], bad: [triggered]}
      - {slug: lock_front_door, label: Front Door Lock, kind: enum, good: [locked]}
      - {slug: garage_door_south, group_as: garage_doors, good: [closed]}
```

`kind` drives rendering:

- `temp` / `gauge` — current value + live sparkline of recent history.
- `counter` — scaled value (`scale` multiplier, e.g. Wh→kWh like
  `ha_summary`'s `/1000` conversion), history kept but no sparkline required.
- `enum` — colored status text; color from `good`/`bad` value lists (green /
  red / yellow fallback for unlisted values).
- Sensors sharing a `group_as` (e.g. the three garage doors) collapse into a
  single line: "All closed" when every member is in its `good` list, else
  "OPEN: <labels>" — same behavior `ha_summary` has today.

`config.example.yaml` ships in the repo with fake sensor names covering each
`kind`, so the schema is self-documenting without exposing real data.

## Data flow

1. `mqtt_client.py` runs `paho-mqtt`'s network loop in a background thread
   (`loop_start()`, auto-reconnect enabled), parses each message into
   `(slug, value, ts)`, and hands it to the app via a thread-safe queue /
   Textual's `call_from_thread`.
2. `state.py` holds the pure data model: per-slug latest value, timestamp,
   and a bounded deque (size `sparkline_points`) for history. Staleness is
   `now - ts >= stale_seconds`, same threshold semantics as `ha_summary`.
3. `app.py` (Textual `App`) owns the layout: a header showing MQTT
   connection state (connected / reconnecting / host), and one panel per
   config `group`. Textual's reactive/watch system repaints only the widget
   whose backing sensor changed — no full-screen redraw per update.

## Error handling

- Missing/unreadable config file → clear startup error naming the expected
  path and pointing at `config.example.yaml`.
- Sensor with no data yet → "n/a" (gray), matching `ha_summary`.
- Stale sensor (past `stale_seconds`) → dimmed / marked, same default
  threshold (6h) as `ha_summary`, configurable.
- Broker unreachable / disconnects mid-session → header reflects
  disconnected/reconnecting state; `paho-mqtt` auto-reconnect handles
  recovery without restarting the app.

## Testing

TDD on the pure logic layer, no broker or terminal required:

- `test_config.py` — schema loading/validation, defaults, error messages for
  malformed config.
- `test_state.py` — payload parsing (`<value>|<epoch>`), staleness
  calculation, sparkline ring-buffer windowing, `group_as` collapsing logic
  (garage-doors-style "All closed" / "OPEN: ...").

The Textual UI layer (`app.py`, `widgets.py`) gets light manual/pilot-based
smoke testing rather than full unit coverage — standard for TUI rendering
code where the value is in the pure logic underneath it.

## Deployment (nexus)

`pipx install /home/mark/projects/hatop` (or directly from the GitHub repo
once pushed) puts `hatop` on `PATH` — no wrapper script, unlike the
venv-wrapper pattern originally considered. Real config lands at
`~/.config/hatop/config.yaml` on nexus, populated with the actual 25-entity
household mapping mirroring `ha_summary`'s groups. Optionally mentioned
alongside `ha_summary` in the login banner's "Commands" list — not
auto-run, same as `ha_summary` today.

## Out of scope (YAGNI, revisit only if needed)

- Persisted history across restarts (sparklines are in-memory only).
- Multiple screens / navigation (single-screen dashboard for v1).
- Any keybinding beyond quit (`q` / Ctrl+C); no interactive controls planned.
- Auto-discovery of new MQTT topics — the config file is the source of
  truth for which sensors are shown.
