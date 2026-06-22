/* Monoline icon set — thin geometric strokes echoing the globe emblem. */

import type { CSSProperties } from "react";

const PATHS: Record<string, React.ReactNode> = {
  home: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <ellipse cx="12" cy="12" rx="3.4" ry="8.5" />
      <line x1="3.5" y1="12" x2="20.5" y2="12" />
      <path d="M5 7.2c4.6 2 9.4 2 14 0M5 16.8c4.6-2 9.4-2 14 0" />
    </>
  ),
  habits: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M8 12.3l2.6 2.6L16 9.2" />
    </>
  ),
  fitness: (
    <path d="M3 13h3.2l2-5 3 11 2.3-7 1.6 2.7H21" />
  ),
  reading: (
    <>
      <path d="M12 6.5C10 5 7 4.7 4 5.4v12.2c3-.7 6-.4 8 1.1 2-1.5 5-1.8 8-1.1V5.4c-3-.7-6-.4-8 1.1z" />
      <line x1="12" y1="6.5" x2="12" y2="19.7" />
    </>
  ),
  goals: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="4.6" />
      <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
    </>
  ),
  checkin: (
    <>
      <rect x="5" y="3.5" width="14" height="17" rx="1.5" />
      <line x1="8.5" y1="9" x2="15.5" y2="9" />
      <line x1="8.5" y1="12.5" x2="15.5" y2="12.5" />
      <line x1="8.5" y1="16" x2="12.5" y2="16" />
    </>
  ),
  music: (
    <>
      <line x1="9" y1="17" x2="9" y2="6.5" />
      <line x1="17" y1="14.5" x2="17" y2="5" />
      <path d="M9 6.5l8-1.5" />
      <ellipse cx="6.6" cy="17" rx="2.4" ry="2" />
      <ellipse cx="14.6" cy="14.5" rx="2.4" ry="2" />
    </>
  ),
  kglw: (() => {
    const pts = Array.from({ length: 9 }, (_, i) => {
      const a = (-90 + i * 40) * Math.PI / 180;
      return [+(12 + 9.2 * Math.cos(a)).toFixed(2), +(12 + 9.2 * Math.sin(a)).toFixed(2)];
    });
    const lines: React.ReactNode[] = [];
    for (let i = 0; i < 9; i++) for (let j = i + 1; j < 9; j++) {
      const consec = j === i + 1 || (i === 0 && j === 8);
      lines.push(
        <line key={`${i}-${j}`} x1={pts[i][0]} y1={pts[i][1]} x2={pts[j][0]} y2={pts[j][1]}
          strokeWidth={consec ? 0.95 : 0.62} />
      );
    }
    return <>{lines}</>;
  })(),
  shows: (
    <>
      <path d="M4 7.5h16v3a1.8 1.8 0 000 3.6v2.4H4v-2.4a1.8 1.8 0 000-3.6z" />
      <line x1="14.5" y1="7.5" x2="14.5" y2="16.5" strokeDasharray="1.4 1.8" />
    </>
  ),
  sports: (
    <>
      <rect x="3.5" y="7.5" width="17" height="11" rx="1.5" />
      <path d="M9 4.5l3 3 3-3" />
      <line x1="7" y1="21" x2="17" y2="21" />
    </>
  ),
  cfb: (
    <>
      <ellipse cx="12" cy="12" rx="8.5" ry="5.2" />
      <line x1="9.5" y1="12" x2="14.5" y2="12" />
      <path d="M11 10.6v2.8M12.2 10.3v3.4M13.4 10.6v2.8" />
    </>
  ),
  scenarios: (
    <>
      <path d="M5 19V9a3 3 0 013-3h6" />
      <path d="M19 5v10a3 3 0 01-3 3h-6" />
      <path d="M11 3l3 3-3 3M13 21l-3-3 3-3" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="6.5" />
      <line x1="16" y1="16" x2="20.5" y2="20.5" />
    </>
  ),
  play: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M10 8.5l5 3.5-5 3.5z" fill="currentColor" stroke="none" />
    </>
  ),
  arrow: (
    <>
      <line x1="4" y1="12" x2="19" y2="12" />
      <path d="M13 6l6 6-6 6" />
    </>
  ),
  pin: (
    <>
      <path d="M12 21c4-5 6.5-8.2 6.5-11A6.5 6.5 0 005.5 10c0 2.8 2.5 6 6.5 11z" />
      <circle cx="12" cy="10" r="2.3" />
    </>
  ),
};

export function OnsIcon({
  name,
  size = 18,
  stroke = 1.6,
  style,
  className,
}: {
  name: string;
  size?: number;
  stroke?: number;
  style?: CSSProperties;
  className?: string;
}) {
  const body = PATHS[name] || PATHS.goals;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={stroke}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={style}
      aria-hidden="true"
    >
      {body}
    </svg>
  );
}

export function GlobeMark({
  size = 40,
  stroke = "currentColor",
  sw = 1.4,
}: {
  size?: number;
  stroke?: string;
  sw?: number;
}) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" fill="none"
      stroke={stroke} strokeWidth={sw} strokeLinecap="round">
      <ellipse cx="24" cy="24" rx="21" ry="16" />
      <ellipse cx="24" cy="24" rx="8" ry="16" />
      <ellipse cx="24" cy="24" rx="15.5" ry="16" opacity="0.55" />
      <line x1="3" y1="24" x2="45" y2="24" />
      <path d="M6 15c11 4.5 25 4.5 36 0M6 33c11-4.5 25-4.5 36 0" />
    </svg>
  );
}
