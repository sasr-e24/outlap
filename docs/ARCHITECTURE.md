# Architecture (P0)

```
  DataSource (port)
  ├─ ReplaySource   ── synthetic fixture (offline)  ─┐
  └─ ReplaySource.from_fastf1 ── real session ───────┤  normalized events
     (OpenF1LiveSource / SignalRSource come at P4)    │
                                                      ▼
  Engine.run():  source.events() ─▶ EventBus.publish ─┬─▶ RaceState.apply()  (canonical, forkable)
                                                      ├─▶ ModelWorker.on_event() ─▶ Prediction ─▶ bus
                                                      └─▶ sinks (WS fan-out, PredictionLedger)
                                                             │
                                     FastAPI  REST /api/*  ◀─┘   WebSocket /ws ─▶ Next.js Race HQ
```

## Key decisions

1. **Ports-and-adapters data layer.** Every source implements `DataSource` and
   emits the same `Event` stream. Downstream code depends only on the port. This
   is what makes "replay-first, real-time-ready" real: swapping `ReplaySource`
   for a live adapter changes nothing downstream.

2. **Event-sourced race state.** The race is a log of events; `RaceState` is a
   deterministic fold (`apply`) over that log. This buys deterministic replays,
   time-scrubbing, and **cheap forking** for the what-if sandbox
   (`state.fork()` → inject a synthetic `PitEntry` → keep folding). Test
   `test_replay_engine_matches_direct_fold` pins the invariant.

3. **Models read state, publish predictions, never mutate.** `ModelWorker`
   subscribes to the bus, reads (never writes) `RaceState`, and emits
   `Prediction` events. Everything a model outputs is logged to the ledger and
   is therefore scoreable. This is the LLM-as-sensor discipline from Pillar E
   generalized to every model: consequences are computed by statistics, and
   every probability is explainable and replayable.

4. **Dependency-light core.** `events`, `bus`, `state`, `engine`, `fixtures`,
   `models` and the OLS deg fit are pure Python — no numpy/pandas — so tests and
   CI run instantly with no network. FastF1/pandas/numpy are an optional extra
   used only for real replays; the production deg path swaps in the vectorized
   NumPy fit + cliff detection behind the same `ModelWorker` interface.

5. **Bus is in-process now, Redis later.** `EventBus` is a minimal asyncio
   pub/sub with type-based subscription (subscribe to `Event` for the firehose).
   The interface is small enough to back with Redis Streams without touching
   publishers or subscribers.

## Why replay is a product feature, not a dev crutch
The same engine powers the Replays view, demo mode, **and** CI: replay a race
with a known outcome, score every prediction the models made, and (at P1+) fail
the build if calibration regresses. The synthetic fixture is the offline stand-in
for that harness today; `DegFitter` recovering the fixture's baked-in 0.04 s/lap
HARD degradation (`test_deg_fitter_recovers_positive_deg`) is the first rung.
