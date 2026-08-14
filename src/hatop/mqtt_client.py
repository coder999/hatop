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
        self._client.connect_async(self._config.host, self._config.port)
        self._client.loop_start()

    def stop(self) -> None:
        self._client.disconnect()
        self._client.loop_stop()

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
            payload_str = message.payload.decode("utf-8")
            value, ts = parse_payload(payload_str)
        except (UnicodeDecodeError, PayloadParseError):
            logger.warning("hatop: ignoring malformed payload on %s", message.topic)
            return
        self._on_update(slug, value, ts)
