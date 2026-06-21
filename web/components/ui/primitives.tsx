import clsx from "clsx";
import type { ReactNode } from "react";

// ── Card ─────────────────────────────────────────────────────────────────────

export function Card({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={clsx(
        "bg-surface border border-border rounded-card p-5",
        className
      )}
    >
      {children}
    </div>
  );
}

// ── PageHeader ───────────────────────────────────────────────────────────────

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

// ── SectionLabel ─────────────────────────────────────────────────────────────

export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <p className="text-[10px] font-semibold tracking-[1.5px] uppercase text-faint mb-2">
      {children}
    </p>
  );
}

// ── Empty ────────────────────────────────────────────────────────────────────
// "An empty screen is an invitation to act" — explain what's missing plainly,
// never imply broken when the real state is "no data exists yet."

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

export function Loading({ label = "Loading..." }: { label?: string }) {
  return (
    <div className="py-8 text-center">
      <p className="text-xs text-faint">{label}</p>
    </div>
  );
}

// ── ErrorState ───────────────────────────────────────────────────────────────
// Distinguishes "no data" from "request failed" — these are different
// states and should never be visually identical.

export function ErrorState({ message }: { message?: string }) {
  return (
    <div className="py-8 text-center">
      <p className="text-sm text-red">Couldn't load this.</p>
      {message && <p className="text-xs text-faint mt-1">{message}</p>}
    </div>
  );
}

// ── StatCard ─────────────────────────────────────────────────────────────────
// value can legitimately be null/undefined per API_STATE_REFERENCE — render
// an em dash rather than "0" or "null" so absence isn't mistaken for a real zero.

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
    value === null || value === undefined || value === ""
      ? "—"
      : typeof value === "number"
      ? value.toLocaleString(undefined, { maximumFractionDigits: 1 })
      : value;

  return (
    <Card className="flex flex-col gap-1">
      <SectionLabel>{label}</SectionLabel>
      <p
        className={clsx(
          "text-2xl font-semibold tabular-nums",
          accent ? "text-green" : "text-ink"
        )}
      >
        {display}
        {unit && display !== "—" && (
          <span className="text-xs text-faint ml-1 font-normal">{unit}</span>
        )}
      </p>
    </Card>
  );
}

// ── PaceBadge ────────────────────────────────────────────────────────────────
// pace_status from mart_goal_pacing: ahead/on_track/at_risk/behind/complete/binary

const PACE_STYLES: Record<string, string> = {
  ahead:       "bg-green/15 text-green",
  on_track:    "bg-green/10 text-green-light",
  at_risk:     "bg-amber/15 text-amber",
  behind:      "bg-red/15 text-red",
  complete:    "bg-green/20 text-green",
  binary:      "bg-border text-muted",
  not_started: "bg-border text-faint",
  // goals without a numeric target (str-type, e.g. "promotion", "roth_ira")
  // come back as pace_status: "unknown" — not an error, just not pace-trackable
  unknown:     "bg-border text-faint",
};

export function PaceBadge({ status }: { status?: string | null }) {
  if (!status) return null;
  const style = PACE_STYLES[status] ?? "bg-border text-muted";
  return (
    <span
      className={clsx(
        "text-2xs font-semibold px-2 py-0.5 rounded-full uppercase tracking-wide",
        style
      )}
    >
      {status.replace("_", " ")}
    </span>
  );
}
