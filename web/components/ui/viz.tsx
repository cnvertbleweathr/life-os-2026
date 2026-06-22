/* Lightweight data-viz primitives for the Almanac system. */

import type { ReactNode } from "react";

export function Sparkline({
  data,
  w = 120,
  h = 32,
  stroke = "currentColor",
  fill = "none",
  sw = 1.6,
  dot = false,
}: {
  data: number[];
  w?: number;
  h?: number;
  stroke?: string;
  fill?: string;
  sw?: number;
  dot?: boolean;
}) {
  if (!data.length) return null;
  const max = Math.max(...data, 1);
  const min = Math.min(...data, 0);
  const span = max - min || 1;
  const step = w / Math.max(data.length - 1, 1);
  const pts = data.map((v, i) => [
    i * step,
    h - ((v - min) / span) * (h - 4) - 2,
  ]);
  const d = pts
    .map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1))
    .join(" ");
  const area = fill !== "none" ? `${d} L ${w} ${h} L 0 ${h} Z` : null;

  return (
    <svg
      width={w}
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      style={{ display: "block", overflow: "visible" }}
    >
      {area && (
        <path d={area} fill={fill} stroke="none" opacity="0.18" />
      )}
      <path
        d={d}
        fill="none"
        stroke={stroke}
        strokeWidth={sw}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {dot && pts.length > 0 && (
        <circle
          cx={pts[pts.length - 1][0]}
          cy={pts[pts.length - 1][1]}
          r={sw + 1}
          fill={stroke}
        />
      )}
    </svg>
  );
}

export function MiniBars({
  data,
  w = 320,
  h = 90,
  color = "currentColor",
  gap = 4,
  radius = 1,
}: {
  data: number[];
  w?: number;
  h?: number;
  color?: string;
  gap?: number;
  radius?: number;
}) {
  const max = Math.max(...data, 1);
  const bw = (w - gap * (data.length - 1)) / data.length;
  return (
    <svg
      width={w}
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      style={{ display: "block" }}
    >
      {data.map((v, i) => {
        const bh = (v / max) * (h - 2);
        return (
          <rect
            key={i}
            x={i * (bw + gap)}
            y={h - bh}
            width={bw}
            height={Math.max(bh, v > 0 ? 2 : 0)}
            rx={radius}
            fill={color}
            opacity={v === 0 ? 0.16 : 1}
          />
        );
      })}
    </svg>
  );
}

export function Donut({
  value,
  size = 56,
  sw = 5,
  color = "currentColor",
  track = "rgba(0,0,0,0.1)",
  children,
}: {
  value: number;
  size?: number;
  sw?: number;
  color?: string;
  track?: string;
  children?: ReactNode;
}) {
  const r = (size - sw) / 2;
  const c = 2 * Math.PI * r;
  const off = c * (1 - Math.max(0, Math.min(1, value)));
  return (
    <div style={{ position: "relative", width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={track}
          strokeWidth={sw}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={sw}
          strokeDasharray={c}
          strokeDashoffset={off}
          strokeLinecap="round"
        />
      </svg>
      {children && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "grid",
            placeItems: "center",
          }}
        >
          {children}
        </div>
      )}
    </div>
  );
}
