"use client";

// Fitness (Logbook Color). Running is blue, CrossFit amber, everywhere on the page. Real data only:
//   runs        /fitness/run-days (every 2026 run from strava.activities) + /fitness/summary (YTD totals)
//   crossfit    /fitness/crossfit (SugarWOD export; score shown as SugarWOD displays it, with its type)
//   goals       /goals/progress (running_miles, crossfit_classes, marathon_completed, squat_max_lbs)
//   readiness   /checkin/today — owner-only, read only when a write key is already saved (no prompt on load)
// Fixes from docs/design/critique.md §5: readiness on the page, charts with scales, WOD scores with units,
// "heaviest logged set" instead of "current max", a heatmap that fills its card and works by tap.

import { useEffect, useMemo, useState } from "react";
import { fitnessApi, goalsApi, checkinApi, hasWriteKey, type FitnessSummary, type CrossfitEntry, type RunDay, type Goal, type Checkin } from "@/lib/api";
import { PageHead, Loading, ErrorState } from "@/components/ui/primitives";
import { PixelScene } from "@/components/ui/PixelScene";

const TZ = "America/Denver";
const DAY = 86_400_000;
const isoDenver = (d: Date) => new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
const fromIso = (iso: string) => { const [y, m, d] = iso.slice(0, 10).split("-").map(Number); return new Date(Date.UTC(y, m - 1, d, 12)); };
const addDays = (iso: string, n: number) => new Date(fromIso(iso).getTime() + n * DAY).toISOString().slice(0, 10);
const daysBetween = (a: string, b: string) => Math.round((fromIso(b).getTime() - fromIso(a).getTime()) / DAY);
const fmt = (iso: string, o: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat("en-US", { timeZone: "UTC", ...o }).format(fromIso(iso));
const short = (iso: string) => fmt(iso, { month: "short", day: "numeric" });
const plural = (n: number, one: string, many = one + "s") => `${n} ${n === 1 ? one : many}`;
const clock = (s: number) => { s = Math.round(s); const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = String(s % 60).padStart(2, "0"); return h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`; };
const pace = (secPerMile: number) => clock(secPerMile);
const one = (x: number) => (Math.round(x * 10) / 10).toFixed(1);

/** A SugarWOD score as words: "18:25" for time, "4+7 rounds", "73 reps", "185 lb". */
function score(c: CrossfitEntry): [string, string] {
  const d = c.best_result_display ?? (c.best_result_raw != null ? String(c.best_result_raw) : "");
  switch (c.score_type) {
    case "Load": return [`${d} lb`, ""];
    case "Reps": return [d, "reps"];
    case "Rounds + Reps": return [d, "rounds"];
    case "Meters": return [`${d} m`, ""];
    case "Checkbox": return ["Done", ""];
    case "Other / Text": return [d || "–", ""];
    default: return d.includes(":") ? [d, "for time"] : [d || "–", ""];
  }
}

const READINESS: Array<[number, string, string]> = [
  [0.78, "Primed", "a hard session or a long run is on"],
  [0.6, "Steady", "train as planned"],
  [0.42, "Manage load", "keep it easy: an easy run or skill work"],
  [0, "Recover", "rest, walk or do mobility today"],
];

type Day = { iso: string; runs: RunDay[]; cf: CrossfitEntry[] };

export default function FitnessPage() {
  const [sum, setSum] = useState<FitnessSummary | null>(null);
  const [runs, setRuns] = useState<RunDay[] | null>(null);
  const [cf, setCf] = useState<CrossfitEntry[] | null>(null);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [checkin, setCheckin] = useState<Checkin | null | "private">("private");
  const [error, setError] = useState<string | null>(null);
  const [today, setToday] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [allRuns, setAllRuns] = useState(false);
  const [allCf, setAllCf] = useState(false);
  const [allLifts, setAllLifts] = useState(false);

  useEffect(() => {
    const t = isoDenver(new Date());
    setToday(t);
    const year = +t.slice(0, 4);
    Promise.all([fitnessApi.summary(), fitnessApi.runDays(year), fitnessApi.crossfit(500)])
      .then(([s, r, c]) => { setSum(s); setRuns(r); setCf(c); })
      .catch((e) => setError(e.message));
    goalsApi.progress().then(setGoals).catch(() => {});
    if (hasWriteKey()) checkinApi.today().then(setCheckin).catch(() => setCheckin("private"));
  }, []);

  const data = useMemo(() => {
    if (!runs || !cf || !today) return null;
    const y = +today.slice(0, 4);
    const daysInYear = (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0 ? 366 : 365;
    const dayOfYear = daysBetween(`${y}-01-01`, today) + 1;
    const yearFrac = dayOfYear / daysInYear, daysLeft = daysInYear - dayOfYear, weeksLeft = daysLeft / 7, weeksGone = dayOfYear / 7;

    const byDay = new Map<string, Day>();
    const day = (iso: string) => byDay.get(iso) ?? (byDay.set(iso, { iso, runs: [], cf: [] }), byDay.get(iso)!);
    runs.forEach((r) => day(r.start_date.slice(0, 10)).runs.push(r));
    cf.forEach((c) => day(c.date).cf.push(c));

    // Weeks run Monday to Sunday, from the week holding Jan 1 to this one.
    const firstMon = addDays(`${y}-01-01`, -((fromIso(`${y}-01-01`).getUTCDay() + 6) % 7));
    const weeks: string[] = [];
    for (let m = firstMon; m <= today; m = addDays(m, 7)) weeks.push(m);
    const weekMiles = weeks.map((m) => Array.from({ length: 7 }, (_, i) => byDay.get(addDays(m, i))).reduce((a, d) => a + (d ? d.runs.reduce((b, r) => b + r.distance_miles, 0) : 0), 0));
    const weekClasses = weeks.map((m) => Array.from({ length: 7 }, (_, i) => byDay.get(addDays(m, i))).filter((d) => d && d.cf.length).length);

    const miles = runs.reduce((a, r) => a + r.distance_miles, 0);
    const since28 = addDays(today, -27);
    const miles28 = runs.filter((r) => r.start_date.slice(0, 10) >= since28).reduce((a, r) => a + r.distance_miles, 0);
    const classDays = Array.from(new Set(cf.map((c) => c.date))).sort();
    const classes28 = classDays.filter((d) => d >= since28).length;
    const newestCf = classDays[classDays.length - 1] ?? null;
    const trainDays = Array.from(byDay.values()).filter((d) => d.iso.startsWith(String(y)) && (d.runs.length || d.cf.length)).length;
    const trainDays28 = Array.from(byDay.values()).filter((d) => d.iso >= since28 && (d.runs.length || d.cf.length)).length;
    const longest = runs.reduce<RunDay | null>((a, r) => (!a || r.distance_miles > a.distance_miles ? r : a), null);
    const totalSec = runs.reduce((a, r) => a + r.moving_time_s, 0);

    // Heaviest logged working set per barbell lift (SugarWOD "Load" scores). Not a tested max.
    const lifts = new Map<string, { lift: string; best: CrossfitEntry; latest: CrossfitEntry; n: number }>();
    cf.filter((c) => c.barbell_lift && c.best_result_raw != null && (c.score_type ?? "Load") === "Load").forEach((c) => {
      const l = lifts.get(c.barbell_lift!);
      if (!l) lifts.set(c.barbell_lift!, { lift: c.barbell_lift!, best: c, latest: c, n: 1 });
      else { l.n++; if (c.best_result_raw! > l.best.best_result_raw!) l.best = c; if (c.date > l.latest.date) l.latest = c; }
    });

    return {
      y, yearFrac, daysLeft, weeksLeft, weeksGone, byDay, weeks, weekMiles, weekClasses, miles, miles28, classDays, classes28,
      newestCf, trainDays, trainDays28, longest, totalSec,
      lifts: Array.from(lifts.values()).sort((a, b) => b.latest.date.localeCompare(a.latest.date)),
    };
  }, [runs, cf, today]);

  if (error) return <div className="ons-page" style={{ padding: "34px 44px 48px" }}><ErrorState message={error} /></div>;
  if (!sum || !data || !today || !runs || !cf) return <Loading label="Loading fitness…" />;

  const d = data;
  const goal = (k: string) => goals.find((g) => g.goal_key === k);
  const milesGoal = goal("running_miles")?.target_numeric ?? null;
  const classGoal = goal("crossfit_classes")?.target_numeric ?? null;
  const squatGoal = goal("squat_max_lbs")?.target_numeric ?? null;
  const marathon = goal("marathon_completed");
  const classes = d.classDays.length;
  const daysSinceCf = d.newestCf ? daysBetween(d.newestCf, today) : null;
  const avgPaceSec = d.miles ? d.totalSec / d.miles : 0;

  type Pace = { cls: "ok" | "risk" | "off"; label: string; perWeek: number };
  const paceOf = (cur: number, target: number): Pace => {
    const left = Math.max(0, target - cur), perWeek = left / Math.max(d.weeksLeft, 0.1), avg = cur / Math.max(d.weeksGone, 0.1);
    if (left === 0) return { cls: "ok", label: "Done", perWeek: 0 };
    if (cur >= target * d.yearFrac) return { cls: "ok", label: "On track", perWeek };
    if (avg > 0 && perWeek > avg * 3) return { cls: "off", label: "Out of reach", perWeek };
    return { cls: "risk", label: "Behind", perWeek };
  };
  const mp = milesGoal ? paceOf(d.miles, milesGoal) : null;
  const cp = classGoal ? paceOf(classes, classGoal) : null;
  const ready = checkin !== "private" && checkin?.logged_at ? READINESS.find(([min]) => checkin.readiness >= min)! : null;
  const backSquat = d.lifts.find((l) => /back squat/i.test(l.lift));

  const lede = (
    <>
      {milesGoal && mp ? (
        <>
          <b>{Math.round(d.miles)} of {milesGoal} miles</b> in {plural(runs.length, "run")}.{" "}
          {mp.cls === "ok" ? <>You&apos;re on pace; {one(mp.perWeek)} mi a week finishes it.</>
            : <>The rest needs <b>{one(mp.perWeek)} mi a week</b> through Dec 31, and the last four weeks averaged {one(d.miles28 / 4)}{mp.perWeek > d.miles28 / 4 ? ", so add a run or stretch the long one" : ""}.</>}
        </>
      ) : <><b>{one(d.miles)} miles</b> in {plural(runs.length, "run")} this year.</>}{" "}
      {classGoal && cp && (
        <>
          <b>{classes} of {classGoal} CrossFit classes</b>
          {cp.cls === "off" ? <>: {classGoal} is out of reach this year ({classGoal - classes} in {Math.round(d.weeksLeft)} weeks would be {Math.round(cp.perWeek)} a week).</>
            : cp.cls === "ok" ? <>, on pace.</> : <>, {one(cp.perWeek)} a week to finish.</>}{" "}
        </>
      )}
      {daysSinceCf != null && daysSinceCf > 6 && <>SugarWOD&apos;s newest record is {short(d.newestCf!)}, {daysSinceCf} days ago; if you&apos;ve been going, the export is stale. </>}
      {ready && <>Today&apos;s check-in says <b>{ready[1].toLowerCase()}</b>: {ready[2]}.</>}
    </>
  );

  // ── Training calendar ──────────────────────────────────────────────────────
  const selDay = sel ?? Array.from(d.byDay.keys()).filter((k) => k <= today).sort().pop() ?? today;
  const selFacts = d.byDay.get(selDay);
  const maxWeekMiles = Math.max(1, ...d.weekMiles);
  const maxWeekClasses = Math.max(1, ...d.weekClasses);
  // A week belongs to the month its Thursday falls in; label the first week of each month.
  const monthOf = (m: string) => fmt(addDays(m, 3), { month: "short" });
  const monthStarts = d.weeks.map((m, i) => (i === 0 ? "Jan" : monthOf(m) !== monthOf(d.weeks[i - 1]) ? monthOf(m) : ""));
  const pick = (e: React.SyntheticEvent) => { const iso = (e.target as HTMLElement).dataset?.date; if (iso) setSel(iso); };

  const runsDesc = [...runs].sort((a, b) => b.start_date.localeCompare(a.start_date));
  const cfDesc = [...cf].sort((a, b) => b.date.localeCompare(a.date));

  // ── Pace chart: every run's pace across the year, with a scale ────────────
  const paces = runs.map((r) => ({ iso: r.start_date.slice(0, 10), s: r.moving_time_s / r.distance_miles, mi: r.distance_miles }));
  const pLo = Math.floor(Math.min(...paces.map((p) => p.s)) / 30) * 30;
  const pHi = Math.max(pLo + 90, Math.min(Math.ceil(Math.max(...paces.map((p) => p.s)) / 30) * 30, Math.ceil((avgPaceSec + 120) / 30) * 30));
  const slow = paces.filter((p) => p.s > pHi);
  const PW = 320, PH = 150, PL = 40, PB = 20;
  const xOf = (iso: string) => PL + (daysBetween(`${d.y}-01-01`, iso) / Math.max(1, daysBetween(`${d.y}-01-01`, today))) * (PW - PL - 8);
  const yOf = (s: number) => 6 + ((Math.min(s, pHi) - pLo) / Math.max(1, pHi - pLo)) * (PH - PB - 12);
  const ticks = Array.from({ length: Math.floor((pHi - pLo) / 30) + 1 }, (_, i) => pLo + i * 30).filter((t, i, a) => a.length <= 5 || i % 2 === 0 || t === pHi);

  return (
    <div className="ons-page" style={{ padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" }}>
      <PageHead
        title="Fitness"
        kicker={`${d.y} through ${fmt(today, { weekday: "short", month: "short", day: "numeric" })} · runs from Strava · CrossFit from SugarWOD${d.newestCf ? `, newest record ${short(d.newestCf)}` : ""}`}
        sub={lede}
        scene={<PixelScene scene="fitness" data={{ classes, miles: Math.round(d.miles), squat: backSquat?.best.best_result_raw ?? "" }}
          label={`a gym: the whiteboard shows ${classes} classes, a lifter squats ${backSquat ? `${backSquat.best.best_result_raw} lb` : "a loaded bar"}, a runner on a treadmill at ${Math.round(d.miles)} miles`} />}
      />

      <div className="ons-tiles" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))" }}>
        <section className="ons-tile t t-run">
          <h2>Running</h2>
          <div className="big n">{one(d.miles)} mi</div>
          <p>{milesGoal ? `of ${milesGoal} · ` : ""}{plural(runs.length, "run")} · {pace(avgPaceSec)} /mi average</p>
          {milesGoal && <div className="ons-bar" style={{ marginTop: "auto" }}><b style={{ width: `${Math.min(100, (d.miles / milesGoal) * 100)}%` }} /><i style={{ left: `${d.yearFrac * 100}%` }} /></div>}
        </section>
        <section className="ons-tile">
          <h2>Miles needed</h2>
          <div className="big n">{mp ? `${one(mp.perWeek)}/wk` : "–"}</div>
          <p>{milesGoal ? <>{Math.max(0, Math.round(milesGoal - d.miles))} mi to go in {plural(d.daysLeft, "day")}. Last 4 weeks: {one(d.miles28 / 4)}/wk.</> : "No mileage goal wired."}</p>
          {mp && <p className="tnote"><span className={`ons-badge ${mp.cls}`}>{mp.label}</span></p>}
        </section>
        <section className="ons-tile t t-lift">
          <h2>CrossFit classes</h2>
          <div className="big n">{classes}</div>
          <p>{classGoal ? `of ${classGoal} · ` : ""}{plural(d.classes28, "class", "classes")} in the last 4 weeks</p>
          {classGoal && <div className="ons-bar" style={{ marginTop: "auto" }}><b style={{ width: `${Math.min(100, (classes / classGoal) * 100)}%` }} /><i style={{ left: `${d.yearFrac * 100}%` }} /></div>}
        </section>
        <section className="ons-tile">
          <h2>Training days</h2>
          <div className="big n">{one(d.trainDays / Math.max(1, d.weeksGone))}/wk</div>
          <p>Days with a run or a class, {d.y} average. Last 4 weeks: {one(d.trainDays28 / 4)}/wk.</p>
          {cp && <p className="tnote"><span className={`ons-badge ${cp.cls}`}>CrossFit: {cp.label.toLowerCase()}</span></p>}
        </section>
      </div>

      <div className="ons-grid">
        <section className="ons-card s12" aria-labelledby="cal-h">
          <div className="ons-ch"><h2 id="cal-h">The year in training</h2><span className="aside">{plural(d.trainDays, "training day")} · {plural(runs.length, "run")} · {plural(classes, "class", "classes")} · tap a day</span></div>
          <div className="ons-calwrap ons-scroll" ref={(el) => { if (el && !el.dataset.scrolled) { el.scrollLeft = el.scrollWidth; el.dataset.scrolled = "1"; } }}>
            <div className="ons-cal" style={{ ["--wks" as string]: d.weeks.length }} onMouseOver={pick} onClick={pick}
                 role="img" aria-label={`${d.y} training calendar: ${plural(d.trainDays, "training day")}, ${plural(runs.length, "run")} and ${plural(classes, "CrossFit class", "CrossFit classes")}. Busiest week ${one(maxWeekMiles)} miles.`}>
              <span />
              {monthStarts.map((m, i) => <span key={i} className="mo">{m}</span>)}
              {["Mon", "", "Wed", "", "Fri", "", "Sun"].map((lab, r) => (
                <FragmentRow key={r} label={lab}>
                  {d.weeks.map((m) => {
                    const iso = addDays(m, r);
                    if (iso > today || iso < `${d.y}-01-01`) return <i key={iso} className="f" />;
                    const f = d.byDay.get(iso), run = !!f?.runs.length, lift = !!f?.cf.length;
                    const cls = [run && lift ? "b" : run ? "r" : lift ? "c" : "", iso === today && "now", iso === selDay && "sel"].filter(Boolean).join(" ");
                    return <i key={iso} className={cls} data-date={iso} />;
                  })}
                </FragmentRow>
              ))}
              <span className="lab">Miles</span>
              {d.weekMiles.map((v, i) => <span key={i} className="bar" title={`Week of ${short(d.weeks[i])}: ${one(v)} mi`}>{v > 0 && <b style={{ height: `${Math.max(6, (v / maxWeekMiles) * 100)}%` }} />}</span>)}
              <span className="lab">Classes</span>
              {d.weekClasses.map((v, i) => <span key={i} className="bar c" title={`Week of ${short(d.weeks[i])}: ${plural(v, "class", "classes")}`}>{v > 0 && <b style={{ height: `${Math.max(12, (v / maxWeekClasses) * 100)}%` }} />}</span>)}
            </div>
          </div>
          <div className="ons-caldetail" aria-live="polite">
            <b>{fmt(selDay, { weekday: "short", month: "short", day: "numeric" })}</b>
            {!selFacts || (!selFacts.runs.length && !selFacts.cf.length) ? <span className="text-muted">Rest day</span> : null}
            {selFacts?.runs.map((r) => <span key={r.strava_id} className="l-run ons-mk ons-n">Run {r.distance_miles.toFixed(2)} mi · {clock(r.moving_time_s)} · {pace(r.moving_time_s / r.distance_miles)} /mi</span>)}
            {selFacts?.cf.map((c, i) => { const [v, k] = score(c); return <span key={i} className="l-lift ons-mk">{c.title} · <span className="ons-n">{v}</span>{k ? ` ${k}` : ""}</span>; })}
          </div>
          <div className="ons-legend">
            <span><i style={{ background: "var(--run-mark)" }} />Run</span>
            <span><i style={{ background: "var(--lift-mark)" }} />CrossFit</span>
            <span><i style={{ background: "linear-gradient(135deg, var(--run-mark) 50%, var(--lift-mark) 50%)" }} />Both</span>
            <span><i style={{ background: "var(--rule)" }} />Rest</span>
            <span>Bars: weekly miles (busiest {one(maxWeekMiles)}) and classes (most {maxWeekClasses}).</span>
          </div>
        </section>

        <section className="ons-card s8" aria-labelledby="runs-h">
          <div className="ons-ch"><h2 id="runs-h">Runs</h2><span className="aside">{one(d.miles)} mi · {clock(d.totalSec)} moving · Strava</span></div>
          <div style={{ overflowX: "auto" }}>
            <table className="ons-table l-run">
              <thead><tr><th>Date</th><th className="r">Distance</th><th className="r">Time</th><th className="r">Pace</th><th className="hide-p" /></tr></thead>
              <tbody>
                {(allRuns ? runsDesc : runsDesc.slice(0, 10)).map((r) => (
                  <tr key={r.strava_id}>
                    <td style={{ whiteSpace: "nowrap" }}><span className="hide-p">{fmt(r.start_date, { weekday: "short" })}, </span>{short(r.start_date)}{r === d.longest && <> <span className="ons-side">Longest</span></>}</td>
                    <td className="r ons-n">{r.distance_miles.toFixed(2)} mi</td>
                    <td className="r ons-n">{clock(r.moving_time_s)}</td>
                    <td className="r ons-n">{pace(r.moving_time_s / r.distance_miles)} /mi</td>
                    <td className="r hide-p"><a className="ons-link" href={`https://www.strava.com/activities/${r.strava_id}`} target="_blank" rel="noreferrer">Strava</a></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {runsDesc.length > 10 && <button type="button" className="ons-tap ons-btn" style={{ marginTop: 12 }} onClick={() => setAllRuns((v) => !v)}>{allRuns ? "Show the latest 10" : `Show all ${runsDesc.length} runs`}</button>}
          {d.longest && d.longest.distance_miles >= 26.2 && marathon && !marathon.current_value && (
            <p className="ons-note">Your {short(d.longest.start_date)} run was {d.longest.distance_miles.toFixed(1)} mi, longer than a marathon. The marathon goal is a manual entry in goals/{d.y}.yaml and still reads not done.</p>
          )}
        </section>

        <div className="s4 ons-col no-stretch">
          {checkin !== "private" && (
            <section className="ons-card t t-check" aria-labelledby="ready-h">
              <div className="ons-ch"><h2 id="ready-h">Today&apos;s call</h2><span className="aside">From the check-in</span></div>
              {ready && checkin ? (
                <p className="m-0" style={{ fontSize: 14, lineHeight: "20px" }}><b>{ready[1]}</b> · readiness <span className="ons-n">{Math.round(checkin.readiness * 100)}</span>. {ready[2][0].toUpperCase() + ready[2].slice(1)}.</p>
              ) : (
                <p className="m-0" style={{ fontSize: 14, lineHeight: "20px" }}>No check-in yet today. <a href="/checkin" className="ons-link" style={{ color: "inherit" }}>Check in</a> to get a training call.</p>
              )}
            </section>
          )}
          <section className="ons-card" aria-labelledby="pace-h">
            <div className="ons-ch"><h2 id="pace-h">Pace by run</h2><span className="aside">min per mile · faster is higher</span></div>
            <svg viewBox={`0 0 ${PW} ${PH}`} width="100%" role="img" aria-label={`Pace for each of ${runs.length} runs this year, from ${pace(pLo)} to ${pace(pHi)} per mile; average ${pace(avgPaceSec)}.`} style={{ display: "block", overflow: "visible" }}>
              {ticks.map((t) => (
                <g key={t}>
                  <line x1={PL} x2={PW - 4} y1={yOf(t)} y2={yOf(t)} stroke="var(--rule)" />
                  <text x={PL - 6} y={yOf(t) + 4} textAnchor="end" fontSize="12" fill="var(--muted)" fontFamily="IBM Plex Mono, monospace">{pace(t)}</text>
                </g>
              ))}
              <line x1={PL} x2={PW - 4} y1={yOf(avgPaceSec)} y2={yOf(avgPaceSec)} stroke="var(--run-ink)" strokeDasharray="3 3" />
              {paces.map((p, i) => <circle key={i} cx={xOf(p.iso)} cy={yOf(p.s)} r={p.mi >= 10 ? 4.5 : 3} fill={p.s > pHi ? "var(--sheet)" : "var(--run-mark)"} stroke={p.s > pHi ? "var(--run-mark)" : "var(--sheet)"} strokeWidth={p.s > pHi ? 1.5 : 1}><title>{`${short(p.iso)}: ${p.mi.toFixed(2)} mi at ${pace(p.s)} /mi`}</title></circle>)}
              {["01", "04", "07", "10"].map((m) => { const iso = `${d.y}-${m}-01`; return iso <= today ? <text key={m} x={xOf(iso)} y={PH - 4} fontSize="12" fill="var(--muted)">{fmt(iso, { month: "short" })}</text> : null; })}
            </svg>
            <p className="ons-note">Dashed line: the {d.y} average, {pace(avgPaceSec)} /mi. Larger dots are runs of 10 miles or more.{slow.length > 0 && <> {slow.length === 1 ? "One run" : `${slow.length} runs`} slower than {pace(pHi)} ({slow.map((p) => `${short(p.iso)}, ${pace(p.s)}`).join("; ")}) {slow.length === 1 ? "sits" : "sit"} on the bottom edge as {slow.length === 1 ? "an open dot" : "open dots"}.</>}</p>
          </section>
        </div>

        <section className="ons-card s8" aria-labelledby="cf-h">
          <div className="ons-ch"><h2 id="cf-h">CrossFit sessions</h2><span className="aside">{plural(cf.length, "score")} on {plural(classes, "day")} · SugarWOD</span></div>
          <div style={{ overflowX: "auto" }}>
            <table className="ons-table l-lift">
              <thead><tr><th>Date</th><th>Workout</th><th className="r">Score</th><th className="r hide-p">Level</th></tr></thead>
              <tbody>
                {(allCf ? cfDesc : cfDesc.slice(0, 12)).map((c, i) => {
                  const [v, k] = score(c);
                  return (
                    <tr key={i}>
                      <td style={{ whiteSpace: "nowrap" }}><span className="hide-p">{fmt(c.date, { weekday: "short" })}, </span>{short(c.date)}</td>
                      <td>{c.title}{c.is_pr && <> <span className="ons-badge ok">PR</span></>}</td>
                      <td className="r" style={{ whiteSpace: "nowrap" }}><span className="ons-n">{v}</span>{k && <span className="text-muted" style={{ fontSize: 13 }}> {k}</span>}</td>
                      <td className="r hide-p">{c.rx_or_scaled ? <span className={`ons-badge ${c.rx_or_scaled === "RX" ? "none" : "risk"}`}>{c.rx_or_scaled === "RX" ? "Rx" : "Scaled"}</span> : null}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {cfDesc.length > 12 && <button type="button" className="ons-tap ons-btn" style={{ marginTop: 12 }} onClick={() => setAllCf((v) => !v)}>{allCf ? "Show the latest 12" : `Show all ${cfDesc.length} scores`}</button>}
        </section>

        <section className="ons-card s4" aria-labelledby="lift-h">
          <div className="ons-ch"><h2 id="lift-h">Lifts</h2><span className="aside">Heaviest logged set</span></div>
          {d.lifts.length ? (
            <table className="ons-table l-lift">
              <thead><tr><th>Lift</th><th className="r">Heaviest</th><th className="r">Sessions</th></tr></thead>
              <tbody>
                {(allLifts ? d.lifts : d.lifts.slice(0, 8)).map((l) => (
                  <tr key={l.lift}>
                    <td>{l.lift}<span className="sub">{short(l.best.date)}{l.latest.date !== l.best.date ? ` · last ${short(l.latest.date)}` : ""}</span></td>
                    <td className="r ons-n">{l.best.best_result_raw} lb</td>
                    <td className="r ons-n">{l.n}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <p className="ons-note m-0">No barbell lifts with a load score in SugarWOD this year.</p>}
          {d.lifts.length > 8 && <button type="button" className="ons-tap ons-btn" style={{ marginTop: 12 }} onClick={() => setAllLifts((v) => !v)}>{allLifts ? "Show the latest 8" : `Show all ${d.lifts.length} lifts`}</button>}
          <p className="ons-note">The heaviest working set logged in SugarWOD, not a tested one-rep max.{squatGoal ? <> The {squatGoal} lb squat goal isn&apos;t wired to SugarWOD{backSquat ? `; the heaviest back squat logged is ${backSquat.best.best_result_raw} lb (${short(backSquat.best.date)})` : ""}.</> : null}</p>
        </section>
      </div>
    </div>
  );
}

function FragmentRow({ label, children }: { label: string; children: React.ReactNode }) {
  return <><span className="lab">{label}</span>{children}</>;
}
