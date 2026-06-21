/**
 * /checkin — Daily subjective check-in
 * 30 seconds: energy, mood, focus, sleep, soreness, stress (1-5) + optional note
 * POSTs to /api/checkin/log → writes to raw.daily_checkin in DuckDB
 */
"use client";

import { useState } from "react";
import { PageHeader, Card, SectionLabel } from "@/components/ui/primitives";
import clsx from "clsx";

const FIELDS = [
  { key: "energy",   label: "Energy",   emoji: "⚡", lo: "Drained", hi: "Energized" },
  { key: "mood",     label: "Mood",     emoji: "🧠", lo: "Low",     hi: "Great"     },
  { key: "focus",    label: "Focus",    emoji: "🎯", lo: "Scattered",hi: "Sharp"    },
  { key: "sleep",    label: "Sleep",    emoji: "😴", lo: "Poor",    hi: "Solid"     },
  { key: "soreness", label: "Soreness", emoji: "💪", lo: "None",    hi: "Very sore" },
  { key: "stress",   label: "Stress",   emoji: "🌡️", lo: "None",   hi: "High"      },
] as const;

type FieldKey = typeof FIELDS[number]["key"];

const COLOR = ["", "bg-red/60", "bg-amber/60", "bg-amber/30", "bg-green/40", "bg-green"];

function ScaleInput({
  label, emoji, lo, hi, value, onChange,
}: {
  label:    string;
  emoji:    string;
  lo:       string;
  hi:       string;
  value:    number;
  onChange: (v: number) => void;
}) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-base">{emoji}</span>
        <span className="text-[13px] font-medium text-ink">{label}</span>
        {value > 0 && (
          <span className="ml-auto text-xs font-semibold text-green">{value}/5</span>
        )}
      </div>
      <div className="flex gap-2">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            onClick={() => onChange(n)}
            className={clsx(
              "flex-1 h-10 rounded-sm text-sm font-semibold transition-all",
              value === n
                ? `${COLOR[n]} text-white ring-2 ring-offset-1 ring-green/40`
                : "bg-canvas border border-border text-muted hover:bg-green/8 hover:text-ink"
            )}
          >
            {n}
          </button>
        ))}
      </div>
      <div className="flex justify-between mt-1">
        <span className="text-2xs text-faint">{lo}</span>
        <span className="text-2xs text-faint">{hi}</span>
      </div>
    </div>
  );
}

export default function CheckinPage() {
  const [values, setValues] = useState<Record<FieldKey, number>>({
    energy: 0, mood: 0, focus: 0, sleep: 0, soreness: 0, stress: 0,
  });
  const [note, setNote]       = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted]   = useState(false);
  const [error, setError]           = useState("");

  const allFilled = Object.values(values).every(v => v > 0);
  const avgScore  = allFilled
    ? Math.round(Object.values(values).reduce((a, b) => a + b, 0) / 6 * 10) / 10
    : null;

  const handleSubmit = async () => {
    if (!allFilled) return;
    setSubmitting(true);
    setError("");
    try {
      const res = await fetch("/api/checkin/log", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...values, note: note.trim() || null }),
      });
      if (!res.ok) throw new Error(`API error ${res.status}`);
      setSubmitted(true);
    } catch (e) {
      setError("Failed to save. Is FastAPI running?");
    } finally {
      setSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <div>
        <PageHeader title="✅ Check-in saved" sub="See you tomorrow" />
        <div className="p-6 max-w-lg">
          <Card className="text-center py-8">
            <p className="text-3xl mb-3">✅</p>
            <p className="text-sm font-medium text-ink">Check-in logged</p>
            {avgScore && (
              <p className="text-xs text-muted mt-1">
                Average score: {avgScore}/5
              </p>
            )}
            <button
              onClick={() => {
                setSubmitted(false);
                setValues({ energy: 0, mood: 0, focus: 0, sleep: 0, soreness: 0, stress: 0 });
                setNote("");
              }}
              className="mt-4 text-xs text-green hover:underline"
            >
              Log another
            </button>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="📋 Daily Check-in"
        sub="30 seconds · feeds training readiness and OpenClaw context"
      />
      <div className="p-6 max-w-lg space-y-4">
        <Card className="space-y-5">
          {FIELDS.map(({ key, label, emoji, lo, hi }) => (
            <ScaleInput
              key={key}
              label={label}
              emoji={emoji}
              lo={lo}
              hi={hi}
              value={values[key]}
              onChange={(v) => setValues(prev => ({ ...prev, [key]: v }))}
            />
          ))}

          <div>
            <SectionLabel>Note (optional)</SectionLabel>
            <textarea
              value={note}
              onChange={e => setNote(e.target.value)}
              placeholder="Anything worth noting — travel, illness, big workout..."
              rows={2}
              className="w-full text-sm border border-border rounded-sm px-3 py-2
                         bg-canvas text-ink placeholder-faint resize-none
                         focus:outline-none focus:ring-1 focus:ring-green/40"
            />
          </div>

          {error && <p className="text-xs text-red">{error}</p>}

          <button
            onClick={handleSubmit}
            disabled={!allFilled || submitting}
            className={clsx(
              "w-full py-3 rounded-card text-sm font-semibold transition-all",
              allFilled && !submitting
                ? "bg-green text-white hover:bg-green-bright"
                : "bg-border text-faint cursor-not-allowed"
            )}
          >
            {submitting ? "Saving..." : allFilled ? "Save check-in" : "Fill all fields to save"}
          </button>
        </Card>

        <p className="text-2xs text-faint text-center">
          Stored in DuckDB · used for training readiness and OpenClaw context
        </p>
      </div>
    </div>
  );
}
