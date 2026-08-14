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


async def test_app_stops_mqtt_client_on_unmount():
    app = HatopApp(config=make_config(), mqtt_client_factory=FakeMqttClient)

    async with app.run_test():
        mqtt_client = app._mqtt_client
        assert mqtt_client.started is True

    assert mqtt_client.stopped is True
