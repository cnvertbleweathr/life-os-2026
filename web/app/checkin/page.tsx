"use client";

import { useState } from "react";
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
  if (r >= 0.78) return ["Primed", "#1d5536"];
  if (r >= 0.6) return ["Steady", "#2f6b43"];
  if (r >= 0.42) return ["Manage load", "#9a6a1e"];
  return ["Recover", "#a8473a"];
}

export default function CheckinPage() {
  const [vals, setVals] = useState<Vals>(BLANK);
  const [note, setNote] = useState("");
  const [saved, setSaved] = useState(false);

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

  const today = new Date().toLocaleDateString("en-US", {
    weekday: "long", year: "numeric", month: "long", day: "numeric",
  });

  const reset = () => {
    setVals(BLANK);
    setNote("");
    setSaved(false);
  };

  if (saved) {
    return (
      <div className="ons-page" style={{ padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" }}>
        <PageHead title="Check-in saved" kicker={today} />
        <Card accent style={{ maxWidth: 460, textAlign: "center", padding: "44px 30px" }}>
          <div
            className="grid place-items-center text-green mx-auto mb-[18px]"
            style={{ width: 56, height: 56, borderRadius: 999, background: "#e9efe7" }}
          >
            <OnsIcon name="habits" size={28} stroke={2} />
          </div>
          <div className="font-serif text-[22px] font-bold">Logged for today</div>
          <p className="text-[13px] text-muted mt-2">
            Readiness <b style={{ color: readColor }}>{readLabel}</b> · avg {avg}/5.
            Feeds training readiness and the morning brief.
          </p>
          <button
            className="ons-tap mt-[18px] font-mono cursor-pointer"
            onClick={reset}
            style={{
              fontSize: 11, color: "#1d5536", background: "#f6f5f2",
              border: "1px solid rgba(29,85,54,0.33)", borderRadius: 999, padding: "8px 18px",
            }}
          >
            LOG ANOTHER
          </button>
        </Card>
      </div>
    );
  }

  return (
    <div className="ons-page" style={{ padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" }}>
      <PageHead
        title="Daily Check-in"
        kicker="30 seconds · feeds training readiness + OpenClaw"
        right={
          <div className="font-mono text-right text-faint" style={{ fontSize: 9.5 }}>
            {today.toUpperCase()}<br />STORED IN DUCKDB
          </div>
        }
      />

      <div className="grid gap-[22px] items-start" style={{ gridTemplateColumns: "1.5fr 1fr" }}>
        <Card>
          <div className="flex flex-col gap-5">
            {FIELDS.map((f) => (
              <div key={f.key}>
                <div className="flex items-center gap-[10px] mb-[9px]">
                  <K color="#232a22" style={{ fontSize: 11 }}>{f.label}</K>
                  {f.invert && (
                    <span className="font-mono text-faint" style={{ fontSize: 8, letterSpacing: "0.5px" }}>
                      (lower = better)
                    </span>
                  )}
                  {vals[f.key] > 0 && (
                    <span className="ml-auto font-mono font-semibold text-green" style={{ fontSize: 11 }}>
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
                          border: `1px solid ${on ? "#1d5536" : "#e6e3dc"}`,
                          background: on ? "#1d5536" : "#f6f5f2",
                          color: on ? "#fff" : "#736e5f",
                          transition: "all .12s",
                        }}
                      >
                        {n}
                      </button>
                    );
                  })}
                </div>
                <div className="flex justify-between mt-[5px] font-mono text-faint" style={{ fontSize: 8.5 }}>
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

            <button
              className="ons-tap w-full font-semibold"
              disabled={!filled}
              onClick={() => setSaved(true)}
              style={{
                padding: 14, borderRadius: 8, border: "none",
                cursor: filled ? "pointer" : "not-allowed",
                fontSize: 14,
                background: filled ? "#1d5536" : "#e6e3dc",
                color: filled ? "#fff" : "#a39d8c",
                transition: "background .15s",
              }}
            >
              {filled ? "Save check-in" : "Rate all six to save"}
            </button>
          </div>
        </Card>

        {/* Live readiness */}
        <div>
          <Card accent style={{ marginBottom: 22, textAlign: "center" }}>
            <K color="#1d5536" style={{ marginBottom: 16 }}>Today's Readiness</K>
            <div className="grid place-items-center">
              <Donut
                value={readiness}
                size={130}
                sw={12}
                color={readColor}
                track="#efebe1"
              >
                <div className="text-center">
                  <div
                    className="font-serif font-bold leading-none"
                    style={{ fontSize: 34, color: filled ? readColor : "#a39d8c" }}
                  >
                    {filled ? Math.round(readiness * 100) : "—"}
                  </div>
                  <div className="font-mono text-faint mt-[3px]" style={{ fontSize: 8, letterSpacing: "1px" }}>
                    {filled ? readLabel.toUpperCase() : "FILL TO SCORE"}
                  </div>
                </div>
              </Donut>
            </div>
            <div className="flex justify-around mt-[18px] pt-[14px] border-t border-border-2">
              <div>
                <div className="font-serif text-[20px] font-semibold">{avg}</div>
                <div className="font-mono text-faint mt-[3px]" style={{ fontSize: 8 }}>AVG / 5</div>
              </div>
              <div>
                <div className="font-serif text-[20px] font-semibold">
                  {FIELDS.filter((f) => vals[f.key] > 0).length}/6
                </div>
                <div className="font-mono text-faint mt-[3px]" style={{ fontSize: 8 }}>RATED</div>
              </div>
            </div>
          </Card>

          <Card>
            <K style={{ marginBottom: 10 }}>Where this goes</K>
            <div className="flex flex-col gap-[10px]">
              {[
                ["fitness", "Training readiness — gates today's WOD intensity"],
                ["scenarios", "Morning brief context (OpenClaw)"],
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
