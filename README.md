# OUTLAP — F1 Live Pit Wall

The pit wall fans don't have: a live **predictive** layer on top of F1 timing —
tyre degradation fitted in real time, pit windows and undercut probabilities
before they happen, and Monte Carlo race odds updating every lap.

> **Replay-first, real-time-ready.** Every data source (replay, OpenF1 live, raw
> SignalR) implements one interface and emits the same normalized events.
> Downstream code cannot tell replay from live — going live is a config change
> plus one adapter, not a rewrite.

This repo implements **P0 (the spine)** plus the first slice of **P1 (strategy
core)** from [`docs/PLAN.md`](docs/PLAN.md). It runs with **no network and no
paid data** on a deterministic synthetic race, and loads real sessions via FastF1.

## What works today

**Engine**
- Normalized event stream: `LapCompleted`, `PitEntry/Exit`, `StintChange`,
  `GapUpdate`, `TrackOutline`, `PositionSample`, `TelemetrySample`,
  `RaceControl`, `Weather`, `Prediction`.
- In-process async event bus (asyncio pub/sub → Redis later, same interface).
- Event-sourced, **forkable** race state — state is a fold over the event log;
  `state.fork()` deep-copies for the what-if sandbox.
- `ReplaySource` — replays the offline synthetic fixture *or* a real FastF1
  session, paced at any speed.

**Models** (each publishes to a predictions ledger, so each can be scored later)
- **Deg fitter** — continuous fuel-corrected lap-time-vs-tyre-age OLS per
  driver/compound, published with a 1σ standard error.
- **Pit window** — box now vs extend 1–5 laps. Pit loss is paid whichever lap
  you box, so it *cancels out of the decision*; the model minimises deg cost
  across the two stints. Reports laps-to-optimal-stop and the extend deltas.
- **Undercut** — `P(undercut) = Φ((fresh-tyre advantage − gap) / σ)` for every
  attacker/defender pair in range. A probability, not a verdict.

**UI (Race HQ)**
- Track map with cars moving around the circuit, click to inspect.
- Telemetry panel: speed, gear, rpm, throttle/brake bars.
- Timing tower with live deg, pit-window and undercut chips.
- Data age always visible; model caveats surfaced in the UI, not buried.

**Tests** — 27 passing, no network. They assert properties, not memorised
outputs: replay-through-the-bus equals a direct fold; the deg fitter recovers the
fixture's built-in degradation; equal deg slopes put the optimal stop at half
distance; a softer current tyre pulls the stop earlier; **pit loss cannot re-enter
the box-now-vs-extend cost function**; the WebSocket frame contract is pinned.

## Quick start

### Backend
```bash
cd backend
pip install -e .                  # core: fastapi + uvicorn, nothing heavy
python -m outlap                  # replay the synthetic race in the terminal
pytest                            # 27 tests, no network needed
uvicorn outlap.api:app --reload   # REST + WebSocket on :8000
```

Real replay (optional heavy deps):
```bash
pip install -e ".[fastf1]"
python -m outlap --fastf1 2024 "Abu Dhabi" R
OUTLAP_SOURCE=fastf1 OUTLAP_FF1_YEAR=2024 OUTLAP_FF1_GP="Abu Dhabi" \
  uvicorn outlap.api:app
```

### Frontend
```bash
cd frontend
npm install
npm run dev                       # http://localhost:3000
```
`OUTLAP_SPEED=1` for real time, `200` to watch a race finish in seconds.
Override endpoints with `NEXT_PUBLIC_OUTLAP_WS` / `NEXT_PUBLIC_OUTLAP_API`.

## API
| Route | Purpose |
|---|---|
| `GET /api/track` | circuit outline (static per session) |
| `GET /api/state` | timing tower + race context |
| `GET /api/cars` | positions + telemetry |
| `GET /api/predictions/{model}/{metric}` | latest model output per driver |
| `WS /ws` | `state`, `cars` and `prediction` frames |

## Layout
```
backend/outlap/
  events.py      normalized event types
  bus.py         async event bus
  state.py       event-sourced, forkable RaceState (the architectural heart)
  engine.py      source -> bus -> state -> models -> ledger wiring
  circuit.py     synthetic circuit geometry (speed from real curvature)
  fixtures.py    deterministic offline race, with car positions
  sources/       DataSource port + ReplaySource (synthetic + FastF1)
  models/        deg fitter, pit window, undercut
  api.py         REST + WebSocket
frontend/app/    Race HQ: track map, telemetry panel, timing tower
docs/            PLAN.md, ARCHITECTURE.md, ROADMAP.md
```

## Honesty notes
Everything predicted is **inferred** from public timing (lap times, gaps, stints,
positions) — never team telemetry. Fuel load, engine modes and real tyre
temperatures are in no public feed. Public feeds also run seconds behind
broadcast, so the UI always shows data age and never claims to beat TV.

The models are deliberately simple and say so. The pit window ignores track
position, rejoin traffic and safety-car probability. The undercut model assumes
the defender covers on the very next lap. Before anyone has run a second
compound, the pit window has no idea how the new set degrades and assumes it
matches the current one — the UI flags this. That gap is exactly what the plan's
weekend-context pipeline (practice long-run priors) is for.

Every published probability is stored in the predictions ledger with a timestamp,
so it can be scored (Brier + calibration) against the real outcome. Honestly
probabilistic with published calibration — not a pretend team strategy computer.

## Status
P0 complete; P1 partially in. See [`docs/ROADMAP.md`](docs/ROADMAP.md).

Verified locally: `pytest` 27/27, `python -m outlap` replays the fixture, live
`uvicorn` + WebSocket carries `state`/`cars`/`prediction` frames, `tsc --noEmit`
and `next build` clean (Next 16 / React 19). The FastF1 path compiles but is
**not** verified against a live session — the F1 API is unreachable from CI.

Licensed MIT.
