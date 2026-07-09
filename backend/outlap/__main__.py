"""CLI replay demo — proves the P0 loop with no network or heavy deps.

    python -m outlap                 # replay the synthetic fixture, print final tower
    python -m outlap --laps 30       # shorter race
    python -m outlap --fastf1 2024 "Abu Dhabi" R   # real replay (needs fastf1)
"""

from __future__ import annotations

import argparse
import asyncio

from .engine import Engine
from .fixtures import build_synthetic_race
from .sources.replay import ReplaySource


def _fmt_time(t):
    if t is None:
        return "     --"
    m, s = divmod(t, 60)
    return f"{int(m)}:{s:06.3f}" if m else f"  {s:6.3f}"


async def _run(source: ReplaySource) -> Engine:
    engine = Engine(source)
    await engine.run()
    return engine


def main() -> None:
    ap = argparse.ArgumentParser(prog="outlap")
    ap.add_argument("--laps", type=int, default=40)
    ap.add_argument("--fastf1", nargs=3, metavar=("YEAR", "GP", "SESSION"))
    args = ap.parse_args()

    if args.fastf1:
        year, gp, ses = args.fastf1
        source = ReplaySource.from_fastf1(int(year), gp, ses, speed=0.0)
    else:
        source = ReplaySource.from_event_log(build_synthetic_race(total_laps=args.laps))

    engine = asyncio.run(_run(source))
    s = engine.state

    print(f"\n  {s.circuit} — {s.session} — lap {s.current_lap}/{s.total_laps}")
    print("  " + "-" * 66)
    print(f"  {'P':>2}  {'DRV':<4} {'LAP':>3}  {'LAST':>9}  {'TYRE':<7} {'AGE':>3}  {'GAP':>8}")
    print("  " + "-" * 66)
    for row in s.timing_tower():
        print(
            f"  {row['position']:>2}  {row['driver']:<4} {row['lap']:>3}  "
            f"{_fmt_time(row['last_lap_time'])}  {row['compound']:<7} {row['tyre_age']:>3}  "
            f"{(row['gap_to_leader'] if row['gap_to_leader'] is not None else 0):>8.3f}"
        )
    print("  " + "-" * 66)

    deg = engine.ledger.latest_by_driver("deg", "deg_slope_s_per_lap")
    if deg:
        print("\n  Live deg fit (s/lap, current compound):")
        for drv, p in sorted(deg.items()):
            se = p.payload.get("slope_stderr")
            se_s = f" ±{se:.3f}" if se is not None else ""
            print(f"    {drv:<4} {p.payload['compound']:<7} {p.value:+.3f}{se_s}  (n={p.payload['n_points']})")

    print(f"\n  events folded: seq={s.last_seq}   predictions logged: {len(engine.ledger.rows)}\n")


if __name__ == "__main__":
    main()
