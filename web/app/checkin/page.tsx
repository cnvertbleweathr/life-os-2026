"use client";

import { useEffect, useState } from "react";
import { checkinApi, hasWriteKey, type CheckinValues } from "@/lib/api";
import { Card, PageHead, K } from "@/components/ui/primitives";
import { OnsIcon } from "@/components/ui/icons";
import { Donut } from "@/components/ui/viz";

const FIELDS = [
  { key: "energy", label: "Energy", lo: "Drained", hi: "Energized", invert: false },
  { key: "mood", label: "Mood", lo: "Low", hi: "Great", invert: false },
  { key: "focus", label: "Focus", lo: "Scattered", hi: "Sharp", invert: false },
  { key: "sleep", label: "Sleep", lo: "Poor", hi: "Solid", invert: false },
  { key: "soreness", label: "Soreness", lo: "None", hi: "Very sore", invert: true },
  { key: "stress", label: "Stress", lo: "None", hi: "High", invert: true },
] as const;

type Vals = Record<string, number>;
const BLANK: Vals = { energy: 0, mood: 0, focus: 0, sleep: 0, soreness: 0, stress: 0 };

function readinessLabel(r: number): [string, string] {
  if (r >= 0.78) return ["Primed", "var(--hue)"];
  if (r >= 0.6) return ["Steady", "var(--hue)"];
  if (r >= 0.42) return ["Manage load", "var(--warn)"];
  return ["Recover", "var(--neg)"];
}

export default function CheckinPage() {
  const [vals, setVals] = useState<Vals>(BLANK);
  const [note, setNote] = useState("");
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [existingAt, setExistingAt] = useState<string | null>(null);

  // If today already has a check-in, start from it so saving updates it.
  const [today, setToday] = useState("");
  const [keyed, setKeyed] = useState(true);
  useEffect(() => {
    // Date and key state are client-only: computing them during render caused a hydration mismatch.
    setToday(new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" }));
    if (!hasWriteKey()) { setKeyed(false); return; } // no key yet: don't prompt on load; saving asks once
    checkinApi
      .today()
      .then((c) => {
        if (!c) return;
        setVals(Object.fromEntries(FIELDS.map((f) => [f.key, c[f.key]])));
        setNote(c.note ?? "");
        setExistingAt(c.logged_at);
      })
      .catch(() => {
        /* page still works for a fresh check-in */
      });
  }, []);

  const save = () => {
    setSaving(true);
    setSaveError(null);
    const values = Object.fromEntries(
      FIELDS.map((f) => [f.key, vals[f.key]])
    ) as unknown as CheckinValues;
    checkinApi
      .log({ ...values, note })
      .then((c) => {
        setExistingAt(c.logged_at);
        setSaved(true);
      })
      .catch((e) => setSaveError(`Couldn't save — ${e.message}`))
      .finally(() => setSaving(false));
  };

  const filled = FIELDS.every((f) => vals[f.key] > 0);
  const readiness = filled
    ? FIELDS.reduce(
        (s, f) => s + (f.invert ? 6 - vals[f.key] : vals[f.key]),
        0
      ) / (FIELDS.length * 5)
    : 0;
  const avg = filled
    ? (FIELDS.reduce((s, f) => s + vals[f.key], 0) / FIELDS.length).toFixed(1)
    : "—";
  const [readLabel, readColor] = readinessLabel(readiness);


  // Back to the form with today's values still filled in, to adjust them.
  const reset = () => setSaved(false);

  if (saved) {
    return (
      <div className="ons-page" style={{ padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" }}>
        <PageHead title="Check-in saved" kicker={today} sub="Saved. It loads into ONS with tonight\u2019s sync." />
        <Card accent style={{ maxWidth: 460, textAlign: "center", padding: "44px 30px" }}>
          <div
            className="grid place-items-center text-green mx-auto mb-[18px]"
            style={{ width: 56, height: 56, borderRadius: 999, background: "var(--hue-soft)" }}
          >
            <OnsIcon name="habits" size={28} stroke={2} />
          </div>
          <div className="font-serif text-[22px] font-bold">Logged for today</div>
          <p className="text-[13px] text-muted mt-2">
            Readiness <b style={{ color: readColor }}>{readLabel}</b> · avg {avg}/5.
            Feeds training readiness and the morning brief. Saving again
            replaces today&apos;s entry.
          </p>
          <button className="ons-tap ons-btn mt-[18px]" onClick={reset}>Edit today&apos;s check-in</button>
        </Card>
      </div>
    );
  }

  return (
    <div className="ons-page" style={{ padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" }}>
      <PageHead
        title="Check-in"
        kicker={`${today}${today ? " · " : ""}${existingAt ? "already checked in today, so saving updates it" : "about 30 seconds"}`}
        sub={<>Six quick ratings. They feed training readiness and tomorrow&apos;s brief, and load into ONS overnight.{!keyed && <> Saving asks for your write key once on this device.</>}</>}
      />

      <div className="ons-stack grid gap-[22px] items-start" style={{ gridTemplateColumns: "1.5fr 1fr" }}>
        <Card>
          <div className="flex flex-col gap-5">
            {FIELDS.map((f) => (
              <div key={f.key}>
                <div className="flex items-center gap-[10px] mb-[9px]">
                  <K color="var(--ink)" style={{ fontSize: 11 }}>{f.label}</K>
                  {f.invert && (
                    <span className="text-muted" style={{ fontSize: 12 }}>
                      (lower = better)
                    </span>
                  )}
                  {vals[f.key] > 0 && (
                    <span className="ml-auto font-mono font-semibold text-green" style={{ fontSize: 12 }}>
                      {vals[f.key]}/5
                    </span>
                  )}
                </div>
                <div className="flex gap-2">
                  {[1, 2, 3, 4, 5].map((n) => {
                    const on = vals[f.key] === n;
                    return (
                      <button
                        key={n}
                        className="ons-tap flex-1 cursor-pointer font-mono font-semibold"
                        onClick={() => setVals({ ...vals, [f.key]: n })}
                        style={{
                          height: 42, borderRadius: 7, fontSize: 14,
                          border: `1px solid ${on ? "var(--hue)" : "var(--border)"}`,
                          background: on ? "var(--hue)" : "var(--raised)",
                          color: on ? "var(--hue-ink)" : "var(--muted)",
                          transition: "all .12s",
                        }}
                      >
                        {n}
                      </button>
                    );
                  })}
                </div>
                <div className="flex justify-between mt-[5px] text-muted" style={{ fontSize: 12 }}>
                  <span>{f.lo}</span>
                  <span>{f.hi}</span>
                </div>
              </div>
            ))}

            <div>
              <K style={{ marginBottom: 8 }}>Note (optional)</K>
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={2}
                placeholder="Anything worth noting — travel, illness, big workout…"
                className="ons-input w-full font-sans"
                style={{ resize: "none", fontSize: 13 }}
              />
            </div>

            {saveError && (
              <div role="alert" style={{ fontSize: 13, color: "var(--neg)" }}>
                {saveError}
              </div>
            )}
            <button
              className="ons-tap w-full font-semibold"
              disabled={!filled || saving}
              onClick={save}
              style={{
                padding: 14, borderRadius: 8, border: "none",
                cursor: filled && !saving ? "pointer" : "not-allowed",
                fontSize: 14,
                background: filled ? "var(--hue)" : "var(--border)",
                color: filled ? "var(--hue-ink)" : "var(--faint)",
                opacity: saving ? 0.75 : 1,
                transition: "background .15s",
              }}
            >
              {!filled
                ? "Rate all six to save"
                : saving
                ? "Saving…"
                : existingAt
                ? "Update check-in"
                : "Save check-in"}
            </button>
          </div>
        </Card>

        {/* Live readiness */}
        <div>
          <Card accent style={{ marginBottom: 22, textAlign: "center" }}>
            <K color="var(--hue)" style={{ marginBottom: 16 }}>Today's Readiness</K>
            <div className="grid place-items-center">
              <Donut
                value={readiness}
                size={130}
                sw={12}
                color={readColor}
                track="var(--frame)"
              >
                <div className="text-center">
                  <div
                    className="font-serif font-bold leading-none"
                    style={{ fontSize: 34, color: filled ? readColor : "var(--faint)" }}
                  >
                    {filled ? Math.round(readiness * 100) : "—"}
                  </div>
                  <div className="text-muted mt-[3px]" style={{ fontSize: 12 }}>
                    {filled ? readLabel : "Rate all six to score"}
                  </div>
                </div>
              </Donut>
            </div>
            <div className="flex justify-around mt-[18px] pt-[14px] border-t border-border-2">
              <div>
                <div className="font-serif text-[20px] font-semibold">{avg}</div>
                <div className="text-muted mt-[3px]" style={{ fontSize: 12 }}>Avg / 5</div>
              </div>
              <div>
                <div className="font-serif text-[20px] font-semibold">
                  {FIELDS.filter((f) => vals[f.key] > 0).length}/6
                </div>
                <div className="text-muted mt-[3px]" style={{ fontSize: 12 }}>Rated</div>
              </div>
            </div>
          </Card>

          <Card>
            <K style={{ marginBottom: 10 }}>Where this goes</K>
            <div className="flex flex-col gap-[10px]">
              {[
                ["fitness", "Training readiness — gates today's WOD intensity"],
                ["scenarios", "Morning brief context"],
                ["goals", "Trend lines for energy, sleep & stress"],
              ].map(([ic, txt], i) => (
                <div key={i} className="flex gap-[10px] items-start">
                  <span className="text-green mt-px">
                    <OnsIcon name={ic} size={15} stroke={1.6} />
                  </span>
                  <span style={{ fontSize: 12.5, lineHeight: 1.4 }}>{txt}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
