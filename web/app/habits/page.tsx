"use client";

import { useEffect, useState, useCallback } from "react";
import {
  habitsApi, parseLocalDate,
  type HabitToday, type HabitStreak, type HabitDay,
} from "@/lib/api";
import {
  Card, PageHead, Stat, StatBand, K, Loading, ErrorState,
} from "@/components/ui/primitives";
import { OnsIcon } from "@/components/ui/icons";

export default function HabitsPage() {
  const [today, setToday] = useState<HabitToday | null>(null);
  const [streaks, setStreaks] = useState<HabitStreak[] | null>(null);
  const [recent, setRecent] = useState<HabitDay[]>([]);
  const [done, setDone] = useState<Record<string, boolean>>({});
  const [pending, setPending] = useState<Record<string, boolean>>({});
  const [saveError, setSaveError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([habitsApi.today(), habitsApi.streaks(), habitsApi.recent(21)])
      .then(([t, s, r]) => {
        setToday(t);
        setStreaks(s);
        setRecent(r);
        setDone(Object.fromEntries(t.habits.map((h) => [h.key, h.done])));
      })
      .catch((e) => setError(e.message));
  }, []);

  // Optimistic: flip immediately, write to the log, roll back on failure.
  // One request per habit at a time so rapid taps can't land out of order.
  const toggle = useCallback((key: string) => {
    if (pending[key]) return;
    const next = !done[key];
    setDone((prev) => ({ ...prev, [key]: next }));
    setPending((prev) => ({ ...prev, [key]: true }));
    setSaveError(null);
    habitsApi
      .log(key, next)
      .then((day) => {
        setToday(day);
        setDone(Object.fromEntries(day.habits.map((h) => [h.key, h.done])));
      })
      .catch((e) => {
        setDone((prev) => ({ ...prev, [key]: !next }));
        setSaveError(`Couldn't save — ${e.message}`);
      })
      .finally(() => setPending((prev) => ({ ...prev, [key]: false })));
  }, [done, pending]);

  if (error) return <ErrorState message={error} />;
  if (!today || !streaks) return <Loading />;

  const habits = today.habits;
  const total = today.total_count;
  const doneCount = habits.filter((h) => done[h.key]).length;
  const longest = Math.max(0, ...streaks.map((s) => s.longest_streak ?? 0));

  const streakFor = (key: string) => streaks.find((s) => s.habit === key);

  const todayLong = parseLocalDate(today.date).toLocaleDateString("en-US", {
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
          {saveError && (
            <div className="font-mono mb-3" role="alert" style={{ fontSize: 10.5, color: "#a8473a" }}>
              {saveError}
            </div>
          )}
          <div className="flex flex-col gap-1">
            {habits.map((h) => {
              const on = !!done[h.key];
              const streak = streakFor(h.key);
              return (
                <button
                  key={h.key}
                  className="ons-tap flex items-center gap-[13px] border-none cursor-pointer text-left"
                  onClick={() => toggle(h.key)}
                  aria-pressed={on}
                  aria-busy={!!pending[h.key]}
                  style={{
                    opacity: pending[h.key] ? 0.7 : 1,
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
              // Previous 20 days from the log (oldest first); today is the
              // dashed cell after them, driven by live toggle state.
              const hist = recent.slice(0, -1).map((d) => ({
                date: d.date,
                on: d[h.key] === true,
              }));
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
                        key={d.date}
                        className="flex-1 rounded-sm"
                        title={`${d.date} · ${d.on ? "done" : "missed"}`}
                        style={{
                          height: 16,
                          background: d.on
                            ? `rgba(29,85,54,${(0.4 + (i / hist.length) * 0.6).toFixed(2)})`
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
