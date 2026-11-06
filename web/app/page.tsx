"use client";

// This week — the Home page (Logbook Color, DESIGN.md). The week is the unit: a strip of days (Mon–Sun)
// with the owner's lanes down the side, built only from real data:
//   weather      /home/weather (Open-Meteo, api/weather.py)
//   running      /fitness/run-days (Strava)
//   crossfit     /fitness/crossfit (SugarWOD; newest record shown so stale data is visible)
//   habits       /habits/recent + /habits/today (toggles write through /habits/log)
//   check-in     /checkin/* — owner-only, read only when a write key is already saved (no prompt on load)
//   plans        /home/calendar (today onward)
//   cfb          /cfb/weeks + /cfb/slate + /cfb/schedule (kick days in Denver time)
// Goals on the clock use /goals/progress; only wired goals get a pace, the rest say "not wired".

import Link from "next/link";
import { Fragment, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  homeApi, habitsApi, fitnessApi, goalsApi, cfbApi, checkinApi, sportsApi, hasWriteKey, API_BASE_URL,
  type HomeSummary, type HabitToday, type HabitDay, type RunDay, type CrossfitEntry, type CalendarEvent,
  type Goal, type WeekWeather, type WeatherCondition, type CfbPick, type CfbScheduleGame, type Checkin, type SportsToday,
} from "@/lib/api";
import { GameLine } from "@/components/sports/GameRow";
import { PageHead, Loading, ErrorState } from "@/components/ui/primitives";
import { PixelScene } from "@/components/ui/PixelScene";

const TZ = "America/Denver";
const READING_GOAL = 10; // books in 2026 (fiction 5 + nonfiction 5 in goals/2026.yaml)
const DAY = 86_400_000;

// ── Date helpers (all in Denver) ────────────────────────────────────────────
const isoDenver = (d: Date) => new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
const fromIso = (iso: string) => { const [y, m, d] = iso.split("-").map(Number); return new Date(Date.UTC(y, m - 1, d, 12)); };
const addDays = (iso: string, n: number) => new Date(fromIso(iso).getTime() + n * DAY).toISOString().slice(0, 10);
const fmt = (iso: string, o: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat("en-US", { timeZone: "UTC", ...o }).format(fromIso(iso));
const fmtTime = (d: Date) => new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "numeric", minute: "2-digit" }).format(d).replace(" AM", "").replace(" PM", "");
const plural = (n: number, one: string, many = one + "s") => `${n} ${n === 1 ? one : many}`;
const join = (xs: string[]) => (xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);

function WxIcon({ c }: { c: WeatherCondition }) {
  const p = { fill: "none", stroke: "currentColor", strokeWidth: 1.6, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  const cloud = "M6.5 18.5h11a4 4 0 0 0 .4-8 6 6 0 0 0-11.5 1.6 3.2 3.2 0 0 0 .1 6.4z";
  const small = "M6.5 14h11a3.6 3.6 0 0 0 .4-7.2 5.5 5.5 0 0 0-10.6 1.5 2.9 2.9 0 0 0-.8 5.7z";
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      {c === "sun" && <><circle cx="12" cy="12" r="4" {...p} /><path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8" {...p} /></>}
      {c === "partly" && <><path d="M9 4v1.5M3.5 9.5H5M5.3 5.8l1 1M12.7 5.8l-1 1M6.2 11.5a3.2 3.2 0 0 1 5.9-2.3" {...p} /><path d="M8 19.5h9.5a3.5 3.5 0 0 0 .3-7 5 5 0 0 0-9.6 1.2A2.9 2.9 0 0 0 8 19.5z" {...p} /></>}
      {c === "cloudy" && <path d={cloud} {...p} />}
      {c === "wind" && <path d="M3 9h11a2.5 2.5 0 1 0-2.5-2.5M3 13h15a2.5 2.5 0 1 1-2.5 2.5M3 17h7" {...p} />}
      {c === "rain" && <><path d={small} {...p} /><path d="M8 17.5l-1 2.5M12 17.5l-1 2.5M16 17.5l-1 2.5" {...p} /></>}
      {c === "snow" && <><path d={small} {...p} /><path d="M8 18v.01M12 20v.01M16 18v.01M10 22v.01M14 22v.01" {...p} strokeWidth={2.4} /></>}
    </svg>
  );
}

/** The daily brief as text: paragraphs and **bold**, never injected HTML. */
function Brief({ text }: { text: string }) {
  return (
    <>
      {text.split(/\n{2,}/).map((para, i) => (
        <p key={i} style={{ margin: i ? "10px 0 0" : 0 }}>
          {para.split(/(\*\*[^*]+\*\*)/g).map((seg, j) =>
            seg.startsWith("**") && seg.endsWith("**") ? <b key={j}>{seg.slice(2, -2)}</b> : <Fragment key={j}>{seg.replace(/^#+\s*/gm, "").replace(/\n/g, " ")}</Fragment>,
          )}
        </p>
      ))}
    </>
  );
}

// ── Goals: pace for the wired ones ──────────────────────────────────────────
const GOAL_AREA: Record<string, [string, string, string]> = {
  running_miles: ["l-run", "Run 350 miles", "mi"],
  crossfit_classes: ["l-lift", "160 CrossFit classes", "classes"],
  fiction_books_goal: ["l-read", "Read 5 fiction", "books"],
  nonfiction_books_goal: ["l-read", "Read 5 nonfiction", "books"],
  marathon_completed: ["l-run", "Run a marathon", ""],
};
function pace(g: Goal, yearFrac: number, weeksLeft: number, weeksGone: number) {
  const target = g.target_numeric!, cur = g.current_value!;
  const left = Math.max(0, target - cur), expected = target * yearFrac;
  const perWeek = left / Math.max(weeksLeft, 0.1), avg = cur / Math.max(weeksGone, 0.1);
  if (left === 0) return { state: "ok" as const, label: "Done", needs: "—" };
  if (target === 1) return { state: "risk" as const, label: "Not yet", needs: "1 to go" };
  const needs = g.goal_key === "running_miles" ? `${perWeek.toFixed(1)} mi/wk` : perWeek < 1 ? `1 per ${Math.round(7 / perWeek)} d` : `${perWeek.toFixed(1)}/wk`;
  if (cur >= expected) return { state: "ok" as const, label: "On track", needs };
  if (avg > 0 && perWeek > avg * 3) return { state: "off" as const, label: "Out of reach", needs };
  const behind = expected - cur;
  return { state: "risk" as const, label: g.goal_key === "running_miles" ? `${behind.toFixed(0)} mi behind` : `${Math.ceil(behind)} behind`, needs };
}

export default function HomePage() {
  const [summary, setSummary] = useState<HomeSummary | null>(null);
  const [today, setToday] = useState<HabitToday | null>(null);
  const [recent, setRecent] = useState<HabitDay[]>([]);
  const [runs, setRuns] = useState<RunDay[]>([]);
  const [cf, setCf] = useState<CrossfitEntry[]>([]);
  const [cal, setCal] = useState<CalendarEvent[]>([]);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [wx, setWx] = useState<WeekWeather | null | false>(null);
  const [brief, setBrief] = useState<string | null | false>(null);
  const [sports, setSports] = useState<SportsToday | null | false>(null);
  const [picks, setPicks] = useState<CfbPick[]>([]);
  const [sched, setSched] = useState<CfbScheduleGame[]>([]);
  const [checkins, setCheckins] = useState<Checkin[] | "private">("private");
  const [wxDay, setWxDay] = useState<string | null>(null);
  const [habitErr, setHabitErr] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const weekRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const year = new Date().getFullYear();
    Promise.all([homeApi.summary(), habitsApi.today()])
      .then(([s, t]) => { setSummary(s); setToday(t); })
      .catch((e) => setError(e.message));
    habitsApi.recent(14).then(setRecent).catch(() => {});
    fitnessApi.runDays(year).then(setRuns).catch(() => {});
    fitnessApi.crossfit(60).then(setCf).catch(() => {});
    homeApi.calendar().then(setCal).catch(() => {});
    goalsApi.progress().then(setGoals).catch(() => {});
    homeApi.weather().then(setWx).catch(() => setWx(false));
    sportsApi.today().then(setSports).catch(() => setSports(false));
    fetch(`${API_BASE_URL}/home/brief/latest?brief_type=daily`)
      .then(r => (r.ok ? r.json() : null))
      .then(b => setBrief(b && typeof b.brief_content === "string" ? b.brief_content : false))
      .catch(() => setBrief(false));
    cfbApi.weeks(year).then(async (w) => {
      const wk = w.current_week; if (wk == null) return;
      const [s, g] = await Promise.all([cfbApi.slate(year, wk), cfbApi.schedule(year, wk)]);
      setPicks(s.filter(p => p.meets_publish_bar)); setSched(g);
    }).catch(() => {});
    if (hasWriteKey()) checkinApi.history(14).then(setCheckins).catch(() => setCheckins("private"));
  }, []);

  // On narrow screens the strip scrolls sideways: start it at today rather than Monday.
  useEffect(() => {
    const wrap = weekRef.current, cell = wrap?.querySelector<HTMLElement>(".hd.today"), lane = wrap?.querySelector<HTMLElement>(".hd.lane");
    if (wrap && cell && lane && wrap.scrollWidth > wrap.clientWidth) wrap.scrollLeft += cell.getBoundingClientRect().left - lane.getBoundingClientRect().right - 4;
  }, [summary, today]);

  const todayIso = summary?.date ?? isoDenver(new Date());
  const monday = addDays(todayIso, -((fromIso(todayIso).getUTCDay() + 6) % 7));
  const days = useMemo(() => Array.from({ length: 7 }, (_, i) => addDays(monday, i)), [monday]);
  const inWeek = (iso: string) => iso >= days[0] && iso <= days[6];

  if (error) return <div className="ons-page" style={{ padding: "34px 44px 48px" }}><ErrorState message={error} /></div>;
  if (!summary || !today) return <Loading label="Loading this week…" />;

  // ── Per-day facts ─────────────────────────────────────────────────────────
  const runsBy = new Map<string, RunDay[]>();
  runs.forEach(r => { const d = r.start_date.slice(0, 10); if (inWeek(d)) runsBy.set(d, [...(runsBy.get(d) ?? []), r]); });
  const weekRuns = Array.from(runsBy.values()).flat();
  const weekMiles = weekRuns.reduce((a, r) => a + r.distance_miles, 0);
  const cfDays = new Set(cf.map(e => e.date));
  const cfNewest = cf.map(e => e.date).sort().pop() ?? null;
  const cfThisWeek = days.filter(d => cfDays.has(d)).length;
  const daysSinceCf = cfNewest ? Math.round((fromIso(todayIso).getTime() - fromIso(cfNewest).getTime()) / DAY) : null;
  const habitBy = new Map(recent.map(h => [h.date, h]));
  const habitKeys = today.habits.map(h => h.key);
  const doneToday = today.habits.filter(h => h.done).length;
  const calBy = new Map<string, string[]>();
  cal.forEach(e => { if (inWeek(e.date)) calBy.set(e.date, [...(calBy.get(e.date) ?? []), e.title]); });
  const checkinBy = checkins === "private" ? null : new Map(checkins.map(c => [c.date, c]));
  const kicks = picks.map(p => {
    const [away, home] = p.matchup.split(" @ ");
    const g = sched.find(s => s.away_team === away && s.home_team === home);
    return g?.start_date ? new Date(g.start_date) : null;
  });
  const cfbBy = new Map<string, Date[]>();
  kicks.forEach(k => { if (k) { const d = isoDenver(k); cfbBy.set(d, [...(cfbBy.get(d) ?? []), k].sort((a, b) => +a - +b)); } });
  const cfbDays = Array.from(cfbBy.keys()).sort();
  const lastCfbDay = cfbDays[cfbDays.length - 1];
  const graded = picks.filter(p => p.outcome === "win" || p.outcome === "loss" || p.outcome === "push").length;
  const wxBy = new Map((wx ? wx.days : []).map(d => [d.date, d]));

  // ── Year pace ─────────────────────────────────────────────────────────────
  const y = +todayIso.slice(0, 4);
  const daysInYear = (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0 ? 366 : 365;
  const dayOfYear = Math.round((fromIso(todayIso).getTime() - fromIso(`${y}-01-01`).getTime()) / DAY) + 1;
  const yearFrac = dayOfYear / daysInYear, daysLeft = daysInYear - dayOfYear;
  const weeksLeft = daysLeft / 7, weeksGone = dayOfYear / 7;
  const books = summary.stat_cards.books_read ?? 0;
  const booksExpected = READING_GOAL * yearFrac;
  const nextBookDue = addDays(`${y}-01-01`, Math.ceil(((books + 1) / READING_GOAL) * daysInYear) - 1);
  const wired = goals.filter(g => GOAL_AREA[g.goal_key] && g.target_numeric != null && g.current_value != null);
  const habitGoals = goals.filter(g => g.description?.includes("habits")).length;
  const notWired = goals.filter(g => g.current_value == null).length;

  // ── Words ─────────────────────────────────────────────────────────────────
  const dayName = (iso: string) => (iso === todayIso ? "today" : fmt(iso, { weekday: "long" }));
  const ahead = (wx ? wx.days : []).filter(d => d.date >= todayIso);
  const wet = ahead.find(d => d.condition === "rain" || d.condition === "snow");
  const windy = ahead.find(d => d.condition === "wind");
  const weatherLine = !wx ? null
    : wet ? <><b>{wet.condition === "snow" ? "Snow" : "Rain"} {dayName(wet.date)}</b>{wet.date !== todayIso ? ", so get your run in before then" : ""}.</>
    : windy ? <>{fmt(windy.date, { weekday: "long" })} is windy (gusts {Math.round(windy.gust_mph ?? 0)}); the rest of the week is dry.</>
    : ahead.length ? <>Dry for the rest of the week, highs {Math.min(...ahead.map(d => d.high_f))}–{Math.max(...ahead.map(d => d.high_f))}°.</> : null;
  const weekendBits = [
    ...(picks.length && lastCfbDay && lastCfbDay >= todayIso ? [`${plural(picks.length, "pick")} ${fmt(cfbDays[0], { weekday: "long" })} from ${fmtTime(cfbBy.get(cfbDays[0])![0])}`] : []),
    ...days.filter(d => d >= todayIso).flatMap(d => (calBy.get(d) ?? []).filter(t => /bday|birthday/i.test(t)).map(t => `${t.replace(/!$/, "")} ${d === todayIso ? "today" : `on ${dayName(d)}`}`)),
  ];
  const lede = (
    <>
      <b>{weekRuns.length ? `${plural(weekRuns.length, "run")} (${weekMiles.toFixed(1)} mi)` : "No runs yet"}</b> this week
      {cfThisWeek ? `, ${plural(cfThisWeek, "CrossFit class", "CrossFit classes")}` : daysSinceCf != null && daysSinceCf > 6 ? <> and <b>no CrossFit logged since {fmt(cfNewest!, { month: "short", day: "numeric" })}</b></> : ""}.
      {weatherLine && <> {weatherLine}</>}
      {weekendBits.length > 0 && <> Coming up: {join(weekendBits)}.</>}
    </>
  );

  const steps: Array<{ cls: string; href: string; title: string; detail: string }> = [];
  if (checkinBy && !checkinBy.get(todayIso)?.logged_at) steps.push({ cls: "l-check", href: "/checkin", title: "Check in", detail: "Today's check-in is due" });
  if (doneToday < today.total_count) steps.push({ cls: "l-habit", href: "/habits", title: `Log ${plural(today.total_count - doneToday, "habit")}`, detail: doneToday ? `${doneToday} of ${today.total_count} done` : "None done yet today" });
  if (daysSinceCf != null && daysSinceCf > 6) steps.push({ cls: "l-lift", href: "/fitness", title: "Get a class in", detail: `No CrossFit logged since ${fmt(cfNewest!, { month: "short", day: "numeric" })}` });
  if (books < Math.floor(booksExpected)) steps.push({ cls: "l-read", href: "/reading", title: `Finish book ${books + 1}`, detail: nextBookDue > todayIso ? `By ${fmt(nextBookDue, { month: "short", day: "numeric" })} to catch up` : "You're behind pace; next one now" });
  if (steps.length < 4 && wet && wet.date > todayIso) steps.push({ cls: "l-run", href: "/fitness", title: "Run before the weather", detail: `${wet.condition === "snow" ? "Snow" : "Rain"} ${fmt(wet.date, { weekday: "long" })}` });

  // ── Scene weather: the selected day, or current conditions today ─────────
  const sel = wxDay && wxBy.get(wxDay);
  const sceneWx = sel ? sel.condition : wx ? wx.current.condition : "sun";
  const sceneTemp = sel ? sel.high_f : wx ? wx.current.temp_f ?? "" : "";

  async function toggleHabit(key: string, on: boolean) {
    setHabitErr(null);
    setToday(t => t && { ...t, habits: t.habits.map(h => (h.key === key ? { ...h, done: on } : h)) });
    try { setToday(await habitsApi.log(key, on)); habitsApi.recent(14).then(setRecent).catch(() => {}); }
    catch (e: any) { setToday(t => t && { ...t, habits: t.habits.map(h => (h.key === key ? { ...h, done: !on } : h)) }); setHabitErr(e.message ?? "Couldn't save"); }
  }

  const lane = (cls: string, label: string, cell: (d: string) => ReactNode) => (
    <>
      <div className={`lane ${cls}`}><span>{label}</span></div>
      {days.map((d, i) => <div key={d} className={[cls, d === todayIso && "today", i >= 5 && "we"].filter(Boolean).join(" ")}>{cell(d)}</div>)}
    </>
  );

  return (
    <div className="ons-page" style={{ padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" }}>
      <PageHead
        title="This week"
        kicker={`${fmt(todayIso, { weekday: "long", month: "long", day: "numeric" })} · week of ${fmt(days[0], { month: "short", day: "numeric" })}–${fmt(days[6], { day: "numeric" })} · ${plural(daysLeft, "day")} left in ${y} · ${wx ? wx.place : "Denver"}`}
        sub={lede}
        right={<div className="flex gap-2"><Link className="ons-tap ons-btn" href="/checkin">Check in</Link><Link className="ons-tap ons-btn pri" href="/habits">Log today's habits</Link></div>}
        scene={<PixelScene scene="week" weather={sceneWx} temp={sceneTemp} label={`a jogger and the pets on the trail${wx ? `, ${sel ? sel.label : wx.current.label}` : ""}`} />}
      />

      {steps.length > 0 && (
        <ol className="ons-next" aria-label="Next steps">
          {steps.slice(0, 4).map(s => <li key={s.title} className={s.cls}><Link href={s.href}><b>{s.title}</b><span>{s.detail}</span></Link></li>)}
        </ol>
      )}

      <div className="ons-grid">
        <section className="ons-card s12" aria-labelledby="wk-h">
          <div className="ons-ch"><h2 id="wk-h">The week</h2><span className="aside">{fmt(days[0], { weekday: "short", month: "short", day: "numeric" })} – {fmt(days[6], { weekday: "short", month: "short", day: "numeric" })} · {weekMiles.toFixed(1)} mi run{wx ? ` · weather ${wx.source}` : ""}</span></div>
          <div className="ons-weekwrap" ref={weekRef}><div className="ons-week" role="table" aria-label="This week by day">
            <div className="hd lane" />
            {days.map((d, i) => <div key={d} className={["hd", d === todayIso && "today", i >= 5 && "we"].filter(Boolean).join(" ")}>{fmt(d, { weekday: "short" })}{d === todayIso ? " · today" : ""}<b>{fmt(d, { day: "numeric" })}</b></div>)}

            {lane("l-wx", "Weather", d => {
              const w = wxBy.get(d);
              if (wx === false) return d === todayIso ? <span className="ons-mk quiet">Unavailable</span> : null;
              if (!w) return null;
              const pressed = (wxDay ?? todayIso) === d;
              return (
                <button type="button" className="ons-wx" aria-pressed={pressed} onClick={() => setWxDay(d === todayIso ? null : d)}
                        aria-label={`${fmt(d, { weekday: "long" })}: ${w.label}, high ${w.high_f}, low ${w.low_f}. Show in the scene`}>
                  <WxIcon c={w.condition} /><span className="n"><b>{w.high_f}°</b> {w.low_f}°</span><small>{w.label}</small>
                </button>
              );
            })}
            {lane("l-run", "Running", d => (runsBy.get(d) ?? []).map(r => <span key={r.strava_id} className="ons-mk ons-n">{r.distance_miles.toFixed(2)} mi · {Math.round(r.moving_time_s / 60)} m</span>))}
            {lane("l-lift", "CrossFit", d => cfDays.has(d) ? <span className="ons-mk">Class</span> : d === todayIso ? <span className="ons-mk miss">Not logged</span> : null)}
            {lane("l-habit", "Habits", d => {
              if (d > todayIso) return null;
              const h = d === todayIso ? Object.fromEntries(today.habits.map(x => [x.key, x.done])) : habitBy.get(d);
              if (!h) return <span className="ons-mk quiet">–</span>;
              const n = habitKeys.filter(k => h[k]).length;
              return <span className="ons-dots" aria-label={`${n} of ${habitKeys.length}`}>{habitKeys.map(k => <i key={k} className={h[k] ? "d" : ""} />)}</span>;
            })}
            {lane("l-check", "Check-in", d => {
              if (!checkinBy) return d === todayIso ? <Link href="/checkin" className="ons-mk quiet" style={{ textDecoration: "none" }}>Private</Link> : null;
              if (d > todayIso) return null;
              const c = checkinBy.get(d);
              return c?.logged_at ? <span className="ons-mk ons-n">Readiness {c.readiness}</span> : d === todayIso ? <span className="ons-mk miss">Due</span> : <span className="ons-mk quiet">–</span>;
            })}
            {lane("l-plan", "Plans", d => (calBy.get(d) ?? []).map((t, i) => <span key={i} className={`ons-mk ${/bday|birthday/i.test(t) ? "solid" : ""}`} title={t}>{t}</span>))}
            {lane("l-edge", "CFB", d => {
              const ks = cfbBy.get(d);
              if (ks?.length) { const s = ks; return <><span className="ons-mk solid">{plural(ks.length, "pick")}</span><span className="ons-mk ons-n">{fmtTime(s[0])}–{fmtTime(s[s.length - 1])}</span></>; }
              if (lastCfbDay && todayIso > lastCfbDay && d === addDays(lastCfbDay, 1)) return <span className="ons-mk quiet">{graded === picks.length ? "Graded" : graded ? `${graded} of ${picks.length} graded` : "Grading"}</span>;
              return null;
            })}
          </div></div>
          <div className="ons-legend">
            <span><i style={{ background: "var(--run-mark)" }} />Logged</span>
            <span><i style={{ outline: "1px dashed var(--muted)", outlineOffset: -1 }} />Missing or due</span>
            <span><i style={{ boxShadow: "inset 0 0 0 1px var(--hue)", background: "var(--hue-soft)" }} />Today</span>
            {cfNewest && daysSinceCf != null && daysSinceCf > 6 && <span>SugarWOD's newest record is {fmt(cfNewest, { month: "short", day: "numeric" })}; if you've been going, the export may be stale.</span>}
          </div>
        </section>

        <section className="ons-card s8" aria-labelledby="pace-h">
          <div className="ons-ch"><h2 id="pace-h">Goals on the clock</h2><span className="aside">{plural(daysLeft, "day")} left · {Math.round(yearFrac * 100)}% of the year gone</span></div>
          <table className="ons-table">
            <thead><tr><th>Goal</th><th className="hide-p">Progress · line is today</th><th className="r">Needs</th><th className="r">State</th></tr></thead>
            <tbody>
              <tr className="l-read">
                <td><div className="ons-goal"><i /><div>Read {READING_GOAL} books<span className="sub ons-n">{books} of {READING_GOAL}</span></div></div></td>
                <td className="hide-p"><div className="ons-bar"><b style={{ width: `${Math.min(100, (books / READING_GOAL) * 100)}%` }} /><i style={{ left: `${yearFrac * 100}%` }} /></div></td>
                <td className="r ons-n">{books >= READING_GOAL ? "—" : `1 per ${Math.max(1, Math.round(daysLeft / (READING_GOAL - books)))} d`}</td>
                <td className="r">{books >= booksExpected ? <span className="ons-badge ok">On track</span> : <span className="ons-badge risk">{Math.ceil(booksExpected - books)} behind</span>}</td>
              </tr>
              {wired.map(g => {
                const [cls, label, unit] = GOAL_AREA[g.goal_key];
                const p = pace(g, yearFrac, weeksLeft, weeksGone);
                return (
                  <tr key={g.goal_key} className={cls}>
                    <td><div className="ons-goal"><i /><div>{label}<span className="sub ons-n">{+g.current_value!.toFixed(2)} of {g.target_numeric}{unit ? ` ${unit}` : ""}</span></div></div></td>
                    <td className="hide-p"><div className="ons-bar"><b style={{ width: `${Math.min(100, (g.current_value! / g.target_numeric!) * 100)}%` }} /><i style={{ left: `${yearFrac * 100}%` }} /></div></td>
                    <td className="r ons-n">{p.needs}</td>
                    <td className="r"><span className={`ons-badge ${p.state}`}>{p.label}</span></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="ons-note">
            "Out of reach" means the rate needed is more than three times this year's average. {habitGoals > 0 && <>{plural(habitGoals, "daily habit goal")} {habitGoals === 1 ? "is" : "are"} tracked on Habits. </>}
            {notWired > 0 && <><Link href="/goals" className="text-hue">{plural(notWired, "more goal")}</Link> {notWired === 1 ? "has" : "have"} no data source wired yet.</>}
          </p>
        </section>

        <div className="s4 ons-col">
          <section className="ons-card t t-habit" aria-labelledby="hab-h">
            <div className="ons-ch"><h2 id="hab-h">Today's habits</h2><span className="aside ons-n">{doneToday} of {today.total_count}</span></div>
            {today.habits.map(h => (
              <button key={h.key} type="button" className="ons-hb" aria-pressed={h.done} onClick={() => toggleHabit(h.key, !h.done)}>
                <span className="box">{h.done && <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>}</span>
                {h.label}
              </button>
            ))}
            {habitErr && <p className="ons-note" role="alert">{habitErr}</p>}
          </section>
          <section className="ons-card" aria-labelledby="teams-h">
            <div className="ons-ch"><h2 id="teams-h">My teams today</h2><Link href="/sports" className="aside" style={{ textDecoration: "none" }}>All sports</Link></div>
            {sports === false ? <p className="ons-note m-0">Couldn't load scores.</p>
              : !sports ? <p className="ons-note m-0">Loading…</p>
              : sports.my_teams.length ? sports.my_teams.slice(0, 3).map(g => <GameLine key={g.id} g={g} label={g.my_team ?? undefined} />)
              : sports.upcoming.length ? <>{<p className="ons-note" style={{ margin: "0 0 6px" }}>None today. Next up:</p>}{sports.upcoming.slice(0, 3).map(g => <GameLine key={g.id} g={g} withDay label={g.my_team ?? undefined} />)}</>
              : <p className="ons-note m-0">None of your teams play today.</p>}
          </section>
        </div>

        <section className="ons-card s8" aria-labelledby="brief-h">
          <div className="ons-ch"><h2 id="brief-h">Today's brief</h2><span className="aside">Written during the morning sync</span></div>
          <div style={{ fontSize: 15, lineHeight: "23px", color: "var(--ink-2)", maxWidth: "70ch" }}>
            {brief ? <Brief text={brief} /> : <p className="m-0 text-muted">{brief === false ? "No brief yet today. It's written during the 9 am sync." : "Loading the brief…"}</p>}
          </div>
        </section>

        <div className="s4 ons-col">
          {summary.daily10 && (
            <section className="ons-card" aria-labelledby="d10-h">
              <div className="ons-ch"><h2 id="d10-h">Daily 10</h2><Link href="/music" className="aside" style={{ textDecoration: "none" }}>Music</Link></div>
              <p className="m-0" style={{ fontSize: 13, lineHeight: "19px", color: "var(--ink-2)" }}>{summary.daily10.description}</p>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
