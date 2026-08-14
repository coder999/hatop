from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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


def test_handle_message_ignores_non_utf8_payload_without_raising():
    client, updates, _ = make_client()
    message = SimpleNamespace(topic="nexus/ha/weather_temp", payload=b"\xff\xfe not valid utf-8")

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


def test_start_uses_connect_async_so_unreachable_broker_does_not_raise():
    with patch("hatop.mqtt_client.mqtt.Client") as MockClient:
        fake_mqtt_client = MockClient.return_value
        config = MqttConfig(host="broker", username="u", password="p")
        client = MqttClient(config, on_update=lambda *a: None, on_status=lambda s: None)

        client.start()

        fake_mqtt_client.connect_async.assert_called_once_with("broker", 1883)
        fake_mqtt_client.connect.assert_not_called()
        fake_mqtt_client.loop_start.assert_called_once()
