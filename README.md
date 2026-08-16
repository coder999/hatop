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

## Publishing from Home Assistant

hatop doesn't care how `<topic_prefix>/<slug>` gets populated — any
publisher that writes `<value>|<unix-epoch-seconds>` retained messages
works. A common setup is a single HA automation that publishes tagged
entities' state to MQTT. Two things matter if you build one:

**Filter at the trigger, not inside the action.** It's tempting to
trigger on the raw `state_changed` event system-wide and filter down to
your tagged entities inside the automation's action — but that means
the automation *runs* (and queues) once per state change for every
entity in your house, not just the ones you care about. On a system
with any background chatter (zigbee, HomeKit, etc.) this can overrun
the automation's run queue continuously, which is enough sustained load
to starve Home Assistant's recorder mid-backup. Use `platform: state`
with an explicit `entity_id:` list so the trigger itself only fires for
entities you're actually publishing.

**Throttle high-churn sensors.** Not every sensor needs to publish the
instant its raw value changes — a temperature reading updating once a
minute is plenty, while a lock or alarm state changing instantly
matters. Split high-frequency, low-urgency sensors (temps, humidity)
onto their own `time_pattern` trigger that batch-publishes current
state on an interval, and reserve immediate on-change publishing for
the ones where it counts.

Example automation (Home Assistant YAML), adjust the `entity_id:` lists
to your setup:

```yaml
- alias: Publish sensors to MQTT
  triggers:
    - platform: state
      id: on_change
      entity_id:
        - lock.front_door
        - binary_sensor.water_leak
    - platform: time_pattern
      id: slow_tick
      minutes: /1
  actions:
    - choose:
        - conditions:
            - condition: trigger
              id: on_change
          sequence:
            - data:
                topic: "myhouse/ha/{{ trigger.entity_id.split('.')[1] }}"
                payload: "{{ trigger.to_state.state }}|{{ as_timestamp(now()) | int }}"
                retain: true
              action: mqtt.publish
        - conditions:
            - condition: trigger
              id: slow_tick
          sequence:
            - repeat:
                for_each:
                  - sensor.outside_temp
                  - sensor.living_room_temp
                sequence:
                  - data:
                      topic: "myhouse/ha/{{ repeat.item.split('.')[1] }}"
                      payload: "{{ states(repeat.item) }}|{{ as_timestamp(now()) | int }}"
                      retain: true
                    action: mqtt.publish
```

This intentionally keeps slug derivation simple (the entity_id's object
id) rather than something dynamic like an HA label lookup — pick
whatever mapping fits your setup, just make sure it can't fire for
entities outside your published set.

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
