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
    try:
        return _parse_config_unsafe(raw, config_path)
    except HatopConfigError:
        raise
    except (TypeError, ValueError, AttributeError) as exc:
        raise HatopConfigError(f"hatop: {config_path} is malformed: {exc}") from exc


def _parse_config_unsafe(raw: dict, config_path: Path) -> HatopConfig:
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
