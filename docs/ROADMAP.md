# Roadmap

Mirrors the phase table in [PLAN.md](PLAN.md). ✅ = done in this repo.

| Phase | Scope | Exit criterion | Status |
|---|---|---|---|
| **P0 — Skeleton** | Adapters interface, ReplaySource, event bus, race state, timing tower UI | Replay a race in the browser; tower matches reality | ✅ engine + bus + state + ReplaySource (synthetic **and** FastF1) + FastAPI/WS + Next.js tower + 13 tests. First model (deg) wired as a worked example. |
| **P1 — Strategy core** | Weekend-context pipeline + deg fitter, pit windows, undercut calc, box-now-vs-extend + first MC sim + rule-based race-control signals | Pit windows flagged before actual stops on replays; predictions logged | ▶ deg fitter + predictions ledger already in place; next: pit-window & undercut workers, minimal MC sim |
| **P2 — Probability + polish** | Full Pillar B panels, win-prob timeline, truth-teller, Race HQ complete | A stranger can follow a replayed race | ☐ |
| **P3 — Sandbox + validation** | What-if forking UI, Whisper+LLM radio tagging, accuracy ledger + calibration page, replay library | Ledger scored across ≥10 replays; radio tagged | ☐ (fork primitive exists in `state.fork()`) |
| **P4 — Go live** | OpenF1 paid feed / SignalR adapter, deploy, alerts | Runs a real weekend unattended | ☐ |
| **P5+** | Later-phase features, battle forecast first | — | ☐ |

## Immediate next steps (P1)
1. `models/pit_window.py` — optimal stop-lap range from deg slope + track pit loss.
2. `models/undercut.py` — deterministic out/in-lap + fresh-tyre delta, + pit-time
   noise → P(undercut) per attacker/defender pair.
3. `models/monte_carlo.py` — vectorized (NumPy) per-lap re-sim → P(win/podium/points).
4. `sources` — record a real SignalR/OpenF1 stream to a replayable event log.
5. CI: replay N sessions, compute Brier score, gate on calibration regression.
