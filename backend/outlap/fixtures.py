"""Synthetic race fixture — deterministic, offline, no dependencies.

Generates a normalized event log for a small made-up race so tests, CI and the
demo run with no network and without FastF1/pandas. The numbers are physically
plausible (linear tyre deg + fuel burn + a pit stop) but are NOT real data —
real replays come from `ReplaySource.from_fastf1`.

The generator is seeded, so the same call always yields the same log — which is
exactly what the event-sourced design needs for reproducible tests.
"""

from __future__ import annotations

import random
from typing import List

from .events import (
    Compound,
    Event,
    GapUpdate,
    LapCompleted,
    PitExit,
    PitEntry,
    SessionInfo,
    StintChange,
    Weather,
)

# driver code -> (base pace seconds, one-stop pit lap)
_GRID = {
    "VER": (91.20, 26),
    "NOR": (91.35, 24),
    "LEC": (91.45, 28),
    "PIA": (91.50, 25),
    "RUS": (91.60, 27),
    "HAM": (91.70, 30),
}

FUEL_EFFECT_PER_LAP = 0.055  # s/lap, car gets lighter → faster
DEG = {  # s per lap of tyre age, per compound
    Compound.SOFT: 0.11,
    Compound.MEDIUM: 0.065,
    Compound.HARD: 0.04,
}
PIT_LANE_LOSS = 21.0


def build_synthetic_race(total_laps: int = 40, seed: int = 7) -> List[Event]:
    rng = random.Random(seed)
    events: List[Event] = []
    events.append(
        SessionInfo(
            sim_time=0.0,
            year=2025,
            round=99,
            circuit="Synthetica GP (fixture)",
            session="R",
            total_laps=total_laps,
        )
    )
    events.append(Weather(sim_time=0.0, air_temp=27.0, track_temp=41.0, rainfall=False))

    # each driver starts on MEDIUM, pits once to HARD
    start_compound = Compound.MEDIUM
    second_compound = Compound.HARD
    clock = {drv: 0.0 for drv in _GRID}  # cumulative race time per driver
    tyre_age = {drv: 0 for drv in _GRID}
    compound = {drv: start_compound for drv in _GRID}
    stint_no = {drv: 1 for drv in _GRID}

    for drv in _GRID:
        events.append(
            StintChange(sim_time=0.0, driver=drv, stint_number=1, compound=start_compound, start_lap=1)
        )

    for lap in range(1, total_laps + 1):
        lap_rows = []
        for drv, (base, pit_lap) in _GRID.items():
            # pit stop happens at the start of pit_lap
            is_pit_lap = lap == pit_lap
            if is_pit_lap:
                events.append(PitEntry(sim_time=clock[drv], driver=drv, lap_number=lap))
                compound[drv] = second_compound
                tyre_age[drv] = 0
                stint_no[drv] += 1
                events.append(
                    StintChange(
                        sim_time=clock[drv],
                        driver=drv,
                        stint_number=stint_no[drv],
                        compound=second_compound,
                        start_lap=lap,
                    )
                )

            fuel_gain = FUEL_EFFECT_PER_LAP * (lap - 1)
            deg_pen = DEG[compound[drv]] * tyre_age[drv]
            noise = rng.gauss(0.0, 0.12)
            lap_time = base - fuel_gain + deg_pen + noise
            if is_pit_lap:
                lap_time += PIT_LANE_LOSS
                events.append(
                    PitExit(
                        sim_time=clock[drv] + lap_time,
                        driver=drv,
                        lap_number=lap,
                        new_compound=second_compound,
                        pit_lane_time=PIT_LANE_LOSS,
                    )
                )

            clock[drv] += lap_time
            tyre_age[drv] += 1
            lap_rows.append((drv, clock[drv], lap_time, is_pit_lap))

        # positions from cumulative race time; gaps to leader
        lap_rows.sort(key=lambda r: r[1])
        leader_time = lap_rows[0][1]
        prev_time = None
        for pos, (drv, cum, lap_time, is_pit_lap) in enumerate(lap_rows, start=1):
            events.append(
                LapCompleted(
                    sim_time=cum,
                    driver=drv,
                    lap_number=lap,
                    lap_time=round(lap_time, 3),
                    position=pos,
                    compound=compound[drv],
                    tyre_age=tyre_age[drv],
                    is_pit_lap=is_pit_lap,
                )
            )
            events.append(
                GapUpdate(
                    sim_time=cum,
                    driver=drv,
                    lap_number=lap,
                    gap_to_leader=round(cum - leader_time, 3),
                    interval_ahead=round(cum - prev_time, 3) if prev_time is not None else 0.0,
                )
            )
            prev_time = cum

    events.sort(key=lambda e: (e.sim_time, 0 if isinstance(e, LapCompleted) else 1))
    return events
