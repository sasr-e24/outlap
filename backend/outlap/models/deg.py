"""Live tyre-degradation fitter (P1 core, wired in at P0 as a worked example).

Fits fuel-corrected lap time vs tyre age per driver, per compound, continuously
as laps arrive. v1 is a robust-ish ordinary least squares on the current stint —
enough to draw a deg curve and feed a slope (s/lap) into the pit/undercut and
Monte Carlo models. Single-stint data is noisy, so we always publish an
uncertainty (standard error of the slope), never a bare point estimate.

Pure-Python OLS keeps the core dependency-free; the production path swaps in the
NumPy vectorized fit + changepoint (cliff) detection described in the model notes.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from ..events import Compound, Event, LapCompleted, Prediction
from ..state import RaceState
from .base import ModelWorker

FUEL_EFFECT_PER_LAP = 0.055  # s/lap assumed fuel burn correction (season-tunable)
MIN_POINTS = 4


def _ols(xs: List[float], ys: List[float]) -> Tuple[float, float, float]:
    """Return (slope, intercept, slope_stderr) for y = slope*x + intercept."""
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, my, float("inf")
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = my - slope * mx
    resid = [y - (slope * x + intercept) for x, y in zip(xs, ys)]
    if n > 2:
        s2 = sum(r * r for r in resid) / (n - 2)
        stderr = (s2 / sxx) ** 0.5
    else:
        stderr = float("inf")
    return slope, intercept, stderr


class DegFitter(ModelWorker):
    name = "deg"

    def __init__(self, bus, state: RaceState):
        super().__init__(bus, state)
        # (driver, compound) -> list of (tyre_age, fuel_corrected_time)
        self._points: Dict[Tuple[str, Compound], List[Tuple[int, float]]] = {}

    async def on_event(self, event: Event) -> List[Prediction]:
        if not isinstance(event, LapCompleted):
            return []
        if event.lap_time is None or event.is_pit_lap or event.compound == Compound.UNKNOWN:
            return []

        # Fuel-correct to a full-fuel (lap-1) reference. Cars get lighter and
        # therefore faster as the race runs; we add that burn-off benefit back so
        # the remaining trend against tyre age is (mostly) pure degradation.
        fuel_corrected = event.lap_time + FUEL_EFFECT_PER_LAP * (event.lap_number - 1)
        key = (event.driver, event.compound)
        self._points.setdefault(key, []).append((event.tyre_age, fuel_corrected))

        pts = self._points[key]
        if len(pts) < MIN_POINTS:
            return []

        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        slope, intercept, stderr = _ols(xs, ys)

        stderr_out = round(stderr, 4) if stderr != float("inf") else None
        return [
            Prediction(
                sim_time=event.sim_time,
                model=self.name,
                driver=event.driver,
                metric="deg_slope_s_per_lap",
                value=round(slope, 4),
                payload={
                    "compound": event.compound.value,
                    "intercept_s": round(intercept, 3),
                    "slope_stderr": stderr_out,
                    "n_points": len(pts),
                    "tyre_age": event.tyre_age,
                },
            )
        ]
