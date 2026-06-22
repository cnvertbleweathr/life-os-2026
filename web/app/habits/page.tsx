"use client";

import { useEffect, useState, useCallback } from "react";
import { habitsApi, type HabitToday, type HabitStreak } from "@/lib/api";
import {
  Card, PageHead, Stat, StatBand, K, Loading, ErrorState,
} from "@/components/ui/primitives";
import { OnsIcon } from "@/components/ui/icons";

export default function HabitsPage() {
  const [today, setToday] = useState<HabitToday | null>(null);
  const [streaks, setStreaks] = useState<HabitStreak[] | null>(null);
  const [done, setDone] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([habitsApi.today(), habitsApi.streaks()])
      .then(([t, s]) => {
        setToday(t);
        setStreaks(s);
        setDone(Object.fromEntries(t.habits.map((h) => [h.key, h.done])));
      })
      .catch((e) => setError(e.message));
  }, []);

  const toggle = useCallback((key: string) => {
    setDone((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!today || !streaks) return <Loading />;

  const habits = today.habits;
  const total = today.total_count;
  const doneCount = habits.filter((h) => done[h.key]).length;
  const longest = Math.max(0, ...streaks.map((s) => s.longest_streak ?? 0));

  const streakFor = (key: string) => streaks.find((s) => s.habit === key);

  const todayLong = new Date(today.date).toLocaleDateString("en-US", {
    weekday: "long", year: "numeric", month: "long", day: "numeric",
  });

  return (
    <div className="ons-page" style={{ padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" }}>
      <PageHead
        title="Habits"
        kicker={`${todayLong} · daily checklist`}
        right={
          <div className="font-mono text-right" style={{ fontSize: 9.5, color: doneCount === total ? "#1d5536" : "#a39d8c" }}>
            {doneCount}/{total} DONE TODAY<br />RESETS AT MIDNIGHT
          </div>
        }
      />

      <StatBand>
        <Stat label="Done Today" value={`${doneCount}/${total}`} accent={doneCount > 0} />
        <Stat label="Longest Streak" value={longest} unit="d" />
        <Stat label="Logged Today" value={doneCount} />
        <Stat label="Tracked Habits" value={total} last />
      </StatBand>

      <div className="grid gap-[22px] items-start" style={{ gridTemplateColumns: "1fr 1.35fr" }}>
        {/* Today checklist */}
        <Card>
          <div className="flex justify-between items-center mb-4">
            <K>Today</K>
            <span className="font-mono text-faint" style={{ fontSize: 9.5 }}>TAP TO LOG</span>
          </div>
          <div className="flex flex-col gap-1">
            {habits.map((h) => {
              const on = !!done[h.key];
              const streak = streakFor(h.key);
              return (
                <button
                  key={h.key}
                  className="ons-tap flex items-center gap-[13px] border-none cursor-pointer text-left"
                  onClick={() => toggle(h.key)}
                  style={{
                    padding: "13px 12px",
                    margin: "0 -12px",
                    background: on ? "#e9efe7" : "transparent",
                    borderRadius: 8,
                  }}
                >
                  <span
                    className="grid place-items-center shrink-0"
                    style={{
                      width: 22, height: 22, borderRadius: 6,
                      border: `1.5px solid ${on ? "#1d5536" : "#e6e3dc"}`,
                      background: on ? "#1d5536" : "transparent",
                      transition: "all .15s",
                    }}
                  >
                    {on && <OnsIcon name="habits" size={13} stroke={2.4} style={{ color: "#fff" }} />}
                  </span>
                  <span
                    className="flex-1"
                    style={{ fontSize: 14.5, color: on ? "#1d5536" : "#232a22", fontWeight: on ? 600 : 400 }}
                  >
                    {h.label}
                  </span>
                  <span className="font-mono text-faint" style={{ fontSize: 10 }}>
                    best {streak?.longest_streak ?? 0}d
                  </span>
                </button>
              );
            })}
          </div>
        </Card>

        {/* Streaks + 21-day history */}
        <Card pad={0}>
          <div className="flex justify-between items-center" style={{ padding: "16px 18px 12px" }}>
            <K>Streaks · last 21 days</K>
            <div className="flex items-center gap-1.5 font-mono text-faint" style={{ fontSize: 8.5 }}>
              <span className="rounded-sm" style={{ width: 9, height: 9, background: "#1d5536" }} /> DONE
              <span className="rounded-sm ml-1.5" style={{ width: 9, height: 9, background: "#efebe1" }} /> MISSED
            </div>
          </div>
          <div style={{ padding: "0 18px 14px" }}>
            {habits.map((h) => {
              const streak = streakFor(h.key);
              const cur = streak?.current_streak ?? (done[h.key] ? 1 : 0);
              const best = streak?.longest_streak ?? 0;
              // synthesize 21-day history (deterministic placeholder —
              // needs a per-day habit log endpoint to be real)
              const seed = h.key.length * 7;
              const hist = Array.from({ length: 21 }, (_, i) =>
                (Math.sin(seed + i * 1.3) * 0.5 + 0.5) > 0.42
              );
              return (
                <div key={h.key} style={{ padding: "14px 0", borderTop: "1px solid #ebe5d8" }}>
                  <div className="flex justify-between items-baseline mb-[9px]">
                    <span style={{ fontSize: 13.5 }}>{h.label}</span>
                    <span>
                      <span className="font-mono font-semibold text-green" style={{ fontSize: 13 }}>{cur}</span>
                      <span className="font-mono text-faint" style={{ fontSize: 9.5 }}> cur · best {best}d</span>
                    </span>
                  </div>
                  <div className="flex gap-[3px]">
                    {hist.map((d, i) => (
                      <div
                        key={i}
                        className="flex-1 rounded-sm"
                        title={d ? "done" : "missed"}
                        style={{
                          height: 16,
                          background: d
                            ? `rgba(29,85,54,${(0.4 + (i / 21) * 0.6).toFixed(2)})`
                            : "#efebe1",
                        }}
                      />
                    ))}
                    <div
                      className="flex-1 rounded-sm"
                      title="today"
                      style={{
                        height: 16,
                        background: done[h.key] ? "#1d5536" : "transparent",
                        border: `1.5px dashed ${done[h.key] ? "#1d5536" : "#e6e3dc"}`,
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      </div>
    </div>
  );
}
