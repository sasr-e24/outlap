"use client";

import type { Car, DegInfo, PitInfo, UndercutInfo } from "../types";

function Bar({ label, value, max, cls }: { label: string; value: number; max: number; cls: string }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="bar-row">
      <span className="bar-label">{label}</span>
      <div className="bar-track">
        <div className={`bar-fill ${cls}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="bar-val num">{Math.round(value)}</span>
    </div>
  );
}

export default function TelemetryPanel({
  car,
  deg,
  pit,
  undercut,
}: {
  car: Car | null;
  deg?: DegInfo;
  pit?: PitInfo;
  undercut?: UndercutInfo;
}) {
  if (!car) {
    return <div className="panel side">Select a driver.</div>;
  }
  return (
    <div className="panel side">
      <div className="side-head">
        <span className="drv big">{car.driver}</span>
        <span className={`tyre ${car.compound}`}>{car.compound.slice(0, 1)}</span>
        <span className="muted">P{car.position}</span>
      </div>

      <div className="speed num">
        {car.speed != null ? Math.round(car.speed) : "--"}
        <span className="unit">km/h</span>
      </div>
      <div className="gearrpm muted num">
        gear {car.gear ?? "--"} &middot; {car.rpm != null ? Math.round(car.rpm) : "--"} rpm
      </div>

      <Bar label="THR" value={car.throttle ?? 0} max={100} cls="thr" />
      <Bar label="BRK" value={car.brake ?? 0} max={100} cls="brk" />

      <div className="side-sec">Strategy</div>
      <div className="kv">
        <span>Deg</span>
        <span className="num">
          {deg ? `${deg.slope >= 0 ? "+" : ""}${deg.slope.toFixed(3)} s/lap` : "fitting…"}
          {deg?.stderr != null ? <span className="muted"> ±{deg.stderr.toFixed(3)}</span> : null}
        </span>
      </div>
      <div className="kv">
        <span>Pit window</span>
        <span>
          {pit ? (
            pit.open ? (
              <span className="chip box">BOX NOW</span>
            ) : (
              <span className="chip">
                box in {pit.lapsToStop} (lap {pit.optimalLap})
              </span>
            )
          ) : (
            <span className="chip">—</span>
          )}
        </span>
      </div>
      {pit?.assumed ? (
        <div className="caveat">
          New-set deg unknown — nobody has run the other compound yet, so it&apos;s assumed
          equal to the current one. The stop lap will move once real data arrives.
        </div>
      ) : null}
      <div className="kv">
        <span>Undercut</span>
        <span>
          {undercut ? (
            <span className={`chip ${undercut.p > 0.5 ? "deg-bad" : ""}`}>
              {(undercut.p * 100).toFixed(0)}% on {undercut.defender}
            </span>
          ) : (
            <span className="chip">not in range</span>
          )}
        </span>
      </div>
      {undercut ? (
        <div className="caveat">
          gap {undercut.gap.toFixed(2)}s vs {undercut.delta.toFixed(2)}s of fresh-tyre advantage.
          Ignores traffic on the rejoin.
        </div>
      ) : null}
    </div>
  );
}
