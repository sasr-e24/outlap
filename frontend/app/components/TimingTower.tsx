"use client";

import type { DegInfo, PitInfo, TowerRow, UndercutInfo } from "../types";

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
  pit,
  undercut,
  selected,
  onSelect,
}: {
  rows: TowerRow[];
  deg: Record<string, DegInfo>;
  pit: Record<string, PitInfo>;
  undercut: Record<string, UndercutInfo>;
  selected: string | null;
  onSelect: (drv: string) => void;
}) {
  return (
    <div className="tower-scroll panel">
      <table className="tower">
        <thead>
          <tr>
            <th className="pos">P</th>
            <th>Driver</th>
            <th>Tyre</th>
            <th className="num">Age</th>
            <th className="num">Last</th>
            <th className="num">Gap</th>
            <th>Deg (s/lap)</th>
            <th>Pit window</th>
            <th>Undercut</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const d = deg[row.driver];
            const p = pit[row.driver];
            const u = undercut[row.driver];
            return (
              <tr
                key={row.driver}
                className={row.driver === selected ? "sel" : ""}
                onClick={() => onSelect(row.driver)}
              >
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
                <td>
                  {d ? (
                    <span className={`chip ${d.slope < 0.05 ? "deg-good" : "deg-bad"}`}>
                      {d.slope >= 0 ? "+" : ""}
                      {d.slope.toFixed(3)}
                    </span>
                  ) : (
                    <span className="chip">fitting…</span>
                  )}
                </td>
                <td>
                  {p ? (
                    p.open ? (
                      <span className="chip box">BOX</span>
                    ) : (
                      <span className="chip">in {p.lapsToStop}</span>
                    )
                  ) : (
                    <span className="chip">—</span>
                  )}
                </td>
                <td>
                  {u ? (
                    <span className={`chip ${u.p > 0.5 ? "deg-bad" : ""}`}>
                      {(u.p * 100).toFixed(0)}% {u.defender}
                    </span>
                  ) : (
                    <span className="chip">—</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
