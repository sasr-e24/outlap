"""Event-sourced state is a deterministic fold — the architectural claim, tested."""

import asyncio

from outlap.engine import Engine
from outlap.events import Compound, LapCompleted, PitExit
from outlap.fixtures import build_synthetic_race
from outlap.sources.replay import ReplaySource
from outlap.state import build_state


def test_fold_is_deterministic():
    log = build_synthetic_race(total_laps=20, seed=7)
    s1 = build_state(log)
    s2 = build_state(log)
    assert s1.timing_tower() == s2.timing_tower()


def test_fixture_is_seeded_reproducible():
    assert build_synthetic_race(20, seed=7) == build_synthetic_race(20, seed=7)


def test_positions_are_a_permutation():
    log = build_synthetic_race(total_laps=25)
    state = build_state(log)
    positions = sorted(d.position for d in state.drivers.values())
    assert positions == list(range(1, len(positions) + 1))


def test_leader_gap_is_zero():
    state = build_state(build_synthetic_race(total_laps=25))
    tower = state.timing_tower()
    assert tower[0]["position"] == 1
    assert abs(tower[0]["gap_to_leader"] or 0.0) < 1e-6


def test_pit_stops_counted_and_compound_switched():
    state = build_state(build_synthetic_race(total_laps=40))
    for d in state.drivers.values():
        assert d.pit_stops == 1
        assert d.compound == Compound.HARD  # everyone ends on hards in the fixture


def test_replay_engine_matches_direct_fold():
    """Driving the fixture through source→bus→state must equal a direct fold."""
    log = build_synthetic_race(total_laps=30)
    direct = build_state(log)

    engine = Engine(ReplaySource.from_event_log(log))
    asyncio.run(engine.run())

    assert engine.state.timing_tower() == direct.timing_tower()
    assert engine.state.current_lap == direct.current_lap


def test_fork_is_independent():
    state = build_state(build_synthetic_race(total_laps=20))
    forked = state.fork()
    forked.apply(PitExit(sim_time=9999, driver="VER", lap_number=99, new_compound=Compound.SOFT))
    assert state.drivers["VER"].compound != Compound.SOFT
    assert forked.drivers["VER"].compound == Compound.SOFT
