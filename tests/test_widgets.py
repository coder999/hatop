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
        assert "n/a" in str(value.visual)


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
        assert "72.3F" in str(value.visual)
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
        assert "*" in str(value.visual)


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
        assert "34962.7 kWh" in str(value.visual)
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
        assert "All closed" in str(status.visual)


async def test_grid_layout_group_mounts_grid_container():
    group = GroupConfig(
        name="Temperatures",
        layout="grid",
        sensors=[SensorConfig(slug="weather_temp", label="Weather", kind="temp", unit="F")],
    )
    app = PanelHarness(group)

    async with app.run_test():
        assert app.query_one(GroupPanel).query_one(Grid) is not None
