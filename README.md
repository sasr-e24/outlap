# OUTLAP — F1 Live Pit Wall

The pit wall fans don't have: a live **predictive** layer on top of F1 timing —
tyre degradation fitted in real time, pit windows and undercut probabilities
before they happen, and Monte Carlo race odds updating every lap.

> **Replay-first, real-time-ready.** Every data source (replay, OpenF1 live, raw
> SignalR) implements one interface and emits the same normalized events.
> Downstream code cannot tell replay from live — going live is a config change
> plus one adapter, not a rewrite.

This repository is **Phase 0 (skeleton)** of the plan in [`docs/PLAN.md`](docs/PLAN.md):
the event-sourced spine, a working replay engine, a first model (live tyre-deg
fitter) wired end-to-end, a FastAPI + WebSocket layer, and a Next.js Race-HQ
timing tower. It runs with **no network and no paid data** on a deterministic
synthetic race, and loads real sessions via FastF1 when you want them.

## What works today (P0)

- **Normalized event stream** (`LapCompleted`, `PitEntry/Exit`, `StintChange`,
  `GapUpdate`, `RaceControl`, `Weather`, `TeamRadio`, `Prediction`).
- **In-process async event bus** (asyncio pub/sub → Redis later, same interface).
- **Event-sourced, forkable race state** — current state is a fold over the event
  log; `state.fork()` deep-copies for the what-if sandbox.
- **`ReplaySource`** — replays either the built-in synthetic fixture (offline) or
  a real **FastF1** session, paced at any speed.
- **`DegFitter` model** — continuous fuel-corrected lap-time-vs-tyre-age OLS per
  driver/compound, published with a 1σ uncertainty and logged to a predictions
  ledger (the seed of the public accuracy ledger).
- **FastAPI**: REST (`/api/state`, `/api/predictions/{model}/{metric}`) +
  WebSocket (`/ws`) pushing live tower + prediction deltas.
- **Next.js Race HQ**: dark pit-wall timing tower with tyre, gap, pit and live
  deg chips; data-age always visible.
- **13 passing tests** including the core invariant *replay-through-the-bus ==
  direct fold*, *deg fitter recovers the fixture's built-in degradation*, and a
  pinned WebSocket frame contract (a missing field fails the build, not the UI).
- **CI** runs backend `pytest` plus frontend `tsc --noEmit` and `next build`.

## Quick start

### Backend
```bash
cd backend
pip install -e .            # core: fastapi + uvicorn
python -m outlap            # replay the synthetic race, print the final tower + deg fit
pytest                      # 13 tests, no network needed
uvicorn outlap.api:app --reload   # serve REST + WS on :8000
```

Real replay (optional heavy deps):
```bash
pip install -e ".[fastf1]"
python -m outlap --fastf1 2024 "Abu Dhabi" R
# or drive the API from a real session:
OUTLAP_SOURCE=fastf1 OUTLAP_FF1_YEAR=2024 OUTLAP_FF1_GP="Abu Dhabi" \
  uvicorn outlap.api:app
```

### Frontend
```bash
cd frontend
npm install
npm run dev                 # http://localhost:3000, connects to ws://localhost:8000/ws
```
Point it elsewhere with `NEXT_PUBLIC_OUTLAP_WS`.

## Layout
```
backend/   FastAPI + engine + models (Python, dependency-light core)
  outlap/
    events.py      normalized event types
    bus.py         async event bus
    state.py       event-sourced, forkable RaceState (the architectural heart)
    engine.py      source -> bus -> state -> models -> ledger wiring
    sources/       DataSource port + ReplaySource (synthetic + FastF1) adapters
    models/        ModelWorker base + DegFitter (worked example)
    fixtures.py    deterministic synthetic race (offline demo/CI)
    api.py         REST + WebSocket
frontend/  Next.js Race-HQ timing tower (TypeScript/React)
docs/      PLAN.md (full feature plan), ARCHITECTURE.md, ROADMAP.md
```

## Honesty notes (carried over from the plan)
Everything predicted is **inferred** from public timing (lap times, gaps, stints)
— never team telemetry (fuel, engine modes, tyre temps are not in any public
feed). Public feeds run seconds behind broadcast, so the UI always shows data
age and never claims to beat TV. Every published probability is stored and will
be scored (Brier + calibration) on the Models page — predictions are honestly
probabilistic, with published calibration, not a pretend team strategy computer.

## Status
P0 skeleton. See [`docs/ROADMAP.md`](docs/ROADMAP.md) for P1–P5.

Verified locally: `pytest` 13/13 green, `python -m outlap` replays the fixture,
`tsc --noEmit` clean, `next build` clean (Next 16 / React 19 — pinned to the
patched line; two moderate transitive advisories remain with no upstream fix).

Licensed MIT.
