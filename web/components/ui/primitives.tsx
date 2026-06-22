import clsx from "clsx";
import type { ReactNode, CSSProperties } from "react";
import { GlobeMark } from "./icons";

// ── K — mono kicker label ─────────────────────────────────────────────────

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
      className={clsx("font-mono uppercase", className)}
      style={{
        fontSize: 9.5,
        letterSpacing: "1.7px",
        color: color ?? "#736e5f",
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
  pad = 18,
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
      className={clsx("bg-surface border border-border rounded-card", className)}
      style={{
        padding: pad,
        borderTop: accent
          ? `2.5px solid ${accentColor ?? "#1d5536"}`
          : undefined,
        ...style,
      }}
    >
      {children}
    </div>
  );
}

// ── PageHead ─────────────────────────────────────────────────────────────────

export function PageHead({
  title,
  kicker,
  sub,
  right,
}: {
  title: string;
  kicker?: string;
  sub?: string;
  right?: ReactNode;
}) {
  return (
    <div className="flex justify-between items-end mb-[26px]">
      <div>
        {kicker && (
          <K color="#1d5536" style={{ marginBottom: 10 }}>
            {kicker}
          </K>
        )}
        <h1
          className="font-serif font-bold text-ink leading-none m-0"
          style={{ fontSize: 40, letterSpacing: "-0.8px" }}
        >
          {title}
        </h1>
        {sub && (
          <p className="text-[13.5px] text-muted mt-[9px]">{sub}</p>
        )}
      </div>
      {right}
    </div>
  );
}

// ── Stat — editorial stat-band cell ──────────────────────────────────────────

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
    <div
      style={{
        padding: "16px 18px",
        borderRight: last ? "none" : "1px solid #ebe5d8",
      }}
    >
      <K>{label}</K>
      <div
        className="font-serif font-semibold leading-none mt-2"
        style={{ fontSize: 30, color: accent ? "#1d5536" : "#232a22" }}
      >
        {value}
        {unit && (
          <span
            className="font-mono font-normal ml-1"
            style={{ fontSize: 11, color: "#a39d8c" }}
          >
            {unit}
          </span>
        )}
      </div>
      {spark ? (
        <div className="mt-[10px] text-green-bright">{spark}</div>
      ) : (
        <div className="h-8" />
      )}
    </div>
  );
}

// ── StatBand — wraps N Stat cells in the editorial band ──────────────────────

export function StatBand({ children }: { children: ReactNode }) {
  return (
    <div
      className="grid mb-7"
      style={{
        gridTemplateColumns: `repeat(${
          Array.isArray(children) ? children.length : 1
        }, 1fr)`,
        borderTop: "1.5px solid #232a22",
        borderBottom: "1px solid #e6e3dc",
      }}
    >
      {children}
    </div>
  );
}

// ── Pace badge ───────────────────────────────────────────────────────────────

const PACE_MAP: Record<string, [string, string]> = {
  on_track: ["#1d5536", "On track"],
  ahead:    ["#1d5536", "Ahead"],
  behind:   ["#a8473a", "Behind"],
  at_risk:  ["#9a6a1e", "At risk"],
  unknown:  ["#a39d8c", "Untracked"],
  binary:   ["#a39d8c", "Logged"],
  complete: ["#1d5536", "Complete"],
};

export function Pace({ status }: { status?: string | null }) {
  const [col, txt] = PACE_MAP[status ?? ""] ?? ["#736e5f", status ?? "—"];
  return (
    <span
      className="font-mono whitespace-nowrap"
      style={{ fontSize: 9, letterSpacing: "0.5px", color: col }}
    >
      {txt}
    </span>
  );
}

// ── Pill — rounded filter toggle ─────────────────────────────────────────────

export function Pill({
  children,
  active,
  color = "#1d5536",
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
      className="ons-tap cursor-pointer"
      onClick={onClick}
      style={{
        fontFamily: "var(--font-mono, 'Spline Sans Mono', monospace)",
        fontSize: 10,
        letterSpacing: "0.5px",
        textTransform: "uppercase",
        border: `1px solid ${active ? color : "#e6e3dc"}`,
        background: active ? color : "#f6f5f2",
        color: active ? "#fff" : "#736e5f",
        borderRadius: 999,
        padding: "6px 13px",
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
  spin?: boolean;
}) {
  return (
    <div
      className="absolute pointer-events-none text-green"
      style={{
        right: -50,
        top: -70,
        opacity,
        animation: spin ? "ons-rot 120s linear infinite" : "none",
      }}
    >
      <GlobeMark size={size} stroke="#1d5536" sw={1} />
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
      <div className="font-serif text-[22px] text-ink">{title}</div>
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
    <div className="bg-surface border border-border rounded-card p-4">
      <p className="font-mono text-[9.5px] tracking-[1.7px] uppercase text-faint mb-2">
        {label}
      </p>
      <p
        className={clsx(
          "font-serif text-2xl font-semibold",
          accent ? "text-green" : "text-ink"
        )}
      >
        {display}
        {unit && (
          <span className="font-mono text-[11px] text-faint font-normal ml-1">
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
    <p className="font-mono text-[9.5px] tracking-[1.7px] uppercase text-faint mb-2">
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
    <div className="px-6 py-4 border-b border-border bg-surface flex items-center justify-between">
      <div>
        <h1 className="text-xl font-semibold text-ink">{title}</h1>
        {sub && <p className="text-xs text-muted mt-0.5">{sub}</p>}
      </div>
      {right}
    </div>
  );
}
