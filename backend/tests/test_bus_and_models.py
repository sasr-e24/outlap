"""Bus fan-out and the deg model worker."""

import asyncio

from outlap.bus import EventBus
from outlap.events import Compound, Event, LapCompleted, Prediction
from outlap.engine import Engine
from outlap.fixtures import build_synthetic_race
from outlap.models.deg import DegFitter, _ols
from outlap.sources.replay import ReplaySource
from outlap.state import RaceState


def test_bus_delivers_to_base_subscriber():
    bus = EventBus()
    got = []

    async def sink(e: Event):
        got.append(e)

    bus.subscribe(Event, sink)
    asyncio.run(bus.publish(LapCompleted(sim_time=1.0, driver="VER", lap_number=1)))
    assert len(got) == 1 and got[0].driver == "VER"


def test_bus_type_filtering():
    bus = EventBus()
    laps, preds = [], []

    async def lap_sink(e):
        laps.append(e)

    async def pred_sink(e):
        preds.append(e)

    bus.subscribe(LapCompleted, lap_sink)
    bus.subscribe(Prediction, pred_sink)
    asyncio.run(bus.publish(LapCompleted(sim_time=1, driver="NOR", lap_number=1)))
    asyncio.run(bus.publish(Prediction(sim_time=1, model="deg", driver="NOR", metric="x", value=1)))
    assert len(laps) == 1 and len(preds) == 1


def test_ols_recovers_known_slope():
    xs = [0, 1, 2, 3, 4, 5]
    ys = [10 + 0.5 * x for x in xs]
    slope, intercept, stderr = _ols(xs, ys)
    assert abs(slope - 0.5) < 1e-9
    assert abs(intercept - 10) < 1e-9
    assert stderr < 1e-6


def test_deg_fitter_recovers_positive_deg():
    """The fixture bakes in HARD deg = 0.04 s/lap; the fitter should find deg > 0."""
    engine = Engine(ReplaySource.from_event_log(build_synthetic_race(total_laps=40)))
    asyncio.run(engine.run())
    deg = engine.ledger.latest_by_driver("deg", "deg_slope_s_per_lap")
    assert deg, "expected deg predictions to be logged"
    # every driver's fitted deg slope should be positive (tyres get slower with age)
    for drv, p in deg.items():
        assert p.value > 0, f"{drv} deg slope not positive: {p.value}"


def test_predictions_logged_to_ledger():
    engine = Engine(ReplaySource.from_event_log(build_synthetic_race(total_laps=30)))
    asyncio.run(engine.run())
    assert len(engine.ledger.rows) > 0
    assert all(isinstance(r, Prediction) for r in engine.ledger.rows)
