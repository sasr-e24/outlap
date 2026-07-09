"""Pit-window and undercut models, plus track geometry.

These assert *directional* behaviour we can reason about from first principles,
not memorised outputs -- a model that merely runs would still fail these.
"""

import asyncio
import math

from outlap import circuit
from outlap.engine import Engine
from outlap.events import PositionSample, TelemetrySample, TrackOutline
from outlap.fixtures import build_synthetic_race
from outlap.models.undercut import _phi
from outlap.sources.replay import ReplaySource
from outlap.state import build_state


def _run(laps=40):
    engine = Engine(ReplaySource.from_event_log(build_synthetic_race(total_laps=laps)))
    asyncio.run(engine.run())
    return engine


# ---- geometry ---------------------------------------------------------------


def test_circuit_is_a_closed_ring():
    pts = circuit.outline()
    assert len(pts) == circuit.OUTLINE_POINTS
    # last point should be adjacent to the first (curve closes on itself)
    gap = math.dist(pts[0], pts[-1])
    span = max(p[0] for p in pts) - min(p[0] for p in pts)
    assert gap < span * 0.05


def test_speed_is_lower_in_corners_than_on_straights():
    """Speed comes from local curvature, so the tightest point must be slowest."""
    us = [i / 400 for i in range(400)]
    radii = [circuit._menger_radius(u) for u in us]
    tightest = us[min(range(len(us)), key=lambda i: radii[i])]
    openest = us[max(range(len(us)), key=lambda i: radii[i])]
    assert circuit.speed_at(tightest) < circuit.speed_at(openest)


def test_telemetry_channels_in_range():
    for i in range(200):
        t = circuit.telemetry_at(i / 200)
        assert circuit.SPEED_MIN <= t["speed"] <= circuit.SPEED_MAX
        assert 0 <= t["throttle"] <= 100 and 0 <= t["brake"] <= 100
        assert 1 <= t["gear"] <= 8
        # a car cannot be on throttle and brake simultaneously
        assert t["throttle"] == 0 or t["brake"] == 0


# ---- positions flow through the fold ---------------------------------------


def test_state_tracks_outline_and_car_positions():
    state = build_state(build_synthetic_race(total_laps=10))
    assert len(state.track_outline) == circuit.OUTLINE_POINTS
    cars = state.cars()
    assert len(cars) == 6
    for c in cars:
        assert c["x"] is not None and c["speed"] is not None


def test_cars_are_spread_around_the_track():
    """Different drivers are at different points on track, not stacked."""
    log = [e for e in build_synthetic_race(total_laps=10) if e.sim_time <= 500]
    state = build_state(log)
    coords = {(round(c["x"]), round(c["y"])) for c in state.cars()}
    assert len(coords) > 1, "all cars at the same point -- positions are not per-driver"


def test_positions_disabled_when_dt_zero():
    log = build_synthetic_race(total_laps=10, position_dt=0)
    assert not any(isinstance(e, (PositionSample, TelemetrySample)) for e in log)
    assert any(isinstance(e, TrackOutline) for e in log)


# ---- pit window -------------------------------------------------------------


def _preds(engine, model, metric):
    return [p for p in engine.ledger.rows if p.model == model and p.metric == metric]


def test_pit_window_predictions_emitted():
    rows = _preds(_run(), "pit_window", "laps_to_optimal_stop")
    assert rows, "expected pit_window predictions"
    assert all("extend_deltas_s" in p.payload for p in rows)
    assert all(p.payload["open"] == (p.value == 0) for p in rows)


def test_pit_loss_cancels_out_of_the_decision():
    """Pit loss is paid once whichever lap you box, so it must not appear in the
    cost function at all. If it ever creeps back in, this fails."""
    import inspect

    from outlap.models import pit_window as pw

    src = inspect.getsource(pw.cost_of_extending)
    assert "PIT_LOSS" not in src, "pit loss must not influence box-now-vs-extend"

    # and doubling it changes nothing about any prediction
    before = [(p.driver, p.value) for p in _preds(_run(), "pit_window", "laps_to_optimal_stop")]
    orig = pw.PIT_LOSS_S
    pw.PIT_LOSS_S = orig * 2
    try:
        after = [(p.driver, p.value) for p in _preds(_run(), "pit_window", "laps_to_optimal_stop")]
    finally:
        pw.PIT_LOSS_S = orig
    assert before == after


def test_equal_slopes_put_the_stop_at_half_distance():
    from outlap.models.pit_window import cost_of_extending

    R, s = 40, 0.06
    costs = [cost_of_extending(k, 0, R, s, s) for k in range(R + 1)]
    assert min(range(len(costs)), key=lambda k: costs[k]) == R // 2


def test_softer_current_tyre_pulls_the_stop_earlier():
    from outlap.models.pit_window import cost_of_extending

    R = 40

    def opt(s_now, s_next):
        c = [cost_of_extending(k, 0, R, s_now, s_next) for k in range(R + 1)]
        return min(range(len(c)), key=lambda k: c[k])

    assert opt(0.11, 0.04) < opt(0.06, 0.06) < opt(0.04, 0.11)


def test_laps_to_optimal_stop_counts_down_within_a_stint():
    """As the ideal stop lap approaches, 'laps until you should box' shrinks."""
    engine = _run()
    rows = [
        p
        for p in _preds(engine, "pit_window", "laps_to_optimal_stop")
        if p.driver == "VER" and p.payload["compound"] == "MEDIUM"
    ]
    assert len(rows) >= 6
    ks = [p.value for p in rows]
    assert ks[0] > ks[-1], f"expected countdown, got {ks[:8]}"
    assert ks[-1] == 0, "by the end of the stint the window should be open"


# ---- undercut ---------------------------------------------------------------


def test_undercut_probability_is_a_probability():
    rows = _preds(_run(), "undercut", "p_undercut")
    assert rows, "expected undercut predictions"
    assert all(0.0 <= p.value <= 1.0 for p in rows)
    assert all(p.payload["defender"] != p.driver for p in rows)


def test_undercut_falls_as_gap_grows():
    """P(undercut) is monotonically decreasing in the gap to the car ahead."""
    from outlap.models.undercut import SIGMA_S

    delta = 1.5
    ps = [_phi((delta - gap) / SIGMA_S) for gap in (0.2, 0.8, 1.5, 2.5)]
    assert ps == sorted(ps, reverse=True)
    # and a gap exactly equal to the advantage is a coin flip
    assert abs(_phi(0.0) - 0.5) < 1e-9


def test_undercut_only_within_range():
    from outlap.models.undercut import MAX_GAP_S

    for p in _preds(_run(), "undercut", "p_undercut"):
        assert 0 < p.payload["gap_s"] <= MAX_GAP_S
