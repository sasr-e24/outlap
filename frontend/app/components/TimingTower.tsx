"use client";

import type { TowerRow } from "../types";
import type { DegInfo } from "../useRaceSocket";

function fmtLap(t: number | null): string {
  if (t == null) return "—";
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return m > 0 ? `${m}:${s.toFixed(3).padStart(6, "0")}` : s.toFixed(3);
}

function fmtGap(row: TowerRow): string {
  if (row.position === 1) return "LEADER";
  if (row.gap_to_leader == null) return "—";
  return `+${row.gap_to_leader.toFixed(3)}`;
}

export default function TimingTower({
  rows,
  deg,
}: {
  rows: TowerRow[];
  deg: Record<string, DegInfo>;
}) {
  return (
    <table className="tower">
      <thead>
        <tr>
          <th className="pos">P</th>
          <th>Driver</th>
          <th>Tyre</th>
          <th className="num">Age</th>
          <th className="num">Last</th>
          <th className="num">Gap</th>
          <th className="num">Int</th>
          <th>Stops</th>
          <th>Deg (s/lap)</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const d = deg[row.driver];
          const degClass = d ? (d.slope < 0.05 ? "deg-good" : "deg-bad") : "";
          return (
            <tr key={row.driver}>
              <td className="pos num">{row.position}</td>
              <td className="drv">
                {row.in_pit ? <span className="pit">▸ </span> : null}
                {row.driver}
              </td>
              <td>
                <span className={`tyre ${row.compound}`}>{row.compound.slice(0, 1)}</span>
              </td>
              <td className="num">{row.tyre_age}</td>
              <td className="num">{fmtLap(row.last_lap_time)}</td>
              <td className="num">{fmtGap(row)}</td>
              <td className="num">
                {row.interval_ahead != null && row.position > 1
                  ? `+${row.interval_ahead.toFixed(3)}`
                  : "—"}
              </td>
              <td className="num">{row.pit_stops}</td>
              <td>
                {d ? (
                  <span className={`chip ${degClass}`}>
                    {d.slope >= 0 ? "+" : ""}
                    {d.slope.toFixed(3)}
                    {d.stderr != null ? ` ±${d.stderr.toFixed(3)}` : ""}
                  </span>
                ) : (
                  <span className="chip">fitting…</span>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
