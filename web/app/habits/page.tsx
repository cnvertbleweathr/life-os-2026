"use client";

import Link from "next/link";
import { useEffect, useState, useCallback } from "react";
import {
  habitsApi, parseLocalDate,
  type HabitToday, type HabitStreak, type HabitDay, type HabitYtd,
} from "@/lib/api";
import { PageHead, Loading, ErrorState } from "@/components/ui/primitives";

export default function HabitsPage() {
  const [today, setToday] = useState<HabitToday | null>(null);
  const [streaks, setStreaks] = useState<HabitStreak[] | null>(null);
  const [recent, setRecent] = useState<HabitDay[]>([]);
  const [done, setDone] = useState<Record<string, boolean>>({});
  const [pending, setPending] = useState<Record<string, boolean>>({});
  const [saveError, setSaveError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ytd, setYtd] = useState<HabitYtd[]>([]);

  useEffect(() => {
    habitsApi.ytd().then(setYtd).catch(() => {});
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

  if (error) return <div className="ons-page" style={{ padding: "34px 44px 48px" }}><ErrorState message={error} /></div>;
  if (!today || !streaks) return <Loading />;

  const habits = today.habits;
  const total = today.total_count;
  const doneCount = habits.filter((h) => done[h.key]).length;
  const streakFor = (key: string) => streaks.find((s) => s.habit === key);
  const ytdFor = (key: string) => ytd.find((y) => y.habit === key);
  const todayLong = parseLocalDate(today.date).toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });

  // The strip: last 21 days, today last. Today's cells follow the live toggles.
  const days = recent.slice(-21);
  const isOn = (d: HabitDay, k: string) => (d.date === today.date ? !!done[k] : !!d[k]);
  const lastLogged = [...recent].reverse().find((d) => d.date !== today.date && d.logged);
  const gap = lastLogged ? Math.round((parseLocalDate(today.date).getTime() - parseLocalDate(lastLogged.date).getTime()) / 86_400_000) : null;
  const best = [...ytd].sort((a, b) => b.completion_rate_pct - a.completion_rate_pct)[0];
  const labelFor = (k: string) => habits.find((h) => h.key === k)?.label ?? k;
  const fmtDay = (iso: string, o: Intl.DateTimeFormatOptions) => parseLocalDate(iso).toLocaleDateString("en-US", o);

  const lede = (
    <>
      <b>{doneCount} of {total} done today.</b>{" "}
      {gap != null && gap > 1 ? <>Your last logged day was {fmtDay(lastLogged!.date, { month: "short", day: "numeric" })}, {gap} days ago; one tap a habit gets the streak going again.</> : doneCount < total ? <>{total - doneCount} to go before midnight.</> : <>All in. Nice.</>}
      {best && best.days_observed > 0 && <> {labelFor(best.habit)} is the one you keep most ({best.done_days} of {best.days_observed} logged days).</>}
    </>
  );

  return (
    <div className="ons-page" style={{ padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" }}>
      <PageHead
        title="Habits"
        kicker={`${todayLong} · ${total} daily habits · each logged day counts toward your 2026 goals`}
        sub={lede}
        right={<Link className="ons-tap ons-btn" href="/checkin">Check in</Link>}
      />

      <div className="ons-grid">
        <div className="s4 ons-col no-stretch">
          <section className="ons-card t t-habit" aria-labelledby="today-h">
            <div className="ons-ch"><h2 id="today-h">Today</h2><span className="aside ons-n">{doneCount} of {total}</span></div>
            {habits.map((h) => (
              <button key={h.key} type="button" className="ons-hb" aria-pressed={!!done[h.key]} aria-busy={!!pending[h.key]} onClick={() => toggle(h.key)}>
                <span className="box">{done[h.key] && <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>}</span>
                {h.label}
                <span className="meta">{streakFor(h.key)?.current_streak ? `${streakFor(h.key)!.current_streak} d` : ""}</span>
              </button>
            ))}
            {saveError && <p className="ons-note" role="alert">{saveError}</p>}
            <p className="ons-note">Saves straight to the habit log; it loads into ONS overnight.</p>
          </section>
        </div>

        <section className="ons-card s8" aria-labelledby="strip-h">
          <div className="ons-ch"><h2 id="strip-h">Last 21 days</h2><span className="aside">{fmtDay(days[0]?.date ?? today.date, { month: "short", day: "numeric" })} – today</span></div>
          <div className="ons-weekwrap">
            <table className="ons-table ons-habit-strip">
              <thead><tr><th />{days.map((d) => <th key={d.date} className={d.date === today.date ? "is-today" : ""} title={d.date}>{fmtDay(d.date, { weekday: "narrow" })}<span className="sub ons-n">{fmtDay(d.date, { day: "numeric" })}</span></th>)}</tr></thead>
              <tbody>
                {habits.map((h) => (
                  <tr key={h.key}>
                    <td className="lab">{h.label}</td>
                    {days.map((d) => <td key={d.date} className={d.date === today.date ? "is-today" : ""}><i className={isOn(d, h.key) ? "on" : d.logged || d.date === today.date ? "off" : "none"} aria-label={`${h.label} ${d.date}: ${isOn(d, h.key) ? "done" : d.logged ? "not done" : "not logged"}`} /></td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="ons-legend"><span><i style={{ background: "var(--habit-mark)" }} />Done</span><span><i style={{ outline: "1.5px solid var(--habit-mark)", outlineOffset: -1.5 }} />Logged, not done</span><span><i style={{ background: "var(--rule)" }} />Not logged</span></div>
        </section>

        <section className="ons-card s12" aria-labelledby="per-h">
          <div className="ons-ch"><h2 id="per-h">By habit</h2><span className="aside">Streaks and logged days this year</span></div>
          <table className="ons-table">
            <thead><tr><th>Habit</th><th className="r">Today</th><th className="r">Streak</th><th className="r hide-p">Longest</th><th className="r">Logged days done</th></tr></thead>
            <tbody>
              {habits.map((h) => {
                const st = streakFor(h.key), y = ytdFor(h.key);
                return (
                  <tr key={h.key}>
                    <td>{h.label}</td>
                    <td className="r">{done[h.key] ? <span className="ons-badge ok">Done</span> : <span className="ons-badge none">Not yet</span>}</td>
                    <td className="r ons-n">{st?.current_streak ?? 0} d</td>
                    <td className="r ons-n hide-p">{st?.longest_streak ?? 0} d</td>
                    <td className="r ons-n">{y ? `${y.done_days} of ${y.days_observed} · ${Math.round(y.completion_rate_pct)}%` : "–"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="ons-note">"Logged days" counts only days with an entry in the habit log, so a missed day with no entry doesn't count against the rate. The Goals page counts each habit against all 366 days.</p>
        </section>
      </div>
    </div>
  );
}
