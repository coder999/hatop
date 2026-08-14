from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from hatop.config import SensorConfig


class PayloadParseError(Exception):
    """Raised when an MQTT payload doesn't match the "<value>|<epoch>" format."""


def parse_payload(payload: str) -> tuple[str, int]:
    if "|" not in payload:
        raise PayloadParseError(f"payload missing '|' separator: {payload!r}")
    value, _, ts_str = payload.rpartition("|")
    try:
        ts = int(ts_str)
    except ValueError as exc:
        raise PayloadParseError(f"payload has non-integer timestamp: {payload!r}") from exc
    return value, ts


@dataclass
class SensorState:
    slug: str
    value: str | None = None
    ts: int | None = None
    history: deque[float] = field(default_factory=lambda: deque(maxlen=120))

    def is_stale(self, now: int, stale_seconds: int) -> bool:
        if self.ts is None:
            return False
        return (now - self.ts) >= stale_seconds


class StateStore:
    def __init__(self, sparkline_points: int = 120) -> None:
        self._sparkline_points = sparkline_points
        self._sensors: dict[str, SensorState] = {}

    def update(self, slug: str, value: str, ts: int) -> None:
        state = self._sensors.get(slug)
        if state is None:
            state = SensorState(slug=slug, history=deque(maxlen=self._sparkline_points))
            self._sensors[slug] = state
        state.value = value
        state.ts = ts
        try:
            state.history.append(float(value))
        except ValueError:
            pass  # non-numeric values (enum states) aren't graphed

    def get(self, slug: str) -> SensorState:
        state = self._sensors.get(slug)
        if state is None:
            return SensorState(slug=slug, history=deque(maxlen=self._sparkline_points))
        return state

    def sparkline_values(self, slug: str) -> list[float]:
        return list(self.get(slug).history)


def collapse_group_status(sensors: list[SensorConfig], store: StateStore) -> str:
    """Combine sensors sharing a group_as key into one ha_summary-style line."""
    open_labels = []
    for sensor in sensors:
        state = store.get(sensor.slug)
        if state.value is None:
            continue
        if sensor.good and state.value not in sensor.good:
            open_labels.append(sensor.label)
    if not open_labels:
        return "All closed"
    return "OPEN: " + ", ".join(open_labels)
