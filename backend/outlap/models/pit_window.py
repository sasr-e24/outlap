"""Pit window / "box now vs extend" (Pillar A).

The question is NOT "is boxing better than never boxing again" -- you are going
to pit regardless. It is "box this lap, or extend k more laps?" Pit loss is paid
exactly once either way, so **it cancels out of the comparison entirely** and
must not appear in the decision. (An earlier version had `- PIT_LOSS` in the net
gain, which made the window look permanently open from mid-stint onward.)

Model. You are on lap C with a tyre `a` laps old, `R` laps remain. Deg is linear,
so a stint of n laps on a tyre with slope s costs `s * n(n+1)/2` seconds relative
to a permanently fresh tyre. Extending by k laps then running the rest on a new
set costs:

    cost(k) = s_now * sum_{i=1..k} (a + i)      # k more laps on the old set
            + s_next * (R-k)(R-k+1) / 2         # the rest on the new set
            ( + PIT_LOSS, identical for every k, therefore dropped )

We minimise `cost(k)` over k. `optimal_k == 0` means box now -- the window is
open. `extend_deltas` reports `cost(k) - cost(0)` for k = 0..5, which is exactly
the plan's "projected race-time delta of pitting this lap vs +1...+5 laps".

Sanity check the shape: with equal slopes the minimum sits at a half-and-half
split; a softer current tyre pulls the stop earlier. Both are asserted in tests.

Still ignored in v1, and it matters: track position and the traffic you'd rejoin
into, safety-car probability, and whether the compound you want is available.
This is the deterministic core, not a strategy call.
"""

from __future__ import annotations

import statistics
from typing import Dict, List, Optional, Tuple

from ..events import Compound, Event, LapCompleted, Prediction
from ..state import RaceState
from .base import ModelWorker

PIT_LOSS_S = 21.0  # reported for context only -- it cancels out of the decision
MIN_REMAINING_LAPS = 5
EXTEND_HORIZON = 5  # report deltas for boxing now vs +1..+5 laps


def _stint_cost(n: int, slope: float) -> float:
    """Seconds lost to deg over an n-lap stint (ages 1..n), vs an always-fresh tyre."""
    if n <= 0:
        return 0.0
    return slope * n * (n + 1) / 2.0


def cost_of_extending(k: int, age: int, remaining: int, s_now: float, s_next: float) -> float:
    """Deg cost of running k more laps on the current set, then pitting."""
    stay = s_now * sum(age + i for i in range(1, k + 1))
    return stay + _stint_cost(remaining - k, s_next)


class PitWindowModel(ModelWorker):
    name = "pit_window"

    def __init__(self, bus, state: RaceState):
        super().__init__(bus, state)
        self._deg: Dict[Tuple[str, str], float] = {}  # (driver, compound) -> slope

    def attach(self) -> None:
        super().attach()
        # cache the deg model's output; this handler never publishes, so no loop
        self.bus.subscribe(Prediction, self._cache_deg)

    async def _cache_deg(self, pred: Event) -> None:
        if isinstance(pred, Prediction) and pred.model == "deg" and pred.metric == "deg_slope_s_per_lap":
            comp = pred.payload.get("compound")
            if comp:
                self._deg[(pred.driver, comp)] = pred.value

    def _next_compound_slope(self, current: str) -> Tuple[Optional[float], Optional[str]]:
        """Deg of the set you'd bolt on: field-median slope of the most durable
        other compound we have a fit for. Unknown before anyone runs it."""
        by_comp: Dict[str, List[float]] = {}
        for (_drv, comp), slope in self._deg.items():
            if comp != current and slope > 0:
                by_comp.setdefault(comp, []).append(slope)
        if not by_comp:
            return None, None
        comp = min(by_comp, key=lambda c: statistics.median(by_comp[c]))
        return statistics.median(by_comp[comp]), comp

    async def on_event(self, event: Event) -> List[Prediction]:
        if not isinstance(event, LapCompleted) or event.is_pit_lap:
            return []
        if event.compound == Compound.UNKNOWN:
            return []

        s_now = self._deg.get((event.driver, event.compound.value))
        if s_now is None or s_now <= 0:
            return []

        remaining = self.state.total_laps - event.lap_number
        if remaining < MIN_REMAINING_LAPS:
            return []

        s_next, next_comp = self._next_compound_slope(event.compound.value)
        assumed = s_next is None
        if assumed:
            # No fit for any other compound yet. Assume the new set degrades like
            # the current one -- flagged in the payload so the UI can say so.
            s_next, next_comp = s_now, event.compound.value

        age = event.tyre_age
        costs = [cost_of_extending(k, age, remaining, s_now, s_next) for k in range(remaining + 1)]
        optimal_k = min(range(len(costs)), key=lambda k: costs[k])
        base = costs[0]
        deltas = {k: round(costs[k] - base, 3) for k in range(0, min(EXTEND_HORIZON, remaining) + 1)}

        return [
            Prediction(
                sim_time=event.sim_time,
                model=self.name,
                driver=event.driver,
                metric="laps_to_optimal_stop",
                value=float(optimal_k),
                payload={
                    "open": optimal_k == 0,
                    "optimal_lap": event.lap_number + optimal_k,
                    "extend_deltas_s": deltas,
                    "cost_now_s": round(base, 3),
                    "cost_at_optimal_s": round(costs[optimal_k], 3),
                    "remaining_laps": remaining,
                    "tyre_age": age,
                    "deg_slope_now": s_now,
                    "deg_slope_next": round(s_next, 4),
                    "next_compound": next_comp,
                    "next_slope_assumed": assumed,
                    "compound": event.compound.value,
                    "pit_loss_s": PIT_LOSS_S,  # context only; cancels in the decision
                },
            )
        ]
