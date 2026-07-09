# OUTLAP — F1 Live Pit Wall: Feature Plan & Architecture

**Working name:** OUTLAP — undercuts are won and lost on the out-lap, which is exactly the moment this app exists for. (Alternates considered: Delta Zero — pit-wall radio call for "push flat out to the stop", but a sim-racing company uses it; BoxBox — taken three times over; Clean Air.)
**One-liner:** The pit wall fans don't have — a live *predictive* layer on top of F1 timing: tire degradation fitted in real time, pit windows and undercut probabilities before they happen, and Monte Carlo race outcome odds updating every lap.
**Positioning:** f1-dash and MultiViewer *describe* the race. Existing strategy sims (TUMFTM, PITWALL, F1 StratLab) run *before* or *outside* the race. Nothing public combines live timing with a continuously updating probability engine. That's the gap.
**Dual purpose:** fan product + engineering portfolio for F1 team applications. Every model ships with a validation writeup and a public accuracy ledger.

---

## 1. Data reality (what we can and cannot know)

| Source | What it gives | Cost | Live? |
|---|---|---|---|
| **OpenF1 API** | Car telemetry ~3.7 Hz (speed/throttle/brake/gear/RPM), gaps & intervals every ~4 s, stints, pit events, race control, weather, radio | Free historical (2023+); **paid tier for real-time** (WebSocket/MQTT) | Yes (paid) |
| **FastF1 (Python)** | Deepest telemetry + timing, tire data, weather; excellent for model training | Free | No — post-session only (can *record* live, analyze after) |
| **F1 SignalR feed (raw)** | The official live timing stream itself — what the F1 app, f1-dash, and FastF1's recorder all consume | Free | Yes |
| **Jolpica (Ergast successor)** | Results, standings, schedules back decades | Free | No |

**What "raw SignalR" means:** F1 streams its live timing from `livetiming.formula1.com` using SignalR (a Microsoft push protocol over WebSockets). The endpoint is publicly reachable — you subscribe to topics like TimingData, CarData.z, Position.z and get a compressed JSON stream. Free, but **unofficial and undocumented**: message formats can change without notice, streams need decompressing and stitching, and there's no support if it breaks mid-race. OpenF1's paid tier is essentially "someone else runs that ingestion and hands you a clean, documented, stable API."

**Not available in any public source** (teams have it, we don't): fuel load, engine modes, actual tire wear/temps, driver instructions. Everything we predict is inferred from lap times, gaps, and stint data — the plan is to be *honestly probabilistic* and publish calibration, not pretend to be a team strategy computer.

**Latency honesty:** public feeds run seconds behind the broadcast (and broadcast itself is delayed). The UI always shows data age. We never claim to beat TV.

---

## 2. Feature set

### Pillar A — Live Pit Strategy Engine (the core)
- **Weekend context pipeline (deg is track-specific — seed before lights out):** tire behavior differs every race, so the race model never starts cold. FP1–FP3 long runs are auto-extracted (stint detection, push-laps and traffic-compromised laps filtered out) to fit compound-specific deg priors for *this* track in *this* weekend's conditions; quali provides the low-fuel pace anchor each driver's fuel correction hangs off. Caveats handled explicitly: FP fuel loads and engine modes are unknown (teams sandbag), and track evolution + temperature shift between Saturday and Sunday — so FP-derived curves enter as *priors with uncertainty*, then get Bayesian-updated by real race laps from lap 1. Prior track history (2023+) backstops weekends with wet or disrupted practice.
- **Live tire deg model per driver/compound:** fuel-corrected lap times fitted continuously (linear + cliff detection); deg curves drawn on each driver's stint.
- **Pit window detection:** optimal stop-lap range per driver given deg, pit loss for this track, and the traffic they'd rejoin into. Highlighted on the timing tower *before* it happens.
- **Undercut/overcut calculator:** for each attacker–defender pair within range: time delta needed, P(undercut works), how many laps the window stays open.
- **Box now vs extend:** projected race-time delta of pitting this lap vs +1…+5 laps.
- **Strategy tree:** viable remaining strategies per driver (compound sequences), pruned live as options expire.

### Pillar B — Race Outcome Probability Engine
- **Monte Carlo race sim** (thousands of race futures re-run every lap): P(win), P(podium), P(points), expected finish ± confidence for every driver.
- **Position probability matrix:** driver × finishing-position heatmap.
- **Safety car model:** per-track SC/VSC probability, and **SC-conditional outcomes** — "if SC comes out now, who gains?" (the single most game-changing strategic variable).
- **Win probability timeline:** the sports-betting-style live win-prob chart that basically doesn't exist for F1.
- **Championship swing:** live WDC/WCC points impact of the current running order.

### Pillar C — What-If Strategist Sandbox
- **Fork the live race:** grab the current race state, make your call ("pit Norris now, hards"), and the sim projects your outcome next to reality.
- **Scored afterwards:** post-race, your calls vs the team's actual calls — "you'd have finished P3, Ferrari got P5." Shareable card.
- **Pre-race strategy builder:** build strategies from practice-session deg data before lights out.

### Pillar D — Driver Performance Truth-Teller
- **Corrected pace:** fuel- and tire-age-corrected lap times — who is *actually* fastest right now, not who leads.
- **Clean-air pace estimate** vs traffic-compromised laps.
- **Stint quality & consistency scores;** teammate deltas normalized for tire age and fuel.
- **Quali vs race pace conversion** per driver/track.

### Pillar E — Race Signal Intelligence (radio + race control interpreter)
The race constantly *announces* things that will change its outcome — team radio, race control messages, weather bulletins — and no tracker turns them into structured inputs. This pillar does. Design rule: **the AI classifies, it never predicts.** A language model tags what happened; the *consequences* are computed by the same statistical models as everything else. Keeps the LLM as a sensor, not an oracle — and keeps every probability explainable.

- **Pipeline:** team radio audio (OpenF1 `team_radio` clips) → local Whisper transcription (free, open-source) → lightweight classifier (small local/free LLM, keyword rules as fallback) → tagged `SignalEvent` on the bus.
- **Signal taxonomy (v1):** box call / strategy intent, damage report, grip or deg complaint, tire warm-up issue, team orders, energy/derating trouble (2026-relevant), penalty or investigation (from race control), weather call.
- **Consequence mapping:** each tag adjusts model inputs, not outcomes directly — a damage report widens that driver's pace-variance and triggers anomaly watch; "box this lap" spikes pit probability; an investigation attaches a conditional penalty scenario to the MC sim; a rain call activates crossover-lap logic.
- **UI:** a live signal feed where every entry shows the raw message, its tag, and the model effect it had — e.g. *"SAI radio: 'something broken, front end' → DAMAGE → pace σ widened, P(podium) 22% → 14%"*. This becomes the app's most screenshot-able element.
- **Honesty caveats:** the feed only carries radio clips F1 publishes (curated, delayed by up to a couple of minutes) — so signals *refine* predictions, they're never load-bearing; sarcasm/code-speak ("plan C" means nothing without team context) gets a confidence score and low-confidence tags are displayed but not applied.

### Later-phase features (parked, architecture accommodates them)
- **Battle forecast:** time-to-catch, laps until attack range, P(overtake) weighted by track overtaking difficulty.
- **Anomaly detector:** sudden pace loss classified — deg cliff vs damage vs traffic.
- **Weather strategy:** rain windows + slick↔inter crossover-lap estimation.
- **Race-control correlation:** investigations/penalties folded into probabilities.
- **Auto post-race strategy report** (generated page/PDF per race).
- **Alerts:** push/Discord — "undercut window opening on Piastri, ~3 laps."
- **Replay library:** any 2023+ race rewatchable with the full prediction layer (also the demo mode).
- **Public model accuracy ledger:** Brier scores and calibration plots per race — portfolio gold.
- **Embeddable widgets / second-screen companion mode.**

---

## 3. UI / UX concept

**Aesthetic:** pit-wall, not fan-site. Dark, dense, information-hierarchical — closer to a trading terminal than a sports app. Data age always visible.

**Views:**
1. **Race HQ (default, live/replay):** enhanced timing tower on the left — each driver row carries prediction chips (pit window ⏱, undercut threat ⚠, P(podium)). Center: track map + win-prob timeline. Right: strategy panel for the selected driver (deg curve, box-now-vs-extend, strategy tree). Every driver row expands to a deep-dive.
2. **Strategy Lab:** the what-if sandbox. Race state snapshot + your decisions vs reality, side by side.
3. **Drivers:** truth-teller comparisons, stint analytics, corrected-pace leaderboard.
4. **Replays:** pick any race since 2023, scrub/play at 1×–30×, full prediction layer running.
5. **Models:** public accuracy ledger + short methodology notes per model (the portfolio page, disguised as transparency).

**UX principles:** everything glanceable in second-screen use (people watch TV simultaneously); probabilities as bars/chips, never raw decimals alone; one-tap from "who's winning" to "why the model thinks so" (drill into the deg fit behind any prediction — explainability as a feature).

---

## 4. Architecture

```
            ┌─────────────────────────────────────────────────────┐
            │                   DATA SOURCE ADAPTERS               │
            │  ReplaySource      OpenF1LiveSource   SignalRSource  │
            │  (FastF1 cache /   (paid WS/MQTT)     (raw feed,     │
            │   recorded feeds)                      later)        │
            └───────────────┬─────────────────────────────────────┘
                            ▼  common interface: normalized event stream
            ┌─────────────────────────────────────────────────────┐
            │  INGESTION — validate, dedupe, timestamp, publish    │
            │  events: LapCompleted, PitEntry/Exit, StintChange,   │
            │  GapUpdate, TelemetrySample, RaceControl, Weather,   │
            │  TeamRadio (audio clip refs)                         │
            └───────────────┬─────────────────────────────────────┘
                            ▼ event bus (asyncio in-proc → Redis later)
            ┌─────────────────────────────────────────────────────┐
            │  RACE STATE (event-sourced)                          │
            │  canonical live state; rebuildable from event log;   │
            │  FORKABLE → powers replay AND what-if sandbox        │
            └───────┬───────────────────────────┬─────────────────┘
                    ▼                           ▼
            ┌───────────────────┐     ┌──────────────────────────┐
            │  MODEL WORKERS     │     │  PERSISTENCE             │
            │  • deg fitter      │     │  Postgres: events, laps, │
            │  • pit/undercut    │     │  predictions ledger      │
            │  • Monte Carlo sim │     │  Parquet/FastF1 cache:   │
            │  • SC model        │     │  bulk telemetry          │
            │  • truth-teller    │     └──────────────────────────┘
            │  • signal intel    │
            │    (Whisper + LLM  │
            │     tagger → bus)  │
            └───────┬───────────┘
                    ▼ predictions re-published to bus
            ┌─────────────────────────────────────────────────────┐
            │  API — FastAPI: REST (state, history, replays)       │
            │        WebSocket push (live deltas to clients)       │
            └───────────────┬─────────────────────────────────────┘
                            ▼
            ┌─────────────────────────────────────────────────────┐
            │  FRONTEND — Next.js/React, WS client, chart layer    │
            └─────────────────────────────────────────────────────┘
```

**Key decisions and why:**

1. **Ports-and-adapters data layer.** Every source (replay, OpenF1 live, raw SignalR) implements the same interface and emits the same normalized events. Downstream code cannot tell replay from live. This is what makes "replay-first, real-time-ready" true rather than aspirational — going live is a config change plus one adapter, not a rewrite.
2. **Event-sourced race state.** The race is a log of events; current state is a fold over that log. Buys us: deterministic replays, time-scrubbing, and **cheap forking for the what-if sandbox** (fork = copy state, inject synthetic PitEntry, continue simulating). This is the architectural heart of the app.
3. **Replay is not a dev crutch — it's a product feature and the validation harness.** The same engine powers the Replays view, demo mode, and CI: replay a race with known outcome, score every prediction the models made, fail the build if calibration regresses. (Very reviewable engineering for F1 team recruiters.)
4. **Compute budget:** MC sim vectorized in NumPy; target a full re-sim cycle < ~2 s per lap event for 20 drivers × few thousand futures. One modest VPS handles it — no distributed anything for v1.
5. **Stack:** Python backend (FastAPI + NumPy/pandas + FastF1 — plays to your strengths, and the F1 data ecosystem is Python), TypeScript/Next.js frontend, Postgres + parquet storage, single container deploy (Fly.io/Railway/Hetzner) behind a public URL.

---

## 5. Model notes (feasibility-checked)

- **Deg fitting:** fuel-corrected lap time vs tire age, per compound; robust linear fit + changepoint (cliff) detection. Seeded by the weekend context pipeline (FP long runs + quali anchor + track history priors); tightened as race laps accumulate. Single-stint data is noisy — always carry uncertainty, feed it into the MC sim rather than point estimates.
- **Signal intelligence:** all free-tier: Whisper (open-source, runs locally — a 15 s radio clip transcribes in ~1–2 s on CPU) + a small open model (Ollama) or free-tier API for tagging; race-control messages arrive as structured text already, so v1 is keyword rules with zero ML. Every applied signal is logged to the predictions ledger like any model output, so its accuracy is scored too (did DAMAGE tags actually precede pace loss?).
- **Undercut model:** deterministic core (out-lap + in-lap + fresh-tire delta vs track position) + noise from pit-stop-time distribution and traffic → probability, not verdict.
- **SC probability:** base rate per track from history, inflated by live signals (incidents, weather). Crude v1 is fine; it's the *conditional* outcomes that create the wow.
- **2026 regs caveat:** DRS is gone — overtaking now runs on **Overtake Mode** (extra electrical energy when within 1 s at detection), **Boost Mode** (manual energy deployment for attack/defense), and **active aero** (X-mode low drag / Z-mode high downforce, available every lap). Attack-range logic (within 1 s) survives, but battle modeling becomes energy-budget-based, and 2023–25 deg/pace priors transfer only partially. Models must be season-aware, weight current-season data heavily, and the accuracy ledger tells us honestly how well we're adapting. This is a feature of the writeup, not an embarrassment.
- **Prediction ledger:** every published probability is stored with timestamp + race outcome → Brier score + calibration plots per model per race, publicly on the Models page.

---

## 6. Build phases

| Phase | Scope | Exit criterion |
|---|---|---|
| **P0 — Skeleton** | Repo, adapters interface, ReplaySource on FastF1 data, event bus, race state, basic timing tower UI | Replay 2025 Abu Dhabi in browser at 10×, tower matches reality |
| **P1 — Strategy core** | Weekend context pipeline + deg fitter, pit windows, undercut calc, box-now-vs-extend (Pillar A) + first MC sim (Pillar B minimal) + race-control signals, rule-based (Pillar E lite) | On replays, pit windows flagged before actual stops; predictions logged |
| **P2 — Probability + polish** | Full Pillar B panels, win-prob timeline, Pillar D truth-teller, Race HQ UI complete | A stranger can follow a replayed race and understand the strategy story |
| **P3 — Sandbox + validation** | Pillar C what-if forking, full Pillar E (Whisper + LLM radio tagging, signal feed UI), accuracy ledger + calibration page, replay library | Ledger shows scored predictions across ≥10 replayed races; radio signals tagged on replays |
| **P4 — Go live** | OpenF1 paid feed (or SignalR adapter), deploy public, alerts | Runs through a real race weekend unattended |
| **P5+** | Later-phase feature list, battle forecast first | — |

**Costs (v1):** hosting ~$5–20/mo; OpenF1 real-time subscription only needed from P4; everything before that is free data.

**Risks:** SignalR/OpenF1 format changes (mitigated by adapter isolation + raw feed archiving); 2026 model transfer (mitigated by season-aware training + ledger); scope creep (mitigated by the phase table — P0–P2 is already a killer portfolio piece even if live never ships).
