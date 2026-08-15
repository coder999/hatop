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
        assert "connected" in str(status.visual)


async def test_app_updates_sensor_row_when_mqtt_update_arrives():
    app = HatopApp(config=make_config(), mqtt_client_factory=FakeMqttClient)

    async with app.run_test():
        app._updates.put(("weather_temp", "72.3", 1000))
        app._tick()
        value = app.query_one("#sensor-weather_temp #value")
        assert "72.3F" in str(value.visual)


def make_multi_group_config() -> HatopConfig:
    def group(name):
        return GroupConfig(
            name=name,
            sensors=[SensorConfig(slug=f"{name.lower()}_sensor", label=name, kind="gauge")],
        )

    return HatopConfig(
        mqtt=MqttConfig(host="broker", username="u", password="p"),
        groups=[group("Alpha"), group("Bravo"), group("Charlie"), group("Delta")],
    )


async def test_app_balances_equal_height_group_panels_across_two_columns():
    app = HatopApp(config=make_multi_group_config(), mqtt_client_factory=FakeMqttClient)

    async with app.run_test():
        left_titles = [p.border_title for p in app.query_one("#col-left").query(".panel")]
        right_titles = [p.border_title for p in app.query_one("#col-right").query(".panel")]
        assert left_titles == ["Alpha", "Charlie"]
        assert right_titles == ["Bravo", "Delta"]


async def test_app_keeps_a_tall_graph_panel_from_overloading_one_column():
    """A group with a `display: graph` sensor is much taller than a
    single-line group. Naive alternation could stack two tall groups in
    the same column while the other sits nearly empty; height-based
    balancing should even that out instead."""
    tall_group = GroupConfig(
        name="Tall",
        sensors=[SensorConfig(slug="tall_sensor", label="Tall", kind="gauge", display="graph")],
    )
    short_groups = [
        GroupConfig(
            name=name,
            sensors=[SensorConfig(slug=f"{name.lower()}_sensor", label=name, kind="gauge")],
        )
        for name in ("Short1", "Short2", "Short3")
    ]
    config = HatopConfig(
        mqtt=MqttConfig(host="broker", username="u", password="p"),
        groups=[tall_group, *short_groups],
    )
    app = HatopApp(config=config, mqtt_client_factory=FakeMqttClient)

    async with app.run_test():
        left_titles = [p.border_title for p in app.query_one("#col-left").query(".panel")]
        right_titles = [p.border_title for p in app.query_one("#col-right").query(".panel")]
        # The tall panel alone should outweigh a column of two-or-more short
        # panels, so it must not share a column with more than one short one.
        assert "Tall" in left_titles
        assert len(left_titles) < len(right_titles)


async def test_app_stops_mqtt_client_on_unmount():
    app = HatopApp(config=make_config(), mqtt_client_factory=FakeMqttClient)

    async with app.run_test():
        mqtt_client = app._mqtt_client
        assert mqtt_client.started is True

    assert mqtt_client.stopped is True
