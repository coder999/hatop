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


class SensorRow(Vertical):
    """One sensor. In `compact` mode (grid-layout groups, e.g. Temperatures)
    it's a single narrow "Label value" cell with no reserved columns, sized
    to its own text so several fit per grid row. Otherwise it's a
    'Label: value' line with fixed label/value columns. `display:
    inline_graph` adds a sparkline beside the value (list mode only —
    compact cells have no room for one); `display: graph` adds a taller
    standalone sparkline below instead. `display: standard` (the default)
    shows just the figure, no graph at all."""

    DEFAULT_CSS = """
    SensorRow { height: auto; }
    SensorRow.compact { height: 1; }
    SensorRow > .row-line { height: 1; }
    SensorRow > .row-line > Label { width: 20; }
    SensorRow > .row-line > #value { width: 14; }
    SensorRow > .row-line > Sparkline { width: 1fr; }
    SensorRow > Sparkline.graph-spark { height: 4; }
    """

    def __init__(self, sensor: SensorConfig, compact: bool = False) -> None:
        super().__init__(id=f"sensor-{sensor.slug}", classes="compact" if compact else "")
        self.sensor = sensor
        self._compact = compact
        # inline_graph and graph both need room compact grid cells don't have
        # (a fixed-height Grid row can't accommodate the taller graph either),
        # so both degrade to a bare figure in compact mode.
        self._show_inline_spark = not compact and sensor.display == "inline_graph"
        self._show_graph = not compact and sensor.display == "graph"

    def compose(self):
        if self._compact:
            yield Static(self._compact_markup(SensorState(slug=self.sensor.slug), stale=False), id="value")
        else:
            with Horizontal(classes="row-line"):
                yield Label(f"{self.sensor.label}:")
                yield Static(self._markup(SensorState(slug=self.sensor.slug), stale=False), id="value")
                if self._show_inline_spark:
                    yield Sparkline([], id="spark")
        if self._show_graph:
            yield Sparkline([], id="spark", classes="graph-spark")

    def _markup(self, state: SensorState, stale: bool) -> str:
        text = format_value(self.sensor, state)
        if stale:
            text += " *"
        color = status_color(self.sensor, state)
        return f"[{color}]{text}[/{color}]"

    def _compact_markup(self, state: SensorState, stale: bool) -> str:
        text = format_value(self.sensor, state)
        if stale:
            text += "*"
        color = status_color(self.sensor, state)
        return f"[{color}]{self.sensor.label} {text}[/{color}]"

    def update_state(self, state: SensorState, stale: bool) -> None:
        markup = self._compact_markup(state, stale) if self._compact else self._markup(state, stale)
        self.query_one("#value", Static).update(markup)
        if self._show_inline_spark or self._show_graph:
            self.query_one("#spark", Sparkline).data = list(state.history)


class GroupPanel(Vertical):
    """One config group (e.g. 'Temperatures'): title + its sensor rows.
    Sensors sharing a group_as key collapse into a single combined row."""

    DEFAULT_CSS = """
    GroupPanel { border: round $primary; padding: 0 1; height: auto; margin-bottom: 1; }
    GroupPanel > .rows { height: auto; }
    GroupPanel > Grid.rows { grid-size: 2; grid-gutter: 0 2; grid-rows: 1; }
    """

    def __init__(self, group: GroupConfig) -> None:
        super().__init__(classes="panel")
        self.group = group
        self.border_title = group.name

    def compose(self):
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
                    yield SensorRow(sensor, compact=(self.group.layout == "grid"))

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
