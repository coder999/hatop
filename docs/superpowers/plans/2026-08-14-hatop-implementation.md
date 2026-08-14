# hatop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `hatop`, a btop-style live terminal dashboard that shows Home
Assistant sensor data streamed over MQTT, packaged as a pip-installable
`hatop` console command, and deploy it on nexus with the real 25-entity
household config.

**Architecture:** A background thread runs `paho-mqtt`'s network loop,
subscribed to `<topic_prefix>/#` (retained messages deliver current state
immediately on subscribe, then live updates stream in). Parsed
`(slug, value, ts)` tuples and connection-status strings are pushed onto
plain `queue.Queue` objects. A Textual `App` drains those queues on a 1s
timer and updates per-sensor widgets — no `call_from_thread` needed, since
`queue.Queue` is itself thread-safe for cross-thread hand-off. Entity
metadata (label/unit/kind/group) is entirely config-driven, never hardcoded.

**Tech Stack:** Python 3.10+, Textual (TUI), paho-mqtt 2.x (MQTT client),
PyYAML (config), pytest + pytest-asyncio (tests).

**Spec:** `docs/superpowers/specs/2026-08-14-hatop-design.md`

## Global Constraints

- Stack is Python + Textual + paho-mqtt + pyyaml — no other UI/MQTT/config
  libraries.
- Packaged as a pip-installable console script (`hatop` command via
  `[project.scripts]`), not a venv-wrapper shell script.
- MQTT payload wire format is `<value>|<unix-epoch-seconds-published>`,
  unchanged from `ha_summary`.
- Defaults: `stale_seconds: 21600` (6h), `sparkline_points: 120`.
- The GitHub repo (`github.com/coder999/hatop`, public) ships no
  household-specific data. The real entity list, labels, and MQTT
  credentials live only at `~/.config/hatop/config.yaml` on the deploy
  machine, gitignored, never committed.
- Live subscription only — subscribe to `<topic_prefix>/#` and react to
  messages; no periodic re-poll of the broker.
- TDD: pure logic (config parsing, state/staleness/sparkline windowing,
  MQTT message dispatch) gets full unit-test coverage written before the
  implementation, per task. The Textual UI layer gets light
  `run_test()`/Pilot-based smoke tests, not exhaustive coverage.
- Never print or log MQTT credentials (host/user/pass) to any transcript,
  file, or terminal output at any point, including during deployment.

---

## Task 1: Project scaffolding & packaging

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `LICENSE`
- Create: `README.md`
- Create: `config.example.yaml`
- Create: `src/hatop/__init__.py`
- Create: `src/hatop/__main__.py`
- Test: `tests/test_smoke.py`

**Interfaces:**
- Produces: `hatop.__main__.main() -> None` (stub for now; rewired to launch
  the real app in Task 7). Console script `hatop` invokes it.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "hatop"
version = "0.1.0"
description = "btop-style live terminal dashboard for Home Assistant sensor data over MQTT"
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
dependencies = [
    "textual>=0.60",
    "paho-mqtt>=2.1",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]

[project.scripts]
hatop = "hatop.__main__:main"

[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create `.gitignore`**

```
__pycache__/
*.pyc
.venv/
*.egg-info/
build/
dist/
.pytest_cache/
config.yaml
```

- [ ] **Step 3: Create `LICENSE`**

```
MIT License

Copyright (c) 2026 Mark Tuttle

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to
deal in the Software without restriction, including without limitation the
rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
sell copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
```

- [ ] **Step 4: Create a minimal `README.md` stub** (replaced fully in Task 7)

```markdown
# hatop

A btop-style live terminal dashboard for Home Assistant sensor data
streamed over MQTT.

**Status:** under construction — see `docs/superpowers/plans/` for the
implementation plan.
```

- [ ] **Step 5: Create `config.example.yaml`**

Generic, safe-to-publish example covering every `kind`:

```yaml
mqtt:
  host: 192.168.1.10
  port: 1883
  username: hatop
  password: "change-me"
  topic_prefix: "myhouse/ha"

# Shown once every 6h without an update, values are marked stale.
stale_seconds: 21600

# Sparkline history length per numeric sensor (in-memory only).
sparkline_points: 120

groups:
  - name: Temperatures
    layout: grid          # arrange sensors in a 3-column grid
    sensors:
      - {slug: living_room_temp, label: "Living Rm", kind: temp, unit: "F"}
      - {slug: outside_temp, label: Weather, kind: temp, unit: "F"}

  - name: Water
    sensors:
      - {slug: water_pressure, label: "Water Pressure", kind: gauge, unit: " PSI"}
      - {slug: water_usage_today, label: "Water Usage Today", kind: gauge, unit: " gal"}

  - name: Energy
    sensors:
      - {slug: home_load, label: "Home Load", kind: gauge, unit: " W"}
      # HA commonly reports cumulative energy sensors in Wh; scale converts to kWh for display.
      - {slug: energy_cumulative, label: "Cumulative Use", kind: counter, unit: " kWh", scale: 0.001}

  - name: Security
    sensors:
      - {slug: alarm_state, label: "Security System", kind: enum, good: [disarmed], bad: [triggered]}
      - {slug: front_door_lock, label: "Front Door Lock", kind: enum, good: [locked]}
      # Sensors sharing group_as collapse into one "All closed" / "OPEN: ..." line.
      - {slug: garage_door_left, label: Left, kind: enum, good: [closed], group_as: garage_doors}
      - {slug: garage_door_right, label: Right, kind: enum, good: [closed], group_as: garage_doors}
```

- [ ] **Step 6: Create `src/hatop/__init__.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 7: Create `src/hatop/__main__.py` stub**

```python
def main() -> None:
    print("hatop: dashboard not yet implemented (scaffold)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 8: Write the smoke test**

```python
# tests/test_smoke.py
from hatop.__main__ import main


def test_main_runs_without_error(capsys):
    main()
    captured = capsys.readouterr()
    assert "hatop" in captured.out
```

- [ ] **Step 9: Create the venv, install editable with dev extras, run tests**

```bash
cd /home/mark/projects/hatop
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -v
```

Expected: 1 passed (`test_main_runs_without_error`).

- [ ] **Step 10: Verify the console script is wired up**

```bash
.venv/bin/hatop
```

Expected output: `hatop: dashboard not yet implemented (scaffold)`

- [ ] **Step 11: Commit**

```bash
git add pyproject.toml .gitignore LICENSE README.md config.example.yaml \
        src/hatop/__init__.py src/hatop/__main__.py tests/test_smoke.py
git commit -m "Scaffold hatop package with console-script entry point

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 2: Config loader

**Files:**
- Create: `src/hatop/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `HatopConfigError(Exception)`; dataclasses `MqttConfig`,
  `SensorConfig`, `GroupConfig`, `HatopConfig`; functions
  `default_config_path() -> Path` and
  `load_config(path: Path | None = None) -> HatopConfig`.
- `SensorConfig` fields: `slug: str`, `kind: str`, `label: str = ""`
  (defaults to `slug` if empty), `unit: str = ""`, `scale: float = 1.0`,
  `good: tuple[str, ...] = ()`, `bad: tuple[str, ...] = ()`,
  `group_as: str | None = None`.
- `GroupConfig` fields: `name: str`, `sensors: list[SensorConfig]`,
  `layout: str = "list"`.
- `HatopConfig` fields: `mqtt: MqttConfig`, `groups: list[GroupConfig]`,
  `stale_seconds: int = 21600`, `sparkline_points: int = 120`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config.py
from pathlib import Path

import pytest

from hatop.config import HatopConfigError, load_config


def write_config(tmp_path: Path, text: str) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(text)
    return config_path


VALID_CONFIG = """
mqtt:
  host: 192.168.1.10
  username: nexus
  password: secret
groups:
  - name: Temperatures
    layout: grid
    sensors:
      - {slug: weather_temp, label: Weather, kind: temp, unit: "F"}
  - name: Security
    sensors:
      - {slug: alarm_state, label: Security System, kind: enum, good: [disarmed], bad: [triggered]}
"""


def test_load_valid_config_populates_expected_fields(tmp_path):
    config_path = write_config(tmp_path, VALID_CONFIG)

    config = load_config(config_path)

    assert config.mqtt.host == "192.168.1.10"
    assert config.mqtt.port == 1883
    assert config.mqtt.topic_prefix == "nexus/ha"
    assert config.stale_seconds == 21600
    assert config.sparkline_points == 120
    assert len(config.groups) == 2
    assert config.groups[0].name == "Temperatures"
    assert config.groups[0].layout == "grid"
    assert config.groups[0].sensors[0].slug == "weather_temp"
    assert config.groups[1].sensors[0].good == ("disarmed",)


def test_missing_config_file_raises_clear_error(tmp_path):
    missing_path = tmp_path / "does-not-exist.yaml"

    with pytest.raises(HatopConfigError, match="cannot read config"):
        load_config(missing_path)


def test_malformed_yaml_raises_clear_error(tmp_path):
    config_path = write_config(tmp_path, "mqtt: [this is not: valid: yaml")

    with pytest.raises(HatopConfigError, match="invalid YAML"):
        load_config(config_path)


def test_missing_mqtt_section_raises_error(tmp_path):
    config_path = write_config(tmp_path, "groups: []\n")

    with pytest.raises(HatopConfigError, match="missing required 'mqtt' section"):
        load_config(config_path)


def test_missing_required_mqtt_field_raises_error(tmp_path):
    config_path = write_config(tmp_path, "mqtt:\n  host: 192.168.1.10\ngroups: []\n")

    with pytest.raises(HatopConfigError, match="missing required field 'username'"):
        load_config(config_path)


def test_missing_groups_raises_error(tmp_path):
    config_path = write_config(
        tmp_path, "mqtt:\n  host: h\n  username: u\n  password: p\n"
    )

    with pytest.raises(HatopConfigError, match="at least one group"):
        load_config(config_path)


def test_unknown_sensor_kind_raises_error(tmp_path):
    config_path = write_config(
        tmp_path,
        """
mqtt:
  host: 192.168.1.10
  username: nexus
  password: secret
groups:
  - name: Bogus
    sensors:
      - {slug: thing, kind: not_a_real_kind}
""",
    )

    with pytest.raises(HatopConfigError, match="unknown kind"):
        load_config(config_path)


def test_sensor_label_defaults_to_slug(tmp_path):
    config_path = write_config(
        tmp_path,
        """
mqtt:
  host: 192.168.1.10
  username: nexus
  password: secret
groups:
  - name: Group
    sensors:
      - {slug: some_slug, kind: gauge}
""",
    )

    config = load_config(config_path)

    assert config.groups[0].sensors[0].label == "some_slug"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_config.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hatop.config'` (or
`ImportError`).

- [ ] **Step 3: Write the implementation**

```python
# src/hatop/config.py
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


class HatopConfigError(Exception):
    """Raised when the hatop config file is missing or invalid."""


@dataclass
class MqttConfig:
    host: str
    port: int = 1883
    username: str | None = None
    password: str | None = None
    topic_prefix: str = "nexus/ha"


@dataclass
class SensorConfig:
    slug: str
    kind: str  # "temp" | "gauge" | "counter" | "enum"
    label: str = ""
    unit: str = ""
    scale: float = 1.0
    good: tuple[str, ...] = ()
    bad: tuple[str, ...] = ()
    group_as: str | None = None

    def __post_init__(self) -> None:
        if not self.label:
            self.label = self.slug


@dataclass
class GroupConfig:
    name: str
    sensors: list[SensorConfig]
    layout: str = "list"  # "list" | "grid"


@dataclass
class HatopConfig:
    mqtt: MqttConfig
    groups: list[GroupConfig]
    stale_seconds: int = 21600
    sparkline_points: int = 120


VALID_KINDS = ("temp", "gauge", "counter", "enum")


def default_config_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "hatop" / "config.yaml"


def load_config(path: Path | None = None) -> HatopConfig:
    config_path = path or default_config_path()
    if not config_path.is_file():
        raise HatopConfigError(
            f"hatop: cannot read config at {config_path}\n"
            "Create one based on config.example.yaml in the hatop repo."
        )

    try:
        raw = yaml.safe_load(config_path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise HatopConfigError(f"hatop: invalid YAML in {config_path}: {exc}") from exc

    return _parse_config(raw, config_path)


def _parse_config(raw: dict, config_path: Path) -> HatopConfig:
    if "mqtt" not in raw:
        raise HatopConfigError(f"hatop: {config_path} is missing required 'mqtt' section")
    mqtt_raw = raw["mqtt"]
    for required in ("host", "username", "password"):
        if required not in mqtt_raw:
            raise HatopConfigError(
                f"hatop: {config_path} 'mqtt' section is missing required field '{required}'"
            )
    mqtt = MqttConfig(
        host=mqtt_raw["host"],
        port=int(mqtt_raw.get("port", 1883)),
        username=mqtt_raw["username"],
        password=mqtt_raw["password"],
        topic_prefix=mqtt_raw.get("topic_prefix", "nexus/ha"),
    )

    if not raw.get("groups"):
        raise HatopConfigError(f"hatop: {config_path} must define at least one group under 'groups'")

    groups: list[GroupConfig] = []
    for group_raw in raw["groups"]:
        if "name" not in group_raw or "sensors" not in group_raw:
            raise HatopConfigError(f"hatop: {config_path} has a group missing 'name' or 'sensors'")
        sensors: list[SensorConfig] = []
        for sensor_raw in group_raw["sensors"]:
            if "slug" not in sensor_raw or "kind" not in sensor_raw:
                raise HatopConfigError(
                    f"hatop: {config_path} has a sensor missing 'slug' or 'kind' "
                    f"in group '{group_raw['name']}'"
                )
            if sensor_raw["kind"] not in VALID_KINDS:
                raise HatopConfigError(
                    f"hatop: {config_path} sensor '{sensor_raw['slug']}' has unknown "
                    f"kind '{sensor_raw['kind']}' (must be one of {VALID_KINDS})"
                )
            sensors.append(
                SensorConfig(
                    slug=sensor_raw["slug"],
                    kind=sensor_raw["kind"],
                    label=sensor_raw.get("label", ""),
                    unit=sensor_raw.get("unit", ""),
                    scale=float(sensor_raw.get("scale", 1.0)),
                    good=tuple(sensor_raw.get("good", ())),
                    bad=tuple(sensor_raw.get("bad", ())),
                    group_as=sensor_raw.get("group_as"),
                )
            )
        groups.append(
            GroupConfig(
                name=group_raw["name"],
                sensors=sensors,
                layout=group_raw.get("layout", "list"),
            )
        )

    return HatopConfig(
        mqtt=mqtt,
        groups=groups,
        stale_seconds=int(raw.get("stale_seconds", 21600)),
        sparkline_points=int(raw.get("sparkline_points", 120)),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_config.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/hatop/config.py tests/test_config.py
git commit -m "Add hatop config loader with schema validation

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 3: State model

**Files:**
- Create: `src/hatop/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Consumes: `hatop.config.SensorConfig` (Task 2).
- Produces: `PayloadParseError(Exception)`;
  `parse_payload(payload: str) -> tuple[str, int]`;
  `SensorState` dataclass with fields `slug: str`, `value: str | None = None`,
  `ts: int | None = None`, `history: deque[float]`, and method
  `is_stale(self, now: int, stale_seconds: int) -> bool`;
  `StateStore` class with `__init__(self, sparkline_points: int = 120)`,
  `update(self, slug: str, value: str, ts: int) -> None`,
  `get(self, slug: str) -> SensorState`,
  `sparkline_values(self, slug: str) -> list[float]`;
  `collapse_group_status(sensors: list[SensorConfig], store: StateStore) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_state.py
import pytest

from hatop.config import SensorConfig
from hatop.state import (
    PayloadParseError,
    SensorState,
    StateStore,
    collapse_group_status,
    parse_payload,
)


def test_parse_payload_splits_value_and_timestamp():
    value, ts = parse_payload("72.3|1755100000")

    assert value == "72.3"
    assert ts == 1755100000


def test_parse_payload_rejects_missing_separator():
    with pytest.raises(PayloadParseError):
        parse_payload("72.3")


def test_parse_payload_rejects_non_integer_timestamp():
    with pytest.raises(PayloadParseError):
        parse_payload("72.3|not-a-number")


def test_sensor_state_not_stale_when_no_timestamp():
    state = SensorState(slug="x")

    assert state.is_stale(now=1000, stale_seconds=100) is False


def test_sensor_state_stale_boundary():
    state = SensorState(slug="x", value="1", ts=1000)

    assert state.is_stale(now=1099, stale_seconds=100) is False
    assert state.is_stale(now=1100, stale_seconds=100) is True


def test_state_store_update_and_get():
    store = StateStore()

    store.update("weather_temp", "72.3", 1755100000)
    state = store.get("weather_temp")

    assert state.value == "72.3"
    assert state.ts == 1755100000


def test_state_store_get_unknown_slug_returns_empty_state():
    store = StateStore()

    state = store.get("never_seen")

    assert state.value is None
    assert state.ts is None


def test_state_store_appends_numeric_history_for_sparkline():
    store = StateStore()

    store.update("weather_temp", "70", 1)
    store.update("weather_temp", "71", 2)
    store.update("weather_temp", "72", 3)

    assert store.sparkline_values("weather_temp") == [70.0, 71.0, 72.0]


def test_state_store_ignores_non_numeric_values_for_history():
    store = StateStore()

    store.update("lock_front_door", "locked", 1)

    assert store.sparkline_values("lock_front_door") == []


def test_state_store_sparkline_window_trims_to_configured_size():
    store = StateStore(sparkline_points=3)

    for i in range(5):
        store.update("weather_temp", str(i), i)

    assert store.sparkline_values("weather_temp") == [2.0, 3.0, 4.0]


def test_collapse_group_status_all_closed():
    store = StateStore()
    store.update("garage_door_south", "closed", 1)
    store.update("garage_door_north", "closed", 1)
    sensors = [
        SensorConfig(slug="garage_door_south", kind="enum", good=("closed",), group_as="garage_doors"),
        SensorConfig(slug="garage_door_north", kind="enum", good=("closed",), group_as="garage_doors"),
    ]

    assert collapse_group_status(sensors, store) == "All closed"


def test_collapse_group_status_reports_open_doors_by_label():
    store = StateStore()
    store.update("garage_door_south", "open", 1)
    store.update("garage_door_north", "closed", 1)
    sensors = [
        SensorConfig(slug="garage_door_south", label="South", kind="enum", good=("closed",), group_as="garage_doors"),
        SensorConfig(slug="garage_door_north", label="North", kind="enum", good=("closed",), group_as="garage_doors"),
    ]

    assert collapse_group_status(sensors, store) == "OPEN: South"


def test_collapse_group_status_ignores_sensors_with_no_data_yet():
    store = StateStore()
    sensors = [
        SensorConfig(slug="garage_door_south", kind="enum", good=("closed",), group_as="garage_doors"),
    ]

    assert collapse_group_status(sensors, store) == "All closed"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_state.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hatop.state'`.

- [ ] **Step 3: Write the implementation**

```python
# src/hatop/state.py
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from hatop.config import SensorConfig


class PayloadParseError(Exception):
    """Raised when an MQTT payload doesn't match the "<value>|<epoch>" format."""


def parse_payload(payload: str) -> tuple[str, int]:
    if "|" not in payload:
        raise PayloadParseError(f"payload missing '|' separator: {payload!r}")
    value, _, ts_str = payload.rpartition("|")
    try:
        ts = int(ts_str)
    except ValueError as exc:
        raise PayloadParseError(f"payload has non-integer timestamp: {payload!r}") from exc
    return value, ts


@dataclass
class SensorState:
    slug: str
    value: str | None = None
    ts: int | None = None
    history: deque[float] = field(default_factory=lambda: deque(maxlen=120))

    def is_stale(self, now: int, stale_seconds: int) -> bool:
        if self.ts is None:
            return False
        return (now - self.ts) >= stale_seconds


class StateStore:
    def __init__(self, sparkline_points: int = 120) -> None:
        self._sparkline_points = sparkline_points
        self._sensors: dict[str, SensorState] = {}

    def update(self, slug: str, value: str, ts: int) -> None:
        state = self._sensors.get(slug)
        if state is None:
            state = SensorState(slug=slug, history=deque(maxlen=self._sparkline_points))
            self._sensors[slug] = state
        state.value = value
        state.ts = ts
        try:
            state.history.append(float(value))
        except ValueError:
            pass  # non-numeric values (enum states) aren't graphed

    def get(self, slug: str) -> SensorState:
        state = self._sensors.get(slug)
        if state is None:
            return SensorState(slug=slug, history=deque(maxlen=self._sparkline_points))
        return state

    def sparkline_values(self, slug: str) -> list[float]:
        return list(self.get(slug).history)


def collapse_group_status(sensors: list[SensorConfig], store: StateStore) -> str:
    """Combine sensors sharing a group_as key into one ha_summary-style line."""
    open_labels = []
    for sensor in sensors:
        state = store.get(sensor.slug)
        if state.value is None:
            continue
        if sensor.good and state.value not in sensor.good:
            open_labels.append(sensor.label)
    if not open_labels:
        return "All closed"
    return "OPEN: " + ", ".join(open_labels)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_state.py -v
```

Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add src/hatop/state.py tests/test_state.py
git commit -m "Add hatop state model: payload parsing, staleness, sparkline history

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 4: MQTT client

**Files:**
- Create: `src/hatop/mqtt_client.py`
- Test: `tests/test_mqtt_client.py`

**Interfaces:**
- Consumes: `hatop.config.MqttConfig` (Task 2),
  `hatop.state.parse_payload`/`PayloadParseError` (Task 3).
- Produces: `MqttClient` class —
  `__init__(self, config: MqttConfig, on_update: Callable[[str, str, int], None], on_status: Callable[[str], None])`,
  `start(self) -> None`, `stop(self) -> None`. `on_update`/`on_status` are
  plain callables — Task 6 wires them to `queue.Queue.put`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_mqtt_client.py
from types import SimpleNamespace
from unittest.mock import MagicMock

from hatop.config import MqttConfig
from hatop.mqtt_client import MqttClient


def make_client(topic_prefix="nexus/ha"):
    config = MqttConfig(host="broker", username="u", password="p", topic_prefix=topic_prefix)
    updates = []
    statuses = []
    client = MqttClient(config, on_update=lambda *a: updates.append(a), on_status=lambda s: statuses.append(s))
    return client, updates, statuses


def test_handle_message_dispatches_parsed_slug_value_timestamp():
    client, updates, _ = make_client()
    message = SimpleNamespace(topic="nexus/ha/weather_temp", payload=b"72.3|1755100000")

    client._handle_message(MagicMock(), None, message)

    assert updates == [("weather_temp", "72.3", 1755100000)]


def test_handle_message_ignores_topics_outside_prefix():
    client, updates, _ = make_client()
    message = SimpleNamespace(topic="other/topic", payload=b"1|1")

    client._handle_message(MagicMock(), None, message)

    assert updates == []


def test_handle_message_ignores_malformed_payload_without_raising():
    client, updates, _ = make_client()
    message = SimpleNamespace(topic="nexus/ha/weather_temp", payload=b"not-a-valid-payload")

    client._handle_message(MagicMock(), None, message)

    assert updates == []


def test_handle_connect_subscribes_and_reports_connected():
    client, _, statuses = make_client()
    fake_mqtt_client = MagicMock()

    client._handle_connect(fake_mqtt_client, None, {}, 0, None)

    fake_mqtt_client.subscribe.assert_called_once_with("nexus/ha/#")
    assert statuses == ["connected"]


def test_handle_connect_reports_failure_reason(monkeypatch=None):
    client, _, statuses = make_client()
    fake_mqtt_client = MagicMock()

    client._handle_connect(fake_mqtt_client, None, {}, 5, None)

    fake_mqtt_client.subscribe.assert_not_called()
    assert statuses == ["connect failed: 5"]


def test_handle_disconnect_reports_reconnecting():
    client, _, statuses = make_client()

    client._handle_disconnect(MagicMock(), None, {}, 1, None)

    assert statuses == ["reconnecting"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_mqtt_client.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hatop.mqtt_client'`.

- [ ] **Step 3: Write the implementation**

```python
# src/hatop/mqtt_client.py
from __future__ import annotations

import logging
from typing import Callable

import paho.mqtt.client as mqtt

from hatop.config import MqttConfig
from hatop.state import PayloadParseError, parse_payload

logger = logging.getLogger(__name__)

UpdateCallback = Callable[[str, str, int], None]
StatusCallback = Callable[[str], None]


class MqttClient:
    """Background MQTT subscriber. Wraps paho-mqtt's network loop in its own
    thread and dispatches parsed (slug, value, ts) updates to on_update, and
    connection-state strings ("connected" | "reconnecting" | "connect failed: <code>")
    to on_status. Callbacks may be invoked from the paho-mqtt network thread;
    callers must use a thread-safe hand-off (e.g. queue.Queue.put).
    """

    def __init__(
        self,
        config: MqttConfig,
        on_update: UpdateCallback,
        on_status: StatusCallback,
    ) -> None:
        self._config = config
        self._on_update = on_update
        self._on_status = on_status
        self._client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        if config.username:
            self._client.username_pw_set(config.username, config.password)
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.on_connect = self._handle_connect
        self._client.on_disconnect = self._handle_disconnect
        self._client.on_message = self._handle_message

    def start(self) -> None:
        self._client.connect(self._config.host, self._config.port)
        self._client.loop_start()

    def stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    def _handle_connect(self, client, userdata, connect_flags, reason_code, properties) -> None:
        if reason_code == 0:
            client.subscribe(f"{self._config.topic_prefix}/#")
            self._on_status("connected")
        else:
            self._on_status(f"connect failed: {reason_code}")

    def _handle_disconnect(self, client, userdata, disconnect_flags, reason_code, properties) -> None:
        self._on_status("reconnecting")

    def _handle_message(self, client, userdata, message) -> None:
        prefix = f"{self._config.topic_prefix}/"
        if not message.topic.startswith(prefix):
            return
        slug = message.topic[len(prefix):]
        try:
            value, ts = parse_payload(message.payload.decode("utf-8"))
        except PayloadParseError:
            logger.warning("hatop: ignoring malformed payload on %s", message.topic)
            return
        self._on_update(slug, value, ts)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_mqtt_client.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/hatop/mqtt_client.py tests/test_mqtt_client.py
git commit -m "Add hatop MQTT client wrapper around paho-mqtt

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 5: Widgets

**Files:**
- Create: `src/hatop/widgets.py`
- Test: `tests/test_widgets.py`

**Interfaces:**
- Consumes: `hatop.config.{GroupConfig, SensorConfig}` (Task 2),
  `hatop.state.{SensorState, StateStore, collapse_group_status}` (Task 3).
- Produces: functions `format_value(sensor: SensorConfig, state: SensorState) -> str`,
  `status_color(sensor: SensorConfig, state: SensorState) -> str`; Textual
  widget classes `SensorRow(Horizontal)` — `__init__(self, sensor: SensorConfig)`,
  mounted with `id=f"sensor-{sensor.slug}"`, method
  `update_state(self, state: SensorState, stale: bool) -> None` — and
  `GroupPanel(Vertical)` — `__init__(self, group: GroupConfig)`, method
  `refresh_state(self, store: StateStore, now: int, stale_seconds: int) -> None`.
  Group-as sensors' combined status is a `Static` with `id=f"group-{group_as}"`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_widgets.py
import pytest
from textual.app import App, ComposeResult
from textual.containers import Grid

from hatop.config import GroupConfig, SensorConfig
from hatop.state import StateStore
from hatop.widgets import GroupPanel


class PanelHarness(App):
    def __init__(self, group: GroupConfig) -> None:
        super().__init__()
        self.panel = GroupPanel(group)

    def compose(self) -> ComposeResult:
        yield self.panel


async def test_sensor_row_shows_na_before_any_data():
    group = GroupConfig(
        name="Temperatures",
        sensors=[SensorConfig(slug="weather_temp", label="Weather", kind="temp", unit="F")],
    )
    app = PanelHarness(group)

    async with app.run_test():
        value = app.query_one("#sensor-weather_temp #value")
        assert "n/a" in str(value.renderable)


async def test_sensor_row_shows_updated_value_and_sparkline():
    group = GroupConfig(
        name="Temperatures",
        sensors=[SensorConfig(slug="weather_temp", label="Weather", kind="temp", unit="F")],
    )
    app = PanelHarness(group)
    store = StateStore()
    store.update("weather_temp", "72.3", 1000)

    async with app.run_test():
        app.panel.refresh_state(store, now=1000, stale_seconds=21600)
        value = app.query_one("#sensor-weather_temp #value")
        assert "72.3F" in str(value.renderable)
        spark = app.query_one("#sensor-weather_temp #spark")
        assert spark.data == [72.3]


async def test_sensor_row_marks_stale_values():
    group = GroupConfig(
        name="Temperatures",
        sensors=[SensorConfig(slug="weather_temp", label="Weather", kind="temp", unit="F")],
    )
    app = PanelHarness(group)
    store = StateStore()
    store.update("weather_temp", "72.3", 0)

    async with app.run_test():
        app.panel.refresh_state(store, now=99999, stale_seconds=100)
        value = app.query_one("#sensor-weather_temp #value")
        assert "*" in str(value.renderable)


async def test_counter_kind_has_no_sparkline():
    group = GroupConfig(
        name="Energy",
        sensors=[SensorConfig(slug="energy_cumulative", label="Cumulative", kind="counter", unit=" kWh", scale=0.001)],
    )
    app = PanelHarness(group)
    store = StateStore()
    store.update("energy_cumulative", "34962668", 1000)

    async with app.run_test():
        app.panel.refresh_state(store, now=1000, stale_seconds=21600)
        value = app.query_one("#sensor-energy_cumulative #value")
        assert "34962.7 kWh" in str(value.renderable)
        assert len(app.query("#sensor-energy_cumulative #spark")) == 0


async def test_group_as_sensors_collapse_to_all_closed():
    group = GroupConfig(
        name="Security",
        sensors=[
            SensorConfig(slug="garage_door_south", label="South", kind="enum", good=("closed",), group_as="garage_doors"),
            SensorConfig(slug="garage_door_north", label="North", kind="enum", good=("closed",), group_as="garage_doors"),
        ],
    )
    app = PanelHarness(group)
    store = StateStore()
    store.update("garage_door_south", "closed", 1)
    store.update("garage_door_north", "closed", 1)

    async with app.run_test():
        app.panel.refresh_state(store, now=1, stale_seconds=21600)
        status = app.query_one("#group-garage_doors")
        assert "All closed" in str(status.renderable)


async def test_grid_layout_group_mounts_grid_container():
    group = GroupConfig(
        name="Temperatures",
        layout="grid",
        sensors=[SensorConfig(slug="weather_temp", label="Weather", kind="temp", unit="F")],
    )
    app = PanelHarness(group)

    async with app.run_test():
        assert app.query_one(GroupPanel).query_one(Grid) is not None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_widgets.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hatop.widgets'`.

- [ ] **Step 3: Write the implementation**

```python
# src/hatop/widgets.py
from __future__ import annotations

from textual.containers import Grid, Horizontal, Vertical
from textual.widgets import Label, Sparkline, Static

from hatop.config import GroupConfig, SensorConfig
from hatop.state import SensorState, StateStore, collapse_group_status


def format_value(sensor: SensorConfig, state: SensorState) -> str:
    if state.value is None:
        return "n/a"
    if sensor.kind in ("temp", "gauge", "counter"):
        try:
            number = float(state.value) * sensor.scale
        except ValueError:
            return f"{state.value}{sensor.unit}"
        text = f"{number:.1f}".rstrip("0").rstrip(".")
        return f"{text}{sensor.unit}"
    return state.value


def status_color(sensor: SensorConfig, state: SensorState) -> str:
    if state.value is None:
        return "grey50"
    if sensor.good and state.value in sensor.good:
        return "green"
    if sensor.bad and state.value in sensor.bad:
        return "red"
    if sensor.good or sensor.bad:
        return "yellow"
    return "white"


class SensorRow(Horizontal):
    """One sensor: 'Label: value' (+ sparkline for temp/gauge kinds)."""

    DEFAULT_CSS = """
    SensorRow { height: 1; }
    SensorRow > Label { width: 20; }
    SensorRow > Static { width: 14; }
    SensorRow > Sparkline { width: 1fr; }
    """

    def __init__(self, sensor: SensorConfig) -> None:
        super().__init__(id=f"sensor-{sensor.slug}")
        self.sensor = sensor
        self._show_sparkline = sensor.kind in ("temp", "gauge")

    def compose(self):
        yield Label(f"{self.sensor.label}:")
        yield Static(id="value")
        if self._show_sparkline:
            yield Sparkline([], id="spark")

    def update_state(self, state: SensorState, stale: bool) -> None:
        text = format_value(self.sensor, state)
        if stale:
            text += " *"
        color = status_color(self.sensor, state)
        self.query_one("#value", Static).update(f"[{color}]{text}[/{color}]")
        if self._show_sparkline:
            self.query_one("#spark", Sparkline).data = list(state.history)


class GroupPanel(Vertical):
    """One config group (e.g. 'Temperatures'): title + its sensor rows.
    Sensors sharing a group_as key collapse into a single combined row."""

    DEFAULT_CSS = """
    GroupPanel { border: round $primary; padding: 0 1; margin-bottom: 1; }
    GroupPanel > Label.title { text-style: bold; }
    GroupPanel > Grid.rows { grid-size: 3; grid-gutter: 0 2; }
    """

    def __init__(self, group: GroupConfig) -> None:
        super().__init__()
        self.group = group

    def compose(self):
        yield Label(self.group.name, classes="title")
        container_cls = Grid if self.group.layout == "grid" else Vertical
        with container_cls(classes="rows"):
            seen_group_as: set[str] = set()
            for sensor in self.group.sensors:
                if sensor.group_as:
                    if sensor.group_as in seen_group_as:
                        continue
                    seen_group_as.add(sensor.group_as)
                    yield Static(id=f"group-{sensor.group_as}")
                else:
                    yield SensorRow(sensor)

    def refresh_state(self, store: StateStore, now: int, stale_seconds: int) -> None:
        rendered_group_as: set[str] = set()
        for sensor in self.group.sensors:
            if sensor.group_as:
                if sensor.group_as in rendered_group_as:
                    continue
                rendered_group_as.add(sensor.group_as)
                siblings = [s for s in self.group.sensors if s.group_as == sensor.group_as]
                status = collapse_group_status(siblings, store)
                color = "green" if status == "All closed" else "red"
                self.query_one(f"#group-{sensor.group_as}", Static).update(
                    f"[{color}]{status}[/{color}]"
                )
            else:
                state = store.get(sensor.slug)
                stale = state.is_stale(now, stale_seconds)
                self.query_one(f"#sensor-{sensor.slug}", SensorRow).update_state(state, stale)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_widgets.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/hatop/widgets.py tests/test_widgets.py
git commit -m "Add hatop Textual widgets: SensorRow and GroupPanel

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 6: HatopApp

**Files:**
- Create: `src/hatop/app.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `hatop.config.{HatopConfig, load_config}` (Task 2),
  `hatop.state.StateStore` (Task 3), `hatop.mqtt_client.MqttClient` (Task 4),
  `hatop.widgets.GroupPanel` (Task 5).
- Produces: `HatopApp(App)` —
  `__init__(self, config: HatopConfig | None = None, mqtt_client_factory=MqttClient)`.
  If `config` is `None`, calls `load_config()` (may raise `HatopConfigError`
  — left to the caller, i.e. `__main__.py`, to catch). `mqtt_client_factory`
  is injectable for tests; called as
  `mqtt_client_factory(mqtt_config, on_update=..., on_status=...)` and must
  return an object with `.start()`/`.stop()`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_app.py
from hatop.app import HatopApp
from hatop.config import GroupConfig, HatopConfig, MqttConfig, SensorConfig


class FakeMqttClient:
    def __init__(self, config, on_update, on_status):
        self.config = config
        self.on_update = on_update
        self.on_status = on_status
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True
        self.on_status("connected")

    def stop(self):
        self.stopped = True


def make_config() -> HatopConfig:
    return HatopConfig(
        mqtt=MqttConfig(host="broker", username="u", password="p"),
        groups=[
            GroupConfig(
                name="Temperatures",
                sensors=[SensorConfig(slug="weather_temp", label="Weather", kind="temp", unit="F")],
            )
        ],
    )


async def test_app_shows_connected_status_after_mqtt_connects():
    app = HatopApp(config=make_config(), mqtt_client_factory=FakeMqttClient)

    async with app.run_test():
        app._tick()
        status = app.query_one("#connection-status")
        assert "connected" in str(status.renderable)


async def test_app_updates_sensor_row_when_mqtt_update_arrives():
    app = HatopApp(config=make_config(), mqtt_client_factory=FakeMqttClient)

    async with app.run_test():
        app._updates.put(("weather_temp", "72.3", 1000))
        app._tick()
        value = app.query_one("#sensor-weather_temp #value")
        assert "72.3F" in str(value.renderable)


async def test_app_stops_mqtt_client_on_unmount():
    app = HatopApp(config=make_config(), mqtt_client_factory=FakeMqttClient)

    async with app.run_test():
        mqtt_client = app._mqtt_client
        assert mqtt_client.started is True

    assert mqtt_client.stopped is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_app.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hatop.app'`.

- [ ] **Step 3: Write the implementation**

```python
# src/hatop/app.py
from __future__ import annotations

import queue
import time

from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, Static

from hatop.config import HatopConfig, load_config
from hatop.mqtt_client import MqttClient
from hatop.widgets import GroupPanel
from hatop.state import StateStore


class HatopApp(App):
    """btop-style live dashboard for Home Assistant sensors over MQTT."""

    CSS = """
    #connection-status { dock: top; height: 1; padding: 0 1; }
    """

    BINDINGS = [("q", "quit", "Quit")]

    REFRESH_INTERVAL = 1.0

    def __init__(self, config: HatopConfig | None = None, mqtt_client_factory=MqttClient) -> None:
        super().__init__()
        self.config = config or load_config()
        self.store = StateStore(sparkline_points=self.config.sparkline_points)
        self._mqtt_client_factory = mqtt_client_factory
        self._mqtt_client = None
        self._panels: list[GroupPanel] = []
        self._updates: "queue.Queue[tuple[str, str, int]]" = queue.Queue()
        self._statuses: "queue.Queue[str]" = queue.Queue()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("MQTT: connecting...", id="connection-status")
        with VerticalScroll(id="panels"):
            for group in self.config.groups:
                panel = GroupPanel(group)
                self._panels.append(panel)
                yield panel
        yield Footer()

    def on_mount(self) -> None:
        self._mqtt_client = self._mqtt_client_factory(
            self.config.mqtt,
            on_update=lambda slug, value, ts: self._updates.put((slug, value, ts)),
            on_status=self._statuses.put,
        )
        self._mqtt_client.start()
        self.set_interval(self.REFRESH_INTERVAL, self._tick)

    def on_unmount(self) -> None:
        if self._mqtt_client is not None:
            self._mqtt_client.stop()

    def _tick(self) -> None:
        self._drain_queues()
        self._refresh_panels()

    def _drain_queues(self) -> None:
        while not self._updates.empty():
            slug, value, ts = self._updates.get_nowait()
            self.store.update(slug, value, ts)
        latest_status = None
        while not self._statuses.empty():
            latest_status = self._statuses.get_nowait()
        if latest_status is not None:
            self.query_one("#connection-status", Static).update(f"MQTT: {latest_status}")

    def _refresh_panels(self) -> None:
        now = int(time.time())
        for panel in self._panels:
            panel.refresh_state(self.store, now, self.config.stale_seconds)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_app.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Run the full test suite so far**

```bash
.venv/bin/pytest -v
```

Expected: all tests across `test_smoke.py`, `test_config.py`, `test_state.py`,
`test_mqtt_client.py`, `test_widgets.py`, `test_app.py` pass.

- [ ] **Step 6: Commit**

```bash
git add src/hatop/app.py tests/test_app.py
git commit -m "Add HatopApp: wires config, MQTT client, and panels together

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 7: Wire the real entry point, finalize docs

**Files:**
- Modify: `src/hatop/__main__.py`
- Modify: `README.md`
- Delete: `tests/test_smoke.py`

**Interfaces:**
- Consumes: `hatop.app.HatopApp`, `hatop.config.HatopConfigError` (Task 2).
- Produces: `hatop.__main__.main() -> None` — the real, final entry point.

- [ ] **Step 1: Rewrite `src/hatop/__main__.py`**

```python
from __future__ import annotations

import sys

from hatop.app import HatopApp
from hatop.config import HatopConfigError


def main() -> None:
    try:
        app = HatopApp()
    except HatopConfigError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
    app.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Delete the now-obsolete smoke test**

```bash
git rm tests/test_smoke.py
```

It asserted on the scaffold's placeholder print, which no longer exists;
`test_app.py` (Task 6) already covers `HatopApp` end-to-end with a fake MQTT
client, and `main()`'s config-error path is simple enough not to need a
dedicated test (it's a two-line try/except around a function already tested
in `test_config.py`).

- [ ] **Step 3: Run the full test suite**

```bash
.venv/bin/pytest -v
```

Expected: all tests pass (no more `test_smoke.py`).

- [ ] **Step 4: Write the final `README.md`**

```markdown
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
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Wire real entry point, finalize README, drop scaffold smoke test

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 8: Push to GitHub

**Files:** none (repository operation only)

- [ ] **Step 1: Push to the `coder999/hatop` remote**

```bash
cd /home/mark/projects/hatop
git push -u origin main
```

- [ ] **Step 2: Verify the push landed**

```bash
git log origin/main --oneline -1
gh repo view coder999/hatop --json defaultBranchRef,pushedAt
```

Expected: `origin/main` matches local `main`'s latest commit; `pushedAt` is
recent.

---

## Task 9: Deploy real config on nexus

**Files:**
- Create (outside repo, gitignored path): `~/.config/hatop/config.yaml`

This task installs `hatop` for real use on nexus and builds its config from
the household's actual 25 HA entities — the same set `ha_summary` already
tracks (see `/home/mark/projects/serverconfig/nexus.md`, "Login Banner +
MQTT + Home Assistant Summary"). MQTT credentials are read from
`/etc/nexus-ha-summary.conf` and are never printed to any output at any
step.

- [ ] **Step 1: Install hatop with pipx**

```bash
which pipx || sudo apt-get install -y pipx
pipx install /home/mark/projects/hatop
hash -r
which hatop
```

Expected: `pipx` reports `installed package hatop`, `which hatop` resolves
to `~/.local/bin/hatop`.

- [ ] **Step 2: Write `~/.config/hatop/config.yaml` from the real entity list**

This mirrors `ha_summary`'s groups exactly (11 temps, 4 water, 3 energy, 1
environment, 2 locks + 1 alarm + 3 garage doors = 25 entities). Broker
host/port/user/pass are substituted from `/etc/nexus-ha-summary.conf`
without ever being echoed to the terminal:

```bash
install -d -m 700 ~/.config/hatop
umask 177
sh -c '
. /etc/nexus-ha-summary.conf
cat > ~/.config/hatop/config.yaml <<YAML
mqtt:
  host: "$MQTT_HOST"
  port: $MQTT_PORT
  username: "$MQTT_USER"
  password: "$MQTT_PASS"
  topic_prefix: "nexus/ha"
stale_seconds: 21600
sparkline_points: 120
groups:
  - name: Temperatures
    layout: grid
    sensors:
      - {slug: weather_temp, label: Weather, kind: temp, unit: "F"}
      - {slug: garage_temp, label: Garage, kind: temp, unit: "F"}
      - {slug: living_room_temp, label: "Living Rm", kind: temp, unit: "F"}
      - {slug: dining_room_temp, label: "Dining Rm", kind: temp, unit: "F"}
      - {slug: attic_temp, label: Attic, kind: temp, unit: "F"}
      - {slug: bedroom_temp, label: Bedroom, kind: temp, unit: "F"}
      - {slug: guest_room2_temp, label: "Guest Rm 2", kind: temp, unit: "F"}
      - {slug: guest_room3_temp, label: "Guest Rm 3", kind: temp, unit: "F"}
      - {slug: guest_room_temp, label: "Guest Rm", kind: temp, unit: "F"}
      - {slug: garage_freezer_temp, label: "Garage Frz", kind: temp, unit: "F"}
      - {slug: water_heater_temp, label: "Wtr Heater", kind: temp, unit: "F"}
  - name: Water
    sensors:
      - {slug: home_water_pressure, label: "Home Water Pressure", kind: gauge, unit: " PSI"}
      - {slug: city_water_pressure, label: "City Water Pressure", kind: gauge, unit: " PSI"}
      - {slug: water_usage_today, label: "Water Usage Today", kind: gauge, unit: " gal"}
      - {slug: hot_water_usage_today, label: "Hot Water Usage Today", kind: gauge, unit: " gal"}
  - name: Energy
    sensors:
      - {slug: energy_load_home, label: "Home Load", kind: gauge, unit: " W"}
      - {slug: energy_load_server_rack, label: "Server Rack Load", kind: gauge, unit: " W"}
      - {slug: energy_cumulative, label: "Cumulative Use", kind: counter, unit: " kWh", scale: 0.001}
  - name: Environment
    sensors:
      - {slug: radon_basement, label: "Basement Radon", kind: gauge, unit: " pCi/L"}
  - name: Security
    sensors:
      - {slug: alarm_state, label: "Security System", kind: enum, good: [disarmed], bad: [triggered]}
      - {slug: lock_front_door, label: "Front Door Lock", kind: enum, good: [locked]}
      - {slug: lock_back_door, label: "Back Door Lock", kind: enum, good: [locked]}
      - {slug: garage_door_1, label: "Door 1", kind: enum, good: [closed], group_as: garage_doors}
      - {slug: garage_door_2, label: "Door 2", kind: enum, good: [closed], group_as: garage_doors}
      - {slug: garage_door_3, label: "Door 3", kind: enum, good: [closed], group_as: garage_doors}
YAML
'
chmod 600 ~/.config/hatop/config.yaml
```

- [ ] **Step 3: Verify the config file structure without printing secrets**

```bash
wc -l ~/.config/hatop/config.yaml
grep -c 'slug:' ~/.config/hatop/config.yaml
stat -c '%a %U:%G' ~/.config/hatop/config.yaml
```

Expected: `grep -c 'slug:'` reports `25`; `stat` reports `600 mark:mark`.

- [ ] **Step 4: Verify the config loads correctly through the installed package**

```bash
~/.local/pipx/venvs/hatop/bin/python -c "
from hatop.config import load_config
c = load_config()
print('groups:', len(c.groups))
print('sensors:', sum(len(g.sensors) for g in c.groups))
"
```

Expected: `groups: 5`, `sensors: 25`. This exercises the real
`~/.config/hatop/config.yaml` without ever printing its credential fields.

- [ ] **Step 5: Verify real MQTT authentication succeeds (not just "installed")**

Per the lesson already learned twice on this box (`unifi-ux7`,
`homeassistant` MCP setups in `nexus.md`) — a tool reporting "installed" or
"connected" doesn't prove credentials actually authenticate. Confirm for
real, without printing the password:

```bash
sh -c '
. /etc/nexus-ha-summary.conf
export MQTT_HOST MQTT_PORT MQTT_USER MQTT_PASS
~/.local/pipx/venvs/hatop/bin/python - <<PY
import os, time
from hatop.config import MqttConfig
from hatop.mqtt_client import MqttClient

config = MqttConfig(
    host=os.environ["MQTT_HOST"],
    port=int(os.environ["MQTT_PORT"]),
    username=os.environ["MQTT_USER"],
    password=os.environ["MQTT_PASS"],
)
result = {}
client = MqttClient(config, on_update=lambda *a: None, on_status=lambda s: result.setdefault("status", s))
client.start()
time.sleep(3)
client.stop()
print("MQTT verification:", result.get("status", "no callback received"))
PY
'
```

Expected: `MQTT verification: connected`.

- [ ] **Step 6: Manual visual verification (Mark, interactive terminal)**

The remaining check needs a real terminal — a non-interactive shell can't
confirm a full-screen TUI actually renders correctly. Run:

```bash
hatop
```

Confirm: the header shows `MQTT: connected`; all five group panels
(Temperatures, Water, Energy, Environment, Security) render; temperature
values populate (not stuck on `n/a`) within a couple seconds; `q` quits
cleanly back to the shell.

- [ ] **Step 7: (Optional) mention `hatop` in the login banner's Commands list**

Only after Step 6 is confirmed working. Edit
`/etc/update-motd.d/99-custom-banner`'s "Commands" section to add a
`hatop` line alongside the existing `ha_summary` entry, same one-line
description style, **not** auto-run (matches `ha_summary`'s own listed-but-
not-executed pattern). This is a `root`-owned file — use `sudo`.
