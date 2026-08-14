from __future__ import annotations

from textual.containers import Grid, Horizontal, Vertical
from textual.widgets import Label, Sparkline, Static

from hatop.config import GroupConfig, SensorConfig
from hatop.state import SensorState, StateStore, collapse_group_status


def format_value(sensor: SensorConfig, state: SensorState) -> str:
    if state.value is None:
        return "n/a"
    if sensor.kind in ("temp", "gauge", "counter"):
        try:
            number = float(state.value) * sensor.scale
        except ValueError:
            return f"{state.value}{sensor.unit}"
        text = f"{number:.1f}".rstrip("0").rstrip(".")
        return f"{text}{sensor.unit}"
    return state.value


def status_color(sensor: SensorConfig, state: SensorState) -> str:
    if state.value is None:
        return "grey50"
    if sensor.good and state.value in sensor.good:
        return "green"
    if sensor.bad and state.value in sensor.bad:
        return "red"
    if sensor.good or sensor.bad:
        return "yellow"
    return "white"


class SensorRow(Horizontal):
    """One sensor: 'Label: value' (+ sparkline for temp/gauge kinds)."""

    DEFAULT_CSS = """
    SensorRow { height: 1; }
    SensorRow > Label { width: 20; }
    SensorRow > Static { width: 14; }
    SensorRow > Sparkline { width: 1fr; }
    """

    def __init__(self, sensor: SensorConfig) -> None:
        super().__init__(id=f"sensor-{sensor.slug}")
        self.sensor = sensor
        self._show_sparkline = sensor.kind in ("temp", "gauge")

    def compose(self):
        yield Label(f"{self.sensor.label}:")
        yield Static(self._markup(SensorState(slug=self.sensor.slug), stale=False), id="value")
        if self._show_sparkline:
            yield Sparkline([], id="spark")

    def _markup(self, state: SensorState, stale: bool) -> str:
        text = format_value(self.sensor, state)
        if stale:
            text += " *"
        color = status_color(self.sensor, state)
        return f"[{color}]{text}[/{color}]"

    def update_state(self, state: SensorState, stale: bool) -> None:
        self.query_one("#value", Static).update(self._markup(state, stale))
        if self._show_sparkline:
            self.query_one("#spark", Sparkline).data = list(state.history)


class GroupPanel(Vertical):
    """One config group (e.g. 'Temperatures'): title + its sensor rows.
    Sensors sharing a group_as key collapse into a single combined row."""

    DEFAULT_CSS = """
    GroupPanel { border: round $primary; padding: 0 1; margin-bottom: 1; }
    GroupPanel > Label.title { text-style: bold; }
    GroupPanel > Grid.rows { grid-size: 3; grid-gutter: 0 2; }
    """

    def __init__(self, group: GroupConfig) -> None:
        super().__init__()
        self.group = group

    def compose(self):
        yield Label(self.group.name, classes="title")
        container_cls = Grid if self.group.layout == "grid" else Vertical
        with container_cls(classes="rows"):
            seen_group_as: set[str] = set()
            for sensor in self.group.sensors:
                if sensor.group_as:
                    if sensor.group_as in seen_group_as:
                        continue
                    seen_group_as.add(sensor.group_as)
                    yield Static(id=f"group-{sensor.group_as}")
                else:
                    yield SensorRow(sensor)

    def refresh_state(self, store: StateStore, now: int, stale_seconds: int) -> None:
        rendered_group_as: set[str] = set()
        for sensor in self.group.sensors:
            if sensor.group_as:
                if sensor.group_as in rendered_group_as:
                    continue
                rendered_group_as.add(sensor.group_as)
                siblings = [s for s in self.group.sensors if s.group_as == sensor.group_as]
                status = collapse_group_status(siblings, store)
                color = "green" if status == "All closed" else "red"
                self.query_one(f"#group-{sensor.group_as}", Static).update(
                    f"[{color}]{status}[/{color}]"
                )
            else:
                state = store.get(sensor.slug)
                stale = state.is_stale(now, stale_seconds)
                self.query_one(f"#sensor-{sensor.slug}", SensorRow).update_state(state, stale)
