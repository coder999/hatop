# hatop

A [btop](https://github.com/aristocratos/btop)-style live terminal
dashboard for Home Assistant sensor data streamed over MQTT.

Subscribes to retained + live MQTT messages (payload format
`<value>|<unix-epoch-seconds>`) and renders them as live-updating panels
— built for setups that already publish HA sensor state to MQTT on a fixed
topic tree (`<topic_prefix>/<slug>`). Groups alternate across two columns
of compact, btop-style bordered panels, sized to fit a standard 80x24
terminal without needing to resize the window.

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
  - `kind` — `temp` / `gauge` (numeric, scaled + unit-suffixed), `counter`
    (scaled cumulative value, e.g. a Wh-native energy meter shown in kWh),
    or `enum` (colored status text, e.g. a lock or alarm state).
  - `display` — `standard` (default: a compact figure, no graph — not every
    sensor needs one), `inline_graph` (adds a sparkline beside the value),
    or `graph` (a taller standalone trend graph below the value, btop-CPU-box
    style — reserve this for one or two sensors you actually want to watch
    trend, since it costs the most vertical space).
  - `label` — display name (defaults to `slug`).
  - `unit` — suffix appended to the value, e.g. `"F"` or `" PSI"` (include
    your own leading space if you want one).
  - `scale` — multiplier applied before display (e.g. `0.001` to show a
    Wh-native sensor in kWh). `temp`/`gauge`/`counter` only.
  - `good` / `bad` — lists of string values that render green / red for
    `enum` sensors; anything else renders yellow.
  - `group_as` — sensors sharing the same key collapse into a single "All
    closed" / "OPEN: <labels>" line (e.g. multiple garage door sensors).
  - `layout: grid` on a group arranges its sensors in a compact 2-column
    grid of merged "label value" cells instead of one per line (handy
    for a dozen+ temperature sensors).

**Keep your real config out of version control** if you fork/publish this
repo — it will contain your household's entity layout and MQTT
credentials. `config.yaml` is already gitignored.

## Run

```bash
hatop
```

`q` or `Ctrl+Q` quits.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```
