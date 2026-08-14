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
