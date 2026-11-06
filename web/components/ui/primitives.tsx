import clsx from "clsx";
import type { ReactNode, CSSProperties } from "react";
import { GlobeMark } from "./icons";

// ── K — section label ────────────────────────────────────────────────────────
// Logbook Color: sentence case, 12px, no tracked caps (DESIGN.md "No Micro-Caps Rule").

export function K({
  children,
  color,
  className,
  style,
}: {
  children: ReactNode;
  color?: string;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <div
      className={clsx("font-sans", className)}
      style={{
        fontSize: 12,
        lineHeight: "16px",
        fontWeight: 500,
        color: color ?? "var(--muted)",
        ...style,
      }}
    >
      {children}
    </div>
  );
}

// ── Card ─────────────────────────────────────────────────────────────────────

export function Card({
  children,
  className,
  accent,
  accentColor,
  pad = 20,
  style,
}: {
  children: ReactNode;
  className?: string;
  accent?: boolean;
  accentColor?: string;
  pad?: number | string;
  style?: CSSProperties;
}) {
  return (
    <div
      className={clsx("bg-sheet border border-border rounded-card min-w-0", className)}
      style={{
        padding: pad,
        boxShadow: accent ? `inset 0 3px 0 ${accentColor ?? "var(--hue)"}` : undefined,
        ...style,
      }}
    >
      {children}
    </div>
  );
}

// ── PageHead ─────────────────────────────────────────────────────────────────
// Logbook Color page intro: title, the span it covers, one coach-voice paragraph.
// Right column: page actions above an optional pixel scene.

export function PageHead({
  title,
  titleSub,
  kicker,
  sub,
  right,
  scene,
}: {
  title: string;
  /** Lighter second part of the title, e.g. "— College Football". */
  titleSub?: string;
  /** The span line under the title (dates, week). */
  kicker?: ReactNode;
  /** The lede: one coach-voice paragraph. */
  sub?: ReactNode;
  right?: ReactNode;
  scene?: ReactNode;
}) {
  return (
    <div className="ons-pagehead flex justify-between items-start gap-6 mb-6">
      <div className="min-w-0" style={{ flex: "1 1 0" }}>
        <h1 className="font-sans font-semibold text-ink m-0" style={{ fontSize: 30, lineHeight: "36px", letterSpacing: "-0.01em" }}>
          {title}
          {titleSub && <span className="font-normal text-muted"> {titleSub}</span>}
        </h1>
        {kicker && <p className="text-[14px] text-muted mt-1 m-0">{kicker}</p>}
        {sub && <p className="text-[16px] leading-[25px] text-ink-2 mt-3 m-0" style={{ maxWidth: "68ch" }}>{sub}</p>}
      </div>
      {(right || scene) && (
        <div className="flex flex-col items-end gap-3" style={{ flex: scene ? "0 1 460px" : "none", minWidth: scene ? 300 : undefined }}>
          {right}
          {scene}
        </div>
      )}
    </div>
  );
}

// ── Stat — one figure in a StatBand ─────────────────────────────────────────

export function Stat({
  label,
  value,
  unit,
  accent,
  spark,
  last,
}: {
  label: string;
  value: string | number;
  unit?: string;
  accent?: boolean;
  spark?: ReactNode;
  last?: boolean;
}) {
  return (
    <div style={{ padding: "16px 18px", borderRight: last ? "none" : "1px solid var(--rule)" }}>
      <K>{label}</K>
      <div className="font-sans font-semibold mt-1" style={{ fontSize: 26, lineHeight: "32px", color: accent ? "var(--hue)" : "var(--ink)" }}>
        {value}
        {unit && <span className="font-mono font-normal ml-1" style={{ fontSize: 12, color: "var(--muted)" }}>{unit}</span>}
      </div>
      {spark ? <div className="mt-[10px] text-hue">{spark}</div> : <div className="h-8" />}
    </div>
  );
}

// ── StatBand — a row of Stat cells in one bordered card ─────────────────────

export function StatBand({ children }: { children: ReactNode }) {
  return (
    <div
      className="ons-band grid mb-6 bg-sheet border border-border rounded-card"
      style={{ gridTemplateColumns: `repeat(${Array.isArray(children) ? children.length : 1}, minmax(0, 1fr))` }}
    >
      {children}
    </div>
  );
}

// ── Pace badge — status pill ────────────────────────────────────────────────
// Untracked goals read "Not wired", never "behind" (critique problem 1).

const PACE_MAP: Record<string, [string, string, string]> = {
  on_track: ["var(--ok)", "var(--ok-ink)", "On track"],
  ahead:    ["var(--ok)", "var(--ok-ink)", "Ahead"],
  complete: ["var(--ok)", "var(--ok-ink)", "Complete"],
  at_risk:  ["var(--risk)", "var(--risk-ink)", "At risk"],
  behind:   ["var(--off)", "var(--off-ink)", "Behind"],
  unknown:  ["var(--none)", "var(--none-ink)", "Not wired"],
  binary:   ["var(--none)", "var(--none-ink)", "Logged"],
};

export function Pace({ status }: { status?: string | null }) {
  const [bg, fg, txt] = PACE_MAP[status ?? ""] ?? ["var(--none)", "var(--none-ink)", status ?? "—"];
  return (
    <span className="font-sans whitespace-nowrap inline-block" style={{ fontSize: 12, fontWeight: 500, lineHeight: "20px", padding: "0 8px", borderRadius: 4, background: bg, color: fg }}>
      {txt}
    </span>
  );
}

// ── Pill — filter toggle chip ───────────────────────────────────────────────

export function Pill({
  children,
  active,
  color = "var(--ink)",
  onClick,
  style,
}: {
  children: ReactNode;
  active?: boolean;
  color?: string;
  onClick?: () => void;
  style?: CSSProperties;
}) {
  return (
    <button
      className="ons-tap cursor-pointer font-sans"
      onClick={onClick}
      aria-pressed={active}
      style={{
        fontSize: 13,
        fontWeight: active ? 500 : 400,
        height: 28,
        border: `1px solid ${active ? color : "var(--border)"}`,
        background: active ? color : "var(--sheet)",
        color: active ? "var(--sheet)" : "var(--ink-2)",
        borderRadius: 6,
        padding: "0 10px",
        ...style,
      }}
    >
      {children}
    </button>
  );
}

// ── Watermark — faint globe in accent cards ──────────────────────────────────

export function Watermark({
  size = 290,
  opacity = 0.05,
  spin,
}: {
  size?: number;
  opacity?: number;
  /** Ignored: nothing spins in Logbook Color. Kept so existing callers compile. */
  spin?: boolean;
}) {
  return (
    <div
      className="absolute pointer-events-none text-green"
      style={{
        right: -50,
        top: -70,
        opacity,
      }}
    >
      <GlobeMark size={size} stroke="var(--hue)" sw={1} />
    </div>
  );
}

// ── Stub — honest empty state ────────────────────────────────────────────────

export function Stub({
  title,
  body,
}: {
  title: string;
  body?: string;
}) {
  return (
    <div className="grid place-items-center py-[90px] px-5 text-center">
      <div className="font-sans font-semibold text-[20px] text-ink">{title}</div>
      {body && (
        <p className="text-[13px] text-muted max-w-[380px] mt-2">{body}</p>
      )}
    </div>
  );
}

// ── Empty ────────────────────────────────────────────────────────────────────

export function Empty({
  message,
  detail,
}: {
  message: string;
  detail?: string;
}) {
  return (
    <div className="py-8 text-center">
      <p className="text-sm text-muted">{message}</p>
      {detail && <p className="text-xs text-faint mt-1">{detail}</p>}
    </div>
  );
}

// ── Loading ──────────────────────────────────────────────────────────────────

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="py-8 text-center">
      <p className="text-xs text-faint">{label}</p>
    </div>
  );
}

// ── ErrorState ───────────────────────────────────────────────────────────────

export function ErrorState({ message }: { message?: string }) {
  return (
    <div className="py-8 text-center">
      <p className="text-sm text-red">Couldn't load this.</p>
      {message && <p className="text-xs text-faint mt-1">{message}</p>}
    </div>
  );
}

// ── Legacy StatCard (used on Home page) ──────────────────────────────────────

export function StatCard({
  label,
  value,
  unit,
  accent = false,
}: {
  label: string;
  value: number | string | null | undefined;
  unit?: string;
  accent?: boolean;
}) {
  const display =
    value === null || value === undefined || value === "" ? "—" : String(value);
  return (
    <div className="bg-sheet border border-border rounded-card p-4">
      <p className="text-[12px] font-medium text-muted mb-2">
        {label}
      </p>
      <p
        className={clsx(
          "font-sans text-2xl font-semibold",
          accent ? "text-green" : "text-ink"
        )}
      >
        {display}
        {unit && (
          <span className="font-mono text-[12px] text-muted font-normal ml-1">
            {unit}
          </span>
        )}
      </p>
    </div>
  );
}

// ── SectionLabel (legacy, used on Home page) ─────────────────────────────────

export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <p className="text-[12px] font-medium text-muted mb-2">
      {children}
    </p>
  );
}

// ── PaceBadge (legacy alias) ─────────────────────────────────────────────────

export function PaceBadge({ status }: { status?: string | null }) {
  return <Pace status={status} />;
}

// ── PageHeader (legacy, used on Home page) ───────────────────────────────────

export function PageHeader({
  title,
  sub,
  right,
}: {
  title: string;
  sub?: string;
  right?: ReactNode;
}) {
  return (
    <div className="px-6 py-4 border-b border-border bg-sheet flex items-center justify-between">
      <div>
        <h1 className="text-xl font-semibold text-ink">{title}</h1>
        {sub && <p className="text-xs text-muted mt-0.5">{sub}</p>}
      </div>
      {right}
    </div>
  );
}
