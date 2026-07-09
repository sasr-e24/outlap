"""ReplaySource — the P0 adapter and the validation harness.

Replay is not a dev crutch: the same engine powers the Replays view, demo mode,
and CI (replay a race with a known outcome, score every prediction, fail the
build if calibration regresses).

Two backends:

  * ``from_fastf1`` — loads a real session via FastF1 and normalizes laps, pit
    stops, stints and weather into the event stream. Requires the optional
    ``fastf1`` dependency and a populated cache; used for real replays.
  * ``from_event_log`` — replays a pre-built list of events. Used by the offline
    synthetic fixture (``outlap.fixtures``) so tests and the demo run with no
    network and no heavy dependency.

Both pace themselves by ``speed`` (e.g. 10× → sleep 1/10th of the sim gap).
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, List, Optional

from ..events import Event
from .base import DataSource


class ReplaySource(DataSource):
    name = "replay"

    def __init__(self, event_log: List[Event], speed: float = 0.0):
        """
        :param event_log: ordered events (ascending sim_time).
        :param speed: playback multiplier. 0 = as fast as possible (tests/CI);
            10 = ten times real time; 1 = real time.
        """
        self._log = sorted(event_log, key=lambda e: e.sim_time)
        self.speed = speed

    @classmethod
    def from_event_log(cls, event_log: List[Event], speed: float = 0.0) -> "ReplaySource":
        return cls(event_log, speed=speed)

    @classmethod
    def from_fastf1(
        cls,
        year: int,
        gp,  # round number or name
        session: str = "R",
        speed: float = 0.0,
        cache_dir: Optional[str] = None,
    ) -> "ReplaySource":
        """Build a replay from a real FastF1 session. Imported lazily so the
        core package has no hard dependency on fastf1/pandas."""
        from ._fastf1_loader import load_fastf1_event_log

        log = load_fastf1_event_log(year, gp, session, cache_dir=cache_dir)
        return cls(log, speed=speed)

    async def events(self) -> AsyncIterator[Event]:
        prev_t: Optional[float] = None
        for event in self._log:
            if self.speed > 0 and prev_t is not None:
                dt = (event.sim_time - prev_t) / self.speed
                if dt > 0:
                    await asyncio.sleep(dt)
            prev_t = event.sim_time
            yield event
