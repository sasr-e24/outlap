"use client";

import { useRaceSocket } from "./useRaceSocket";
import TimingTower from "./components/TimingTower";

export default function RaceHQ() {
  const { state, deg, connected, dataAge } = useRaceSocket();

  return (
    <div className="wrap">
      <div className="header">
        <h1>
          OUT<span className="accent">LAP</span> &middot; RACE HQ
        </h1>
        <div className="meta">
          <span>
            <span className={`dot ${connected ? "on" : "off"}`} />
            {connected ? "live" : "reconnecting"}
          </span>
          {state && (
            <>
              <span>{state.circuit ? state.circuit : "—"}</span>
              <span>
                LAP {state.current_lap}/{state.total_laps || "?"}
              </span>
              <span className={`status-${state.track_status}`}>{state.track_status}</span>
              <span className="age">data age {dataAge.toFixed(1)}s</span>
            </>
          )}
        </div>
      </div>

      {state ? (
        <TimingTower rows={state.tower} deg={deg} />
      ) : (
        <p style={{ color: "var(--muted)" }}>Waiting for the race feed…</p>
      )}

      <p className="foot">
        Predictions shown are <em>inferred</em> from public timing only (lap times, gaps,
        stints) — never team telemetry. Deg = fuel-corrected lap-time slope vs tyre age,
        with 1σ. Replay-first: this same view runs live at P4 with no code change.
      </p>
    </div>
  );
}
