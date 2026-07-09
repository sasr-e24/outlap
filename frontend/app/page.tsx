"use client";

import { useState } from "react";
import { useRaceSocket } from "./useRaceSocket";
import TimingTower from "./components/TimingTower";
import TrackMap from "./components/TrackMap";
import TelemetryPanel from "./components/TelemetryPanel";

export default function RaceHQ() {
  const { state, cars, outline, deg, pit, undercut, connected, dataAge } = useRaceSocket();
  const [selected, setSelected] = useState<string | null>(null);
  const leader = cars.find((c) => c.position === 1)?.driver ?? null;
  const active = selected ?? leader;
  const car = cars.find((c) => c.driver === active) ?? null;

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
              <span>{state.circuit || "—"}</span>
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
        <>
          <div className="grid">
            <TrackMap
              outline={outline}
              cars={cars}
              selected={active}
              onSelect={setSelected}
            />
            <TelemetryPanel
              car={car}
              deg={active ? deg[active] : undefined}
              pit={active ? pit[active] : undefined}
              undercut={active ? undercut[active] : undefined}
            />
          </div>
          <TimingTower
            rows={state.tower}
            deg={deg}
            pit={pit}
            undercut={undercut}
            selected={active}
            onSelect={setSelected}
          />
        </>
      ) : (
        <p className="muted">Waiting for the race feed…</p>
      )}

      <p className="foot">
        Everything here is <em>inferred</em> from public timing — lap times, gaps, stints,
        positions — never team telemetry. Deg is a fuel-corrected lap-time slope vs tyre age
        with 1σ. The pit window compares boxing now against extending 1–5 laps; pit loss is
        paid either way, so it cancels. Undercut is a probability, not a verdict.
      </p>
    </div>
  );
}
