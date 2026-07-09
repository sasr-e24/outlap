"""Normalized event types for the OUTLAP race event stream.

Every data source (replay, OpenF1 live, raw SignalR) emits these same events.
Downstream code cannot tell replay from live — that is the whole point of the
ports-and-adapters layer described in the architecture doc.

Events are immutable, timestamped, and carry a monotonically increasing sequence
number once they pass through ingestion. The race state is a deterministic fold
over an ordered log of these events, which is what makes replay, time-scrubbing
and the what-if sandbox fork cheap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Compound(str, Enum):
    SOFT = "SOFT"
    MEDIUM = "MEDIUM"
    HARD = "HARD"
    INTERMEDIATE = "INTERMEDIATE"
    WET = "WET"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class Event:
    """Base for all normalized events.

    `sim_time` is seconds since session start (the authoritative clock for
    ordering and replay). `wall_time` is the ingestion wall-clock (unix seconds)
    used only for data-age display. `seq` is assigned by ingestion.
    """

    sim_time: float
    wall_time: float = 0.0
    seq: int = -1

    @property
    def kind(self) -> str:
        return type(self).__name__


@dataclass(frozen=True, slots=True)
class SessionInfo(Event):
    """Emitted once at the top of a session/replay to seed state."""

    year: int = 0
    round: int = 0
    circuit: str = ""
    session: str = "R"  # R, Q, FP1...
    total_laps: int = 0


@dataclass(frozen=True, slots=True)
class LapCompleted(Event):
    driver: str = ""
    lap_number: int = 0
    lap_time: Optional[float] = None  # seconds, None if not set (e.g. lap 1 / pit lap)
    position: int = 0
    compound: Compound = Compound.UNKNOWN
    tyre_age: int = 0  # laps on the current set at end of this lap
    is_pit_lap: bool = False


@dataclass(frozen=True, slots=True)
class GapUpdate(Event):
    """Gap to leader and interval to car ahead, in seconds."""

    driver: str = ""
    lap_number: int = 0
    gap_to_leader: Optional[float] = None
    interval_ahead: Optional[float] = None


@dataclass(frozen=True, slots=True)
class PitEntry(Event):
    driver: str = ""
    lap_number: int = 0


@dataclass(frozen=True, slots=True)
class PitExit(Event):
    driver: str = ""
    lap_number: int = 0
    new_compound: Compound = Compound.UNKNOWN
    pit_lane_time: Optional[float] = None  # total time lost in pit lane, seconds


@dataclass(frozen=True, slots=True)
class StintChange(Event):
    driver: str = ""
    stint_number: int = 0
    compound: Compound = Compound.UNKNOWN
    start_lap: int = 0


@dataclass(frozen=True, slots=True)
class TrackOutline(Event):
    """The circuit shape, emitted once per session.

    `points` is an ordered ring of (x, y) in the source's own coordinate space
    (FastF1 uses tenths of a metre; the fixture uses arbitrary units). The UI
    normalizes to a viewBox, so absolute scale never matters.
    """

    points: tuple = ()


@dataclass(frozen=True, slots=True)
class PositionSample(Event):
    """Where a car is on track at `sim_time`. ~1 Hz here; the real feed is faster."""

    driver: str = ""
    x: float = 0.0
    y: float = 0.0


@dataclass(frozen=True, slots=True)
class TelemetrySample(Event):
    driver: str = ""
    speed: float = 0.0
    throttle: float = 0.0
    brake: float = 0.0
    gear: int = 0
    rpm: float = 0.0


@dataclass(frozen=True, slots=True)
class RaceControl(Event):
    """Structured race-control message (already text from the feed)."""

    message: str = ""
    category: str = ""  # Flag, SafetyCar, Drs, CarEvent, Other
    flag: Optional[str] = None  # GREEN, YELLOW, RED, SC, VSC, CHEQUERED
    driver: Optional[str] = None


@dataclass(frozen=True, slots=True)
class Weather(Event):
    air_temp: Optional[float] = None
    track_temp: Optional[float] = None
    humidity: Optional[float] = None
    rainfall: bool = False
    wind_speed: Optional[float] = None


@dataclass(frozen=True, slots=True)
class TeamRadio(Event):
    """Reference to a published team-radio clip (audio fetched lazily)."""

    driver: str = ""
    audio_url: str = ""
    transcript: Optional[str] = None  # filled by the signal-intel worker later


# ---- Prediction events (published back onto the bus by model workers) -------


@dataclass(frozen=True, slots=True)
class Prediction(Event):
    """A model output, logged to the predictions ledger and scored post-race."""

    model: str = ""  # deg, pit_window, undercut, monte_carlo, ...
    driver: str = ""
    metric: str = ""  # e.g. "p_podium", "pit_window_open"
    value: float = 0.0
    payload: dict = field(default_factory=dict)


ALL_EVENT_TYPES = (
    SessionInfo,
    LapCompleted,
    GapUpdate,
    PitEntry,
    PitExit,
    StintChange,
    TelemetrySample,
    TrackOutline,
    PositionSample,
    RaceControl,
    Weather,
    TeamRadio,
    Prediction,
)
