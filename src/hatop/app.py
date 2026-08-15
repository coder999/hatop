from __future__ import annotations

import queue
import time

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Footer, Header, Static

from hatop.config import GroupConfig, HatopConfig, load_config
from hatop.mqtt_client import MqttClient
from hatop.widgets import GroupPanel
from hatop.state import StateStore


def _estimate_group_rows(group: GroupConfig) -> int:
    """Rough number of terminal rows this group's content will need, for
    balancing panels across the two columns -- doesn't need to be exact,
    just consistent enough that a tall group (e.g. one with a `display:
    graph` sensor) doesn't get stacked with other tall groups purely
    because of where it falls in the config's group order."""
    if group.layout == "grid":
        visible = len({sensor.group_as or sensor.slug for sensor in group.sensors})
        return -(-visible // 2)  # ceil division, matches the 2-column sensor grid
    rows = 0
    seen_group_as: set[str] = set()
    for sensor in group.sensors:
        if sensor.group_as:
            if sensor.group_as in seen_group_as:
                continue
            seen_group_as.add(sensor.group_as)
            rows += 1
        else:
            rows += 1
            if sensor.display == "graph":
                rows += 4  # row-line + the taller standalone Sparkline below it
    return rows


def _assign_columns(groups: list[GroupConfig]) -> tuple[list[GroupConfig], list[GroupConfig]]:
    """Greedily assigns each group to whichever column currently has less
    estimated height, so panels balance across the two columns instead of
    just alternating by config order (which can stack multiple tall
    panels in the same column while the other sits nearly empty)."""
    left: list[GroupConfig] = []
    right: list[GroupConfig] = []
    left_height = 0
    right_height = 0
    border_rows = 2
    for group in groups:
        height = border_rows + _estimate_group_rows(group)
        if left_height <= right_height:
            left.append(group)
            left_height += height
        else:
            right.append(group)
            right_height += height
    return left, right


class HatopApp(App):
    """btop-style live dashboard for Home Assistant sensors over MQTT."""

    CSS = """
    #connection-status { dock: top; height: 1; padding: 0 1; }
    #panel-columns { height: auto; }
    #panel-columns > .panel-col { width: 1fr; height: auto; }
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
        # Groups are balanced (by estimated height, see _assign_columns) across
        # two independent vertical columns rather than a single stack, so a
        # standard 80x24 terminal fits all of them without scrolling. Each
        # column sizes to its own content (Textual's Grid only supports
        # uniform row heights, which would waste space on shorter panels
        # sharing a row with a taller one) -- plain Vertical containers avoid
        # that entirely. The whole thing still scrolls as a fallback on a
        # genuinely too-small terminal.
        left_groups, right_groups = _assign_columns(self.config.groups)
        with VerticalScroll(id="panels"):
            with Horizontal(id="panel-columns"):
                with Vertical(id="col-left", classes="panel-col"):
                    for group in left_groups:
                        panel = GroupPanel(group)
                        self._panels.append(panel)
                        yield panel
                with Vertical(id="col-right", classes="panel-col"):
                    for group in right_groups:
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
