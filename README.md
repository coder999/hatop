# hatop

A [btop](https://github.com/aristocratos/btop)-style live terminal
dashboard for Home Assistant sensor data streamed over MQTT.

Subscribes to retained + live MQTT messages (payload format
`<value>|<unix-epoch-seconds>`) and renders them as live-updating panels
with sparkline history — built for setups that already publish HA sensor
state to MQTT on a fixed topic tree (`<topic_prefix>/<slug>`).

## Install

```bash
pipx install git+https://github.com/coder999/hatop.git
```

Or from a local checkout:

```bash
pipx install /path/to/hatop
```

## Configure

hatop reads `~/.config/hatop/config.yaml` (or `$XDG_CONFIG_HOME/hatop/config.yaml`).
Copy `config.example.yaml` as a starting point:

```bash
mkdir -p ~/.config/hatop
cp config.example.yaml ~/.config/hatop/config.yaml
chmod 600 ~/.config/hatop/config.yaml
```

Then edit it to list your own broker connection and sensors:

- `mqtt.topic_prefix` — messages are expected at `<topic_prefix>/<slug>`.
- `stale_seconds` — how long before a sensor with no update is marked stale
  (default 21600 = 6h).
- `sparkline_points` — how many recent values to keep per numeric sensor for
  its live sparkline (default 120; in-memory only, resets on restart).
- `groups` — one or more named sections, each a list of sensors:
  - `slug` — the MQTT topic suffix.
  - `kind` — `temp` / `gauge` (value + sparkline), `counter` (scaled value,
    no sparkline — e.g. a cumulative energy meter), or `enum` (colored
    status text, e.g. a lock or alarm state).
  - `label` — display name (defaults to `slug`).
  - `unit` — suffix appended to the value, e.g. `"F"` or `" PSI"` (include
    your own leading space if you want one).
  - `scale` — multiplier applied before display (e.g. `0.001` to show a
    Wh-native sensor in kWh). `temp`/`gauge`/`counter` only.
  - `good` / `bad` — lists of string values that render green / red for
    `enum` sensors; anything else renders yellow.
  - `group_as` — sensors sharing the same key collapse into a single "All
    closed" / "OPEN: <labels>" line (e.g. multiple garage door sensors).
  - `layout: grid` on a group arranges its sensors in a 3-column grid
    instead of one per line (handy for a dozen+ temperature sensors).

**Keep your real config out of version control** if you fork/publish this
repo — it will contain your household's entity layout and MQTT
credentials. `config.yaml` is already gitignored.

## Run

```bash
hatop
```

`q` or `Ctrl+C` quits.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```
