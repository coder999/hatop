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
