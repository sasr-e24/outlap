"""Event-sourced race state.

The race is a log of events; current state is a fold over that log. This buys:

  * deterministic replays (same log → same state),
  * time-scrubbing (fold up to sim_time T),
  * cheap forking for the what-if sandbox (deep-copy state, inject a synthetic
    PitEntry, keep folding).

`RaceState.apply()` is the single reducer. Keep it pure and total — no I/O, no
model calls. Model workers read state and publish Predictions; they never mutate
it. This separation is what keeps every probability explainable and replayable.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional

from .events import (
    Compound,
    Event,
    GapUpdate,
    LapCompleted,
    PitEntry,
    PitExit,
    RaceControl,
    SessionInfo,
    StintChange,
    Weather,
)


@dataclass
class Stint:
    stint_number: int
    compound: Compound
    start_lap: int
    end_lap: Optional[int] = None
    laps: List[float] = field(default_factory=list)  # lap times observed in stint


@dataclass
class DriverState:
    driver: str
    position: int = 0
    lap_number: int = 0
    last_lap_time: Optional[float] = None
    compound: Compound = Compound.UNKNOWN
    tyre_age: int = 0
    gap_to_leader: Optional[float] = None
    interval_ahead: Optional[float] = None
    in_pit: bool = False
    pit_stops: int = 0
    stints: List[Stint] = field(default_factory=list)

    @property
    def current_stint(self) -> Optional[Stint]:
        return self.stints[-1] if self.stints else None


@dataclass
class RaceState:
    # session context
    year: int = 0
    round: int = 0
    circuit: str = ""
    session: str = "R"
    total_laps: int = 0

    # live context
    current_lap: int = 0
    track_status: str = "GREEN"  # GREEN / YELLOW / SC / VSC / RED / CHEQUERED
    air_temp: Optional[float] = None
    track_temp: Optional[float] = None
    rainfall: bool = False

    # per-driver
    drivers: Dict[str, DriverState] = field(default_factory=dict)

    # bookkeeping
    last_seq: int = -1
    last_sim_time: float = 0.0
    race_control_log: List[str] = field(default_factory=list)

    # ---- reducer --------------------------------------------------------

    def _driver(self, code: str) -> DriverState:
        d = self.drivers.get(code)
        if d is None:
            d = DriverState(driver=code)
            self.drivers[code] = d
        return d

    def apply(self, event: Event) -> "RaceState":
        """Fold a single event into state, mutating in place, returning self."""
        if event.seq >= 0:
            self.last_seq = event.seq
        self.last_sim_time = max(self.last_sim_time, event.sim_time)

        if isinstance(event, SessionInfo):
            self.year = event.year
            self.round = event.round
            self.circuit = event.circuit
            self.session = event.session
            self.total_laps = event.total_laps

        elif isinstance(event, LapCompleted):
            d = self._driver(event.driver)
            d.lap_number = event.lap_number
            d.position = event.position
            d.last_lap_time = event.lap_time
            d.compound = event.compound
            d.tyre_age = event.tyre_age
            self.current_lap = max(self.current_lap, event.lap_number)
            stint = d.current_stint
            if stint is not None and event.lap_time is not None and not event.is_pit_lap:
                stint.laps.append(event.lap_time)

        elif isinstance(event, GapUpdate):
            d = self._driver(event.driver)
            if event.gap_to_leader is not None:
                d.gap_to_leader = event.gap_to_leader
            if event.interval_ahead is not None:
                d.interval_ahead = event.interval_ahead

        elif isinstance(event, PitEntry):
            d = self._driver(event.driver)
            d.in_pit = True

        elif isinstance(event, PitExit):
            d = self._driver(event.driver)
            d.in_pit = False
            d.pit_stops += 1
            if event.new_compound != Compound.UNKNOWN:
                d.compound = event.new_compound

        elif isinstance(event, StintChange):
            d = self._driver(event.driver)
            if d.current_stint is not None:
                d.current_stint.end_lap = event.start_lap - 1
            d.stints.append(
                Stint(
                    stint_number=event.stint_number,
                    compound=event.compound,
                    start_lap=event.start_lap,
                )
            )
            d.compound = event.compound

        elif isinstance(event, RaceControl):
            if event.flag:
                self.track_status = event.flag
            self.race_control_log.append(event.message)

        elif isinstance(event, Weather):
            if event.air_temp is not None:
                self.air_temp = event.air_temp
            if event.track_temp is not None:
                self.track_temp = event.track_temp
            self.rainfall = event.rainfall

        return self

    # ---- fork / snapshot -------------------------------------------------

    def fork(self) -> "RaceState":
        """Deep-copy for the what-if sandbox. The copy can be driven with
        synthetic events without affecting the canonical live state."""
        return copy.deepcopy(self)

    def timing_tower(self) -> List[dict]:
        """Ordered rows for the timing tower UI."""
        rows = sorted(self.drivers.values(), key=lambda d: d.position or 99)
        return [
            {
                "position": d.position,
                "driver": d.driver,
                "lap": d.lap_number,
                "last_lap_time": d.last_lap_time,
                "compound": d.compound.value,
                "tyre_age": d.tyre_age,
                "gap_to_leader": d.gap_to_leader,
                "interval_ahead": d.interval_ahead,
                "in_pit": d.in_pit,
                "pit_stops": d.pit_stops,
            }
            for d in rows
        ]


def build_state(events) -> RaceState:
    """Fold an ordered iterable of events into a fresh RaceState."""
    state = RaceState()
    for event in events:
        state.apply(event)
    return state
