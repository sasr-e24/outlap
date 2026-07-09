"""Undercut probability (Pillar A).

For each attacker-defender pair close enough to matter: if the attacker boxes
now and the defender responds one lap later, does the attacker come out ahead?

The attacker rejoins on fresh rubber while the defender runs one more lap on a
tyre `age` laps old. The attacker's out-lap advantage is roughly

    delta = slope_defender * age_defender  +  FRESH_BOOST

(the deg the defender is still carrying, plus the raw grip advantage of a new
set). The attacker starts `gap` seconds behind, so the undercut works when
`delta > gap`. Pit-stop time varies and traffic intervenes, so rather than a
verdict we return a probability, treating the outcome as normally distributed:

    P(undercut) = Phi((delta - gap) / sigma)

`sigma` bundles pit-stop variance and traffic. This is a probability, not a
prophecy: it ignores where the attacker rejoins in traffic and assumes the
defender covers on the very next lap.
"""

from __future__ import annotations

import math
from typing import Dict, List

from ..events import Event, LapCompleted, Prediction
from ..state import RaceState
from .base import ModelWorker

FRESH_BOOST_S = 0.8  # raw out-lap pace advantage of a new set, seconds
SIGMA_S = 0.9  # pit-stop time variance + traffic, seconds
MAX_GAP_S = 3.0  # beyond this an undercut is not on
MIN_REMAINING_LAPS = 3


def _phi(z: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


class UndercutModel(ModelWorker):
    name = "undercut"

    def __init__(self, bus, state: RaceState):
        super().__init__(bus, state)
        self._deg: Dict[str, float] = {}

    def attach(self) -> None:
        super().attach()
        self.bus.subscribe(Prediction, self._cache_deg)

    async def _cache_deg(self, pred: Event) -> None:
        if isinstance(pred, Prediction) and pred.model == "deg" and pred.metric == "deg_slope_s_per_lap":
            self._deg[pred.driver] = pred.value

    async def on_event(self, event: Event) -> List[Prediction]:
        if not isinstance(event, LapCompleted) or event.is_pit_lap:
            return []
        if self.state.total_laps - event.lap_number < MIN_REMAINING_LAPS:
            return []

        attacker = self.state.drivers.get(event.driver)
        if attacker is None or attacker.position <= 1:
            return []  # the leader has nobody to undercut

        gap = attacker.interval_ahead
        if gap is None or gap <= 0 or gap > MAX_GAP_S:
            return []

        defender = next(
            (d for d in self.state.drivers.values() if d.position == attacker.position - 1), None
        )
        if defender is None:
            return []

        def_slope = self._deg.get(defender.driver)
        if def_slope is None or def_slope <= 0:
            return []

        delta = def_slope * defender.tyre_age + FRESH_BOOST_S
        p = _phi((delta - gap) / SIGMA_S)

        return [
            Prediction(
                sim_time=event.sim_time,
                model=self.name,
                driver=event.driver,
                metric="p_undercut",
                value=round(p, 4),
                payload={
                    "defender": defender.driver,
                    "gap_s": round(gap, 3),
                    "delta_s": round(delta, 3),
                    "defender_tyre_age": defender.tyre_age,
                    "sigma_s": SIGMA_S,
                },
            )
        ]
