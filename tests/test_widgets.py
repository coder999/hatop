from textual.app import App, ComposeResult
from textual.containers import Grid
from textual.widgets import Label

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
        sensors=[
            SensorConfig(
                slug="weather_temp", label="Weather", kind="temp", unit="F", display="inline_graph"
            )
        ],
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


async def test_sensor_row_standard_display_has_no_sparkline_by_default():
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
        assert len(app.query("#sensor-weather_temp #spark")) == 0


async def test_sensor_row_graph_display_shows_taller_sparkline():
    group = GroupConfig(
        name="Energy",
        sensors=[
            SensorConfig(
                slug="energy_load_home", label="Home Load", kind="gauge", unit=" W", display="graph"
            )
        ],
    )
    app = PanelHarness(group)
    store = StateStore()
    store.update("energy_load_home", "343", 1000)

    async with app.run_test():
        app.panel.refresh_state(store, now=1000, stale_seconds=21600)
        value = app.query_one("#sensor-energy_load_home #value")
        assert "343 W" in str(value.visual)
        spark = app.query_one("#sensor-energy_load_home #spark")
        assert spark.data == [343.0]
        assert "graph-spark" in spark.classes


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


async def test_sensor_row_label_is_not_truncated_by_value_column_width():
    group = GroupConfig(
        name="Security",
        sensors=[SensorConfig(slug="water_pressure", label="Home Water Pressure", kind="gauge", unit=" PSI")],
    )
    app = PanelHarness(group)

    async with app.run_test():
        label = app.query_one("#sensor-water_pressure Label")
        assert label.size.width == 20


async def test_group_panel_shows_name_as_border_title_not_separate_label():
    group = GroupConfig(
        name="Temperatures",
        sensors=[SensorConfig(slug="weather_temp", label="Weather", kind="temp", unit="F")],
    )
    app = PanelHarness(group)

    async with app.run_test():
        assert app.panel.border_title == "Temperatures"
        assert len(app.query("GroupPanel Label.title")) == 0


async def test_grid_layout_sensor_ignores_graph_display_no_room_for_it():
    group = GroupConfig(
        name="Temperatures",
        layout="grid",
        sensors=[
            SensorConfig(slug="weather_temp", label="Weather", kind="temp", unit="F", display="graph")
        ],
    )
    app = PanelHarness(group)

    async with app.run_test():
        assert len(app.query("#sensor-weather_temp Sparkline")) == 0


async def test_grid_layout_group_mounts_grid_container():
    group = GroupConfig(
        name="Temperatures",
        layout="grid",
        sensors=[SensorConfig(slug="weather_temp", label="Weather", kind="temp", unit="F")],
    )
    app = PanelHarness(group)

    async with app.run_test():
        assert app.query_one(GroupPanel).query_one(Grid) is not None


async def test_grid_layout_sensor_renders_compact_merged_cell():
    """Grid-layout groups (e.g. Temperatures) use a single narrow cell —
    label and value merged into one Static, no fixed 20+14-column split —
    since a fixed-width split doesn't fit a grid cell once the panel is
    already halved by the app's two-column layout."""
    group = GroupConfig(
        name="Temperatures",
        layout="grid",
        sensors=[SensorConfig(slug="weather_temp", label="Weather", kind="temp", unit="F")],
    )
    app = PanelHarness(group)
    store = StateStore()
    store.update("weather_temp", "68.2", 1000)

    async with app.run_test():
        app.panel.refresh_state(store, now=1000, stale_seconds=21600)
        row = app.query_one("#sensor-weather_temp")
        assert len(row.query(Label)) == 0
        value = app.query_one("#sensor-weather_temp #value")
        assert "Weather 68.2F" in str(value.visual)
