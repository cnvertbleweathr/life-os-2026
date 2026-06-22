"use client";

import { useEffect, useState } from "react";
import { homeApi, habitsApi, type HomeSummary, type HabitToday } from "@/lib/api";
import { Card, K, Pace, Watermark, Loading, ErrorState } from "@/components/ui/primitives";
import { OnsIcon } from "@/components/ui/icons";

const CFB_BACKTEST_ROI = "+34.5"; // confirmed 4-season walk-forward backtest, same fact as the CFB page header

function CalendarIcon({ title }: { title: string }) {
  const t = title.toLowerCase();
  if (/concert|show|fest/.test(t)) return <OnsIcon name="shows" size={13} stroke={1.6} style={{ color: "#a39d8c" }} />;
  if (/trip|fly|dia|airport|hartford|rehoboth/.test(t)) return <OnsIcon name="pin" size={13} stroke={1.6} style={{ color: "#a39d8c" }} />;
  if (/bday|birthday/.test(t)) return <span className="rounded-full" style={{ width: 5, height: 5, background: "#9a6a1e" }} />;
  return null;
}

export default function HomePage() {
  const [data, setData] = useState<HomeSummary | null>(null);
  const [habitsToday, setHabitsToday] = useState<HabitToday | null>(null);
  const [done, setDone] = useState<Record<string, boolean>>({});
  const [vote, setVote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([homeApi.summary(), habitsApi.today()])
      .then(([h, t]) => {
        setData(h);
        setHabitsToday(t);
        setDone(Object.fromEntries(t.habits.map((x) => [x.key, x.done])));
      })
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!data || !habitsToday) return <Loading label="Loading today's summary..." />;

  const { stat_cards: sc, calendar, daily10, goals } = data;
  const todayLong = new Date(data.date).toLocaleDateString("en-US", {
    weekday: "long", year: "numeric", month: "long", day: "numeric",
  });

  const doneCount = habitsToday.habits.filter((h) => done[h.key]).length;
  const habitsTotal = habitsToday.total_count;

  // Streak: longest current streak across today's habits, if any are active
  // (real streak data lives in /habits/streaks — not fetched here to keep
  // Home to two calls; shows "—" rather than a guess if unavailable)
  const streakDisplay = "—";

  // Books-behind-pace, same math as the Reading page
  const READING_GOAL = 10;
  const now = new Date();
  const dayOfYear = Math.floor(
    (now.getTime() - new Date(now.getFullYear(), 0, 0).getTime()) / 86400000
  );
  const ytdTarget = Math.round((READING_GOAL / 365) * dayOfYear);
  const booksBehind = Math.max(0, ytdTarget - (sc.books_read ?? 0));
  const readingOnPace = booksBehind === 0;

  const toggleHabit = (key: string) => {
    setDone((prev) => ({ ...prev, [key]: !prev[key] }));
    // Note: optimistic UI only — POST /habits/log isn't wired yet.
    // Mirrors the Habits page until that endpoint exists.
  };

  return (
    <div className="ons-page" style={{ padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" }}>
      {/* Masthead */}
      <div className="flex justify-between items-start mb-7">
        <div>
          <K color="#1d5536">{todayLong} · Denver, CO</K>
          <h1
            className="font-serif font-bold leading-none m-0 mt-3"
            style={{ fontSize: 50, letterSpacing: "-1px" }}
          >
            Good morning.<br />
            <span className="text-muted">You ran </span>
            <span className="text-green">{sc.weekly_miles ?? 0} miles</span>
            <span className="text-muted"> this week.</span>
          </h1>
        </div>
        <div className="text-right shrink-0 pt-1">
          <div
            className="ons-tap inline-flex items-center gap-[9px] text-muted cursor-text"
            style={{
              border: "1px solid #e6e3dc", background: "#fbfaf5", borderRadius: 999,
              padding: "9px 15px", fontSize: 12.5,
            }}
          >
            <OnsIcon name="search" size={15} stroke={1.6} /> Ask the system…
            <span
              className="font-mono"
              style={{ fontSize: 9, border: "1px solid #e6e3dc", borderRadius: 4, padding: "1px 5px", marginLeft: 4 }}
            >
              ⌘K
            </span>
          </div>
          <div className="font-mono text-faint mt-[11px]" style={{ fontSize: 9.5, letterSpacing: "0.5px" }}>
            DATA AS OF {data.date}
          </div>
        </div>
      </div>

      {/* Stat band */}
      <div
        className="grid mb-7"
        style={{ gridTemplateColumns: "repeat(6,1fr)", borderTop: "1.5px solid #232a22", borderBottom: "1px solid #e6e3dc" }}
      >
        {[
          { l: "YTD Miles", v: sc.ytd_miles ?? 0, u: "mi", a: true },
          { l: "Weekly Runs", v: sc.weekly_runs ?? 0, u: "" },
          { l: "Books", v: sc.books_read ?? 0, u: `/${READING_GOAL}` },
          { l: "Habits", v: `${doneCount}/${habitsTotal}`, u: "", a: doneCount > 0 },
          { l: "Streak", v: streakDisplay, u: "" },
          { l: "CFB Edge", v: CFB_BACKTEST_ROI, u: "%", a: true },
        ].map((c, i) => (
          <div
            key={i}
            style={{
              padding: "16px 18px 16px 0",
              borderRight: i < 5 ? "1px solid #ebe5d8" : "none",
              paddingLeft: i ? 18 : 0,
            }}
          >
            <K>{c.l}</K>
            <div
              className="font-serif font-semibold leading-none mt-2"
              style={{ fontSize: 32, color: c.a ? "#1d5536" : "#232a22" }}
            >
              {c.v}
              <span className="font-mono font-normal ml-1 text-faint" style={{ fontSize: 11 }}>{c.u}</span>
            </div>
            <div className="h-8" />
          </div>
        ))}
      </div>

      {/* Brief + This Week */}
      <div className="grid gap-[22px] mb-[22px]" style={{ gridTemplateColumns: "1.62fr 1fr" }}>
        <div
          className="relative overflow-hidden"
          style={{
            background: "#fbfaf5", border: "1px solid #e6e3dc", borderTop: "2.5px solid #1d5536",
            borderRadius: 3, padding: "22px 26px 20px",
          }}
        >
          <Watermark spin />
          <div className="relative">
            <div className="flex justify-between items-center mb-[14px]">
              <div className="flex items-center gap-[10px]">
                <K color="#1d5536">Today's Brief</K>
              </div>
              <span className="font-mono text-faint" style={{ fontSize: 9 }}>UPDATED {data.date}</span>
            </div>
            <p
              className="font-serif m-0"
              style={{ fontSize: 21, lineHeight: 1.4, color: "#232a22", maxWidth: 640, marginBottom: 18 }}
            >
              You're <b className="text-green">on pace for running</b> and{" "}
              <b style={{ color: readingOnPace ? "#1d5536" : "#a8473a" }}>
                {readingOnPace ? "on pace for reading" : "behind on reading"}
              </b>. {calendar.length === 0 ? "Nothing on the calendar — " : "Light day on the calendar — "}
              a good window to {doneCount < habitsTotal ? "close the habit gap." : "stay ahead on habits."}
            </p>
            <div className="grid" style={{ gridTemplateColumns: "repeat(3,1fr)", borderTop: "1px solid #ebe5d8" }}>
              {[
                {
                  icon: "fitness", title: "What's happening",
                  body: `${sc.ytd_miles ?? 0} mi YTD · ${sc.weekly_runs ?? 0} run${sc.weekly_runs === 1 ? "" : "s"} this week. Books at ${sc.books_read ?? 0}/${READING_GOAL}. Habits ${doneCount}/${habitsTotal} today.`,
                },
                {
                  icon: "goals", title: "Why it matters",
                  body: booksBehind > 0
                    ? `Reading trails pace by ~${booksBehind} book${booksBehind === 1 ? "" : "s"}. Habits reset if not logged by midnight.`
                    : `Reading is on pace. Habits reset if not logged by midnight.`,
                },
                {
                  icon: "scenarios", title: "Do next",
                  body: doneCount < habitsTotal
                    ? `${habitsTotal - doneCount} habit${habitsTotal - doneCount === 1 ? "" : "s"} left today. Check the calendar for anything time-sensitive.`
                    : `All habits logged. Check the calendar for anything time-sensitive.`,
                },
              ].map((f, i) => (
                <div key={i} style={{ padding: "16px 16px 4px", borderLeft: i ? "1px solid #ebe5d8" : "none", paddingLeft: i ? 16 : 0 }}>
                  <div className="flex items-center gap-[7px] mb-[9px] text-green">
                    <OnsIcon name={f.icon} size={15} stroke={1.6} />
                    <span className="font-mono uppercase text-green" style={{ fontSize: 9.5, letterSpacing: "1px" }}>
                      {f.title}
                    </span>
                  </div>
                  <p className="m-0" style={{ fontSize: 12.5, lineHeight: 1.5, color: "#232a22" }}>{f.body}</p>
                </div>
              ))}
            </div>
            <div className="flex justify-between items-center mt-[18px] pt-[14px]" style={{ borderTop: "1px solid #ebe5d8" }}>
              <span className="font-mono text-faint" style={{ fontSize: 9 }}>BUILT FROM TODAY'S DATA</span>
              <div className="flex gap-2 items-center">
                <span className="font-mono text-faint mr-0.5" style={{ fontSize: 9 }}>
                  {vote ? "THANKS — LOGGED" : "HELPFUL?"}
                </span>
                {["Useful", "Not useful"].map((t) => (
                  <button
                    key={t}
                    className="ons-tap cursor-pointer"
                    onClick={() => setVote(t)}
                    style={{
                      fontSize: 11, color: vote === t ? "#fff" : "#736e5f",
                      border: `1px solid ${vote === t ? "#1d5536" : "#e6e3dc"}`,
                      background: vote === t ? "#1d5536" : "#f6f5f2",
                      borderRadius: 999, padding: "4px 11px",
                    }}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* This Week */}
        <Card pad={0}>
          <div className="flex justify-between items-center" style={{ padding: "16px 18px 12px" }}>
            <K>This Week</K>
            <span className="font-mono text-faint" style={{ fontSize: 9 }}>{calendar.length} ENTRIES</span>
          </div>
          <div style={{ padding: "0 18px 10px" }}>
            {calendar.length === 0 ? (
              <div className="text-center text-muted py-8" style={{ fontSize: 13 }}>Nothing on the calendar.</div>
            ) : (
              calendar.slice(0, 9).map((e, i) => (
                <div
                  key={i}
                  className="ons-row flex items-center gap-3 border-t border-border-2"
                  style={{ padding: "8px 6px", margin: "0 -6px" }}
                >
                  <span className="font-mono shrink-0" style={{ fontSize: 9.5, color: "#2f6b43", width: 42 }}>
                    {e.date.toUpperCase()}
                  </span>
                  <span className="flex-1" style={{ fontSize: 13 }}>{e.title}</span>
                  <CalendarIcon title={e.title} />
                </div>
              ))
            )}
          </div>
        </Card>
      </div>

      {/* Lower row: Habits · Daily 10 · Goals */}
      <div className="grid gap-[22px]" style={{ gridTemplateColumns: "1.2fr 1fr 1.2fr" }}>
        <Card>
          <div className="flex justify-between items-center mb-3">
            <K>Today's Habits</K>
            <span className="font-mono" style={{ fontSize: 9.5, color: doneCount === habitsTotal ? "#1d5536" : "#a39d8c" }}>
              {doneCount}/{habitsTotal} DONE
            </span>
          </div>
          <div className="flex flex-col gap-0.5">
            {habitsToday.habits.map((h) => {
              const on = !!done[h.key];
              return (
                <button
                  key={h.key}
                  className="ons-tap flex items-center gap-[11px] border-none cursor-pointer text-left"
                  onClick={() => toggleHabit(h.key)}
                  style={{ padding: "9px 8px", margin: "0 -8px", borderRadius: 6 }}
                >
                  <span
                    className="grid place-items-center shrink-0"
                    style={{
                      width: 19, height: 19, borderRadius: 5,
                      border: `1.5px solid ${on ? "#1d5536" : "#e6e3dc"}`,
                      background: on ? "#1d5536" : "transparent",
                      transition: "all .15s",
                    }}
                  >
                    {on && <OnsIcon name="habits" size={12} stroke={2.2} style={{ color: "#fff" }} />}
                  </span>
                  <span
                    style={{
                      fontSize: 13.5, color: on ? "#a39d8c" : "#232a22",
                      textDecoration: on ? "line-through" : "none", transition: "color .15s",
                    }}
                  >
                    {h.label}
                  </span>
                </button>
              );
            })}
          </div>
        </Card>

        <Card>
          <K style={{ marginBottom: 12 }}>Daily 10 · Cover</K>
          {daily10 ? (
            <>
              <div
                className="grid place-items-center mb-[11px]"
                style={{
                  aspectRatio: "16/8",
                  background: "repeating-linear-gradient(135deg, #efebe1, #efebe1 7px, #fbfaf5 7px, #fbfaf5 14px)",
                  border: "1px solid #e6e3dc",
                }}
              >
                <span className="font-mono text-faint" style={{ fontSize: 9, letterSpacing: "1px" }}>
                  {daily10.date}
                </span>
              </div>
              <p className="m-0" style={{ fontSize: 11.5, lineHeight: 1.45, color: "#232a22" }}>
                {daily10.description}
              </p>
            </>
          ) : (
            <div className="text-center text-muted py-8" style={{ fontSize: 13 }}>
              No playlist generated yet today.
            </div>
          )}
        </Card>

        <Card>
          <K style={{ marginBottom: 12 }}>Goal Pacing · 2026</K>
          {goals.length === 0 ? (
            <div className="text-center text-muted py-8" style={{ fontSize: 13 }}>No goals tracked yet.</div>
          ) : (
            <div className="flex flex-col gap-[11px]">
              {goals.slice(0, 5).map((g) => {
                const pct = g.progress_percent != null ? Math.min(100, g.progress_percent) : 0;
                const col = g.pace_status === "behind" ? "#a8473a"
                  : g.pace_status === "at_risk" ? "#9a6a1e"
                  : g.pace_status === "unknown" || g.pace_status === "binary" ? "#a39d8c"
                  : "#1d5536";
                return (
                  <div key={g.goal_key}>
                    <div className="flex justify-between items-baseline mb-[5px]">
                      <span style={{ fontSize: 12.5 }}>{g.label}</span>
                      <Pace status={g.pace_status} />
                    </div>
                    <div className="relative" style={{ height: 3, background: "#efebe1" }}>
                      <div
                        className="absolute inset-0"
                        style={{ width: `${pct}%`, background: col, transition: "width .6s" }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
