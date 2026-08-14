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
