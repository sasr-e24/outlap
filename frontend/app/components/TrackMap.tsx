"use client";

import type { Car } from "../types";

const PAD = 0.06; // fraction of span kept as margin

export default function TrackMap({
  outline,
  cars,
  selected,
  onSelect,
}: {
  outline: [number, number][];
  cars: Car[];
  selected: string | null;
  onSelect: (drv: string) => void;
}) {
  if (!outline.length) {
    return <div className="panel map-empty">no track geometry</div>;
  }

  const xs = outline.map((p) => p[0]);
  const ys = outline.map((p) => p[1]);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const w = maxX - minX;
  const h = maxY - minY;
  const padX = w * PAD;
  const padY = h * PAD;

  // SVG's y axis points down; track coordinates point up. Flip about the mid-line
  // so corners aren't mirrored.
  const fy = (y: number) => minY + maxY - y;

  const d =
    outline.map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(1)},${fy(p[1]).toFixed(1)}`).join(" ") +
    " Z";

  const stroke = Math.max(w, h) / 90;
  const r = Math.max(w, h) / 55;

  return (
    <div className="panel map">
      <svg
        viewBox={`${minX - padX} ${minY - padY} ${w + 2 * padX} ${h + 2 * padY}`}
        preserveAspectRatio="xMidYMid meet"
      >
        <path d={d} className="track-line" strokeWidth={stroke} />
        {cars.map((c) => {
          if (c.x == null || c.y == null) return null;
          const cls = [
            "car",
            c.driver === selected ? "sel" : "",
            c.in_pit ? "inpit" : "",
            c.position === 1 ? "leader" : "",
          ]
            .filter(Boolean)
            .join(" ");
          return (
            <g
              key={c.driver}
              className={cls}
              transform={`translate(${c.x.toFixed(1)},${fy(c.y).toFixed(1)})`}
              onClick={() => onSelect(c.driver)}
            >
              <circle r={r} />
              <text y={-r * 1.7} fontSize={r * 2.1} textAnchor="middle">
                {c.driver}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
