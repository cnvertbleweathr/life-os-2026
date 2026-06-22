"use client";

import { useEffect, useState } from "react";
import { fitnessApi, type FitnessSummary, type CrossfitEntry } from "@/lib/api";
import {
  Card, PageHead, K, Empty, Loading, ErrorState,
} from "@/components/ui/primitives";
import { OnsIcon } from "@/components/ui/icons";
import { Sparkline } from "@/components/ui/viz";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

interface DayActivity {
  date: string; // YYYY-MM-DD
  ran: boolean;
  crossfit: boolean;
  runMiles: number;
  cfTitle: string | null;
}

// Training heatmap — real per-day data, grouped into month columns, with hover tooltip
function TrainingHeatmap({ days }: { days: Map<string, DayActivity> }) {
  const [hover, setHover] = useState<{ d: DayActivity; x: number; y: number } | null>(null);

  // Build the last ~26 weeks as a calendar grid, oldest first, grouped by month
  const today = new Date();
  const start = new Date(today);
  start.setDate(start.getDate() - 26 * 7);
  // Align to the previous Sunday so weeks are clean columns
  start.setDate(start.getDate() - start.getDay());

  const weeks: Date[][] = [];
  let cursor = new Date(start);
  while (cursor <= today) {
    const week: Date[] = [];
    for (let d = 0; d < 7; d++) {
      week.push(new Date(cursor));
      cursor.setDate(cursor.getDate() + 1);
    }
    weeks.push(week);
  }

  const gap = 2.5;
  const cols = weeks.length;
  const rows = 7;

  // Month label positions — first week column where a new month starts
  const monthLabels: { col: number; label: string }[] = [];
  let lastMonth = -1;
  weeks.forEach((week, c) => {
    const m = week[3].getMonth(); // mid-week, avoids edge flicker
    if (m !== lastMonth) {
      monthLabels.push({ col: c, label: MONTHS[m] });
      lastMonth = m;
    }
  });

  const RUN_RGB = "29,85,54";
  const CF_RGB = "154,106,30";

  const fill = (a: DayActivity | undefined) => {
    if (!a) return "#efebe1";
    if (a.ran && a.crossfit) return "#1d5536";
    if (a.ran) return `rgba(${RUN_RGB},${Math.min(1, 0.4 + a.runMiles / 10).toFixed(2)})`;
    if (a.crossfit) return `rgba(${CF_RGB},0.78)`;
    return "#efebe1";
  };

  return (
    <div style={{ position: "relative", maxWidth: 640 }}>
      <div
        className="grid font-mono text-faint mb-1"
        style={{ fontSize: 8, gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 0 }}
      >
        {weeks.map((week, c) => {
          const m = monthLabels.find((ml) => ml.col === c);
          return <span key={c}>{m ? m.label : ""}</span>;
        })}
      </div>
      <div
        className="grid"
        style={{ gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: `${gap}px`, marginTop: 6 }}
      >
        {weeks.map((week, c) => (
          <div key={c} className="grid" style={{ gridTemplateRows: `repeat(${rows}, 1fr)`, gap: `${gap}px` }}>
            {week.map((day, r) => {
              if (day > today) {
                return <div key={r} style={{ aspectRatio: "1" }} />;
              }
              const key = day.toISOString().slice(0, 10);
              const a = days.get(key);
              const both = a?.ran && a?.crossfit;
              return (
                <div
                  key={r}
                  onMouseEnter={(e) => {
                    const rect = e.currentTarget.getBoundingClientRect();
                    setHover({ d: a ?? { date: key, ran: false, crossfit: false, runMiles: 0, cfTitle: null }, x: rect.x, y: rect.y });
                  }}
                  onMouseLeave={() => setHover(null)}
                  style={{
                    aspectRatio: "1",
                    borderRadius: 2,
                    background: fill(a),
                    border: both ? "1.2px solid #9a6a1e" : "none",
                    boxSizing: "border-box",
                  }}
                />
              );
            })}
          </div>
        ))}
      </div>
      {hover && (
        <div
          className="font-mono fixed z-10 pointer-events-none"
          style={{
            left: hover.x, top: hover.y - 46, fontSize: 9.5,
            background: "#232a22", color: "#fbfaf5", padding: "5px 8px",
            borderRadius: 4, whiteSpace: "nowrap",
          }}
        >
          {new Date(hover.d.date + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" })}
          {!hover.d.ran && !hover.d.crossfit && " — rest"}
          {hover.d.ran && ` — ${hover.d.runMiles.toFixed(1)}mi run`}
          {hover.d.crossfit && ` — ${hover.d.cfTitle ?? "CrossFit"}`}
        </div>
      )}
      <div className="flex items-center gap-4 mt-3 font-mono text-muted" style={{ fontSize: 9 }}>
        <span className="flex items-center gap-[5px]">
          <span className="rounded-sm" style={{ width: 9, height: 9, background: `rgba(${RUN_RGB},0.8)` }} /> RUN
        </span>
        <span className="flex items-center gap-[5px]">
          <span className="rounded-sm" style={{ width: 9, height: 9, background: `rgba(${CF_RGB},0.8)` }} /> CROSSFIT
        </span>
        <span className="flex items-center gap-[5px]">
          <span className="rounded-sm" style={{ width: 9, height: 9, background: "#1d5536", border: "1.5px solid #9a6a1e", boxSizing: "border-box" }} /> BOTH
        </span>
      </div>
    </div>
  );
}

// Mini bar chart for weekly volume
function MiniVol({ data, color, h = 70, labels }: { data: number[]; color: string; h?: number; labels?: string[] }) {
  const max = Math.max(...data, 1);
  return (
    <div>
      <div className="flex items-end gap-[5px]" style={{ height: h }}>
        {data.map((v, i) => (
          <div key={i} className="flex-1 flex flex-col justify-end" style={{ height: "100%" }}>
            <div
              className="rounded-sm"
              style={{
                height: v > 0 ? `${Math.max(2, (v / max) * (h - 4))}px` : 0,
                background: v === 0 ? "#e6e3dc" : color,
              }}
              title={`${v}`}
            />
          </div>
        ))}
      </div>
      {labels && (
        <div className="flex justify-between mt-1.5 font-mono text-faint" style={{ fontSize: 8 }}>
          {labels.map((l, i) => <span key={i}>{l}</span>)}
        </div>
      )}
    </div>
  );
}

function MiniStat({ v, u, l, color }: { v: string | number; u: string; l: string; color?: string }) {
  return (
    <div>
      <div className="font-serif font-bold leading-none" style={{ fontSize: 24, color: color ?? "#232a22" }}>
        {v}<span className="font-mono font-normal ml-0.5 text-faint" style={{ fontSize: 10 }}>{u}</span>
      </div>
      <div className="font-mono text-faint mt-[5px]" style={{ fontSize: 8.5, letterSpacing: "0.5px" }}>{l}</div>
    </div>
  );
}

export default function FitnessPage() {
  const [data, setData] = useState<FitnessSummary | null>(null);
  const [crossfit, setCrossfit] = useState<CrossfitEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([fitnessApi.summary(), fitnessApi.crossfit(200)])
      .then(([f, cf]) => { setData(f); setCrossfit(cf); })
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!data || !crossfit) return <Loading />;

  const { running_summary: rs, recent_runs, weekly_miles } = data;
  const weeklyRunData = weekly_miles.map((w) => w.miles);
  const paceSeries = [...recent_runs].reverse().map((r) => 12 - r.pace);

  // ── Build the real per-day activity map for the heatmap ──
  const days = new Map<string, DayActivity>();
  for (const r of recent_runs) {
    const key = r.run_date.slice(0, 10);
    days.set(key, { date: key, ran: true, crossfit: false, runMiles: r.miles, cfTitle: null });
  }
  for (const c of crossfit) {
    const key = c.date;
    const existing = days.get(key);
    if (existing) {
      existing.crossfit = true;
      existing.cfTitle = c.title;
    } else {
      days.set(key, { date: key, ran: false, crossfit: true, runMiles: 0, cfTitle: c.title });
    }
  }

  // ── Derive CrossFit stats from the real log ──
  const now = new Date();
  const weekAgo = new Date(now);
  weekAgo.setDate(weekAgo.getDate() - 7);
  const classDates = new Set(crossfit.map((c) => c.date));
  const classesYtd = classDates.size;
  const classesThisWeek = [...classDates].filter((d) => new Date(d) >= weekAgo).length;

  // Weekly class counts, last 12 weeks
  const cfWeekly: number[] = [];
  const cfWeekLabels: string[] = [];
  for (let i = 11; i >= 0; i--) {
    const wkStart = new Date(now);
    wkStart.setDate(wkStart.getDate() - i * 7 - now.getDay());
    const wkEnd = new Date(wkStart);
    wkEnd.setDate(wkEnd.getDate() + 7);
    const count = [...classDates].filter((d) => {
      const dt = new Date(d);
      return dt >= wkStart && dt < wkEnd;
    }).length;
    cfWeekly.push(count);
    if (i % 3 === 0) cfWeekLabels.push(MONTHS[wkStart.getMonth()]);
  }

  // Lifts: group entries with a barbell_lift + numeric result, take history per lift
  const liftHistory = new Map<string, CrossfitEntry[]>();
  for (const c of crossfit) {
    if (c.barbell_lift && c.barbell_lift.trim() && c.best_result_raw != null) {
      const list = liftHistory.get(c.barbell_lift) ?? [];
      list.push(c);
      liftHistory.set(c.barbell_lift, list);
    }
  }
  // "Current" max = most recent dated entry per lift; show up to 4 lifts by recency
  const currentMaxes = [...liftHistory.entries()]
    .map(([lift, entries]) => {
      const sorted = entries.sort((a, b) => a.date.localeCompare(b.date));
      const latest = sorted[sorted.length - 1];
      return { lift, latest, history: sorted };
    })
    .sort((a, b) => b.latest.date.localeCompare(a.latest.date))
    .slice(0, 4);

  const recentWods = crossfit.slice(0, 8);

  // Avg workout days per week, across all of 2026.
  //
  // Honest constraint: /fitness/summary's recent_runs is capped server-side
  // to the last 30 days (max 10 rows) — not enough to know which specific
  // days you ran across the full year. weekly_miles IS a full-year query
  // and tells us which weeks had >0 running miles. CrossFit dates ARE
  // full-year (capped at limit=200, well above real attendance).
  //
  // So: count a week as a "workout week" if it had running miles > 0
  // OR at least one CrossFit class that week, then average days/week
  // using CrossFit's actual day-level density for the CrossFit side and
  // 1 day/week credit for any running-only week (a real day count for
  // running weeks isn't available without a backend change).
  const yearStart = new Date(now.getFullYear(), 0, 1);
  const daysElapsed = Math.floor((now.getTime() - yearStart.getTime()) / 86400000) + 1;
  const weeksElapsed = Math.max(1, daysElapsed / 7);

  // CrossFit: exact day count, full year
  const cfDaysThisYear = [...classDates].filter(
    (d) => new Date(d + "T00:00:00").getFullYear() === now.getFullYear()
  ).length;

  // Running: weekly_miles gives complete week-level coverage but not
  // day-level — credit 1 day for each week with running miles > 0
  const runWeeksThisYear = weekly_miles.filter((w) => w.miles > 0).length;

  const avgWorkoutDaysPerWeek = (cfDaysThisYear + runWeeksThisYear) / weeksElapsed;

  return (
    <div className="ons-page ons-scroll" style={{ padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" }}>
      <PageHead
        title="Fitness"
        kicker="Running + CrossFit · Strava + SugarWOD"
        right={
          <div className="font-mono text-right text-faint" style={{ fontSize: 9.5 }}>
            YTD 2026 · DENVER<br />{rs.total_runs} RUNS · {classesYtd} CLASSES
          </div>
        }
      />

      {/* Training consistency heatmap — smaller, month-grouped, hoverable */}
      <Card style={{ marginBottom: 26, padding: "16px 20px" }}>
        <div className="flex justify-between items-center mb-1">
          <K>Training Consistency</K>
          <div className="flex items-center gap-4">
            <span className="font-mono" style={{ fontSize: 11 }}>
              <span className="font-serif font-bold" style={{ fontSize: 15, color: "#1d5536" }}>
                {avgWorkoutDaysPerWeek.toFixed(1)}
              </span>
              <span className="text-faint"> / 7 days · avg this year</span>
            </span>
            <span className="font-mono text-faint" style={{ fontSize: 9 }}>HOVER A DAY FOR DETAIL</span>
          </div>
        </div>
        <div className="font-mono text-faint mb-3" style={{ fontSize: 8.5 }}>
          CrossFit counted by exact day · running weeks counted as 1 day (day-level running data beyond 30 days isn't in the API yet)
        </div>
        <TrainingHeatmap days={days} />
      </Card>

      {/* Split: Running (left) / CrossFit (right) */}
      <div className="grid gap-[30px] items-start" style={{ gridTemplateColumns: "1fr 1fr" }}>
        {/* Running */}
        <div>
          <div className="flex justify-between items-center mb-4" style={{ borderTop: "2.5px solid #1d5536", paddingTop: 12 }}>
            <div className="flex items-center gap-[9px]">
              <span className="text-green"><OnsIcon name="fitness" size={18} stroke={1.8} /></span>
              <div>
                <div className="font-serif font-bold text-ink leading-none" style={{ fontSize: 19 }}>Running</div>
                <div className="font-mono text-faint mt-[3px]" style={{ fontSize: 8.5, letterSpacing: "1px" }}>STRAVA</div>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3 mb-5">
            <MiniStat v={rs.ytd_miles} u="mi" l="YTD MILES" color="#1d5536" />
            <MiniStat v={rs.avg_pace_min_mile} u="/mi" l="AVG PACE" />
            <MiniStat v={rs.total_runs} u="" l="TOTAL RUNS" />
          </div>

          <Card style={{ marginBottom: 22 }}>
            <K style={{ marginBottom: 14 }}>Pace Trend · last {recent_runs.length} runs</K>
            {paceSeries.length > 1 ? (
              <div className="text-green">
                <Sparkline data={paceSeries} w={420} h={82} stroke="#1d5536" sw={2.2} fill="#1d5536" dot />
              </div>
            ) : (
              <Empty message="Need more runs for a trend line." />
            )}
          </Card>

          <Card style={{ marginBottom: 22 }}>
            <K style={{ marginBottom: 14 }}>Weekly Volume · {weeklyRunData.length} wk</K>
            <MiniVol data={weeklyRunData} color="#1d5536" />
          </Card>

          <Card pad={0}>
            <div style={{ padding: "16px 18px 8px" }}><K>Recent Runs</K></div>
            <div style={{ padding: "0 18px 12px" }}>
              {recent_runs.length === 0 ? (
                <Empty message="No recent runs." />
              ) : (
                recent_runs.map((r, i) => (
                  <div key={i} className="ons-row flex items-center gap-3 border-t border-border-2" style={{ padding: "10px 6px", margin: "0 -6px" }}>
                    <span className="grid place-items-center shrink-0 text-green" style={{ width: 26, height: 26, borderRadius: 6, background: "#e9efe7" }}>
                      <OnsIcon name="fitness" size={15} stroke={1.7} />
                    </span>
                    <div className="flex-1">
                      <div style={{ fontSize: 13.5 }}>{r.miles.toFixed(2)} mi</div>
                      <div className="font-mono text-faint mt-px" style={{ fontSize: 10.5 }}>
                        {r.minutes.toFixed(0)} min · {r.pace.toFixed(1)}/mi
                      </div>
                    </div>
                    <span className="font-mono text-muted" style={{ fontSize: 10 }}>
                      {r.run_date.slice(5, 10)}
                    </span>
                  </div>
                ))
              )}
            </div>
          </Card>
        </div>

        {/* CrossFit */}
        <div>
          <div className="flex justify-between items-center mb-4" style={{ borderTop: "2.5px solid #9a6a1e", paddingTop: 12 }}>
            <div className="flex items-center gap-[9px]">
              <span style={{ color: "#9a6a1e" }}><OnsIcon name="habits" size={18} stroke={1.8} /></span>
              <div>
                <div className="font-serif font-bold text-ink leading-none" style={{ fontSize: 19 }}>CrossFit</div>
                <div className="font-mono text-faint mt-[3px]" style={{ fontSize: 8.5, letterSpacing: "1px" }}>SUGARWOD</div>
              </div>
            </div>
            <span className="font-mono text-faint" style={{ fontSize: 9 }}>{classesYtd} CLASSES YTD</span>
          </div>

          <div className="grid grid-cols-3 gap-3 mb-5">
            <MiniStat v={classesYtd} u="" l="CLASSES YTD" color="#9a6a1e" />
            <MiniStat v={classesThisWeek} u="" l="THIS WEEK" />
            <MiniStat v={currentMaxes.length} u="" l="LIFTS TRACKED" />
          </div>

          <Card accent accentColor="#9a6a1e" style={{ marginBottom: 22 }}>
            <div className="flex justify-between items-center mb-4">
              <K color="#9a6a1e">Current Maxes</K>
              <span className="font-mono text-faint" style={{ fontSize: 9 }}>MOST RECENT LOGGED</span>
            </div>
            {currentMaxes.length === 0 ? (
              <Empty message="No lift entries with a barbell_lift + numeric result found in your SugarWOD log." />
            ) : (
              <div className="grid grid-cols-2">
                {currentMaxes.map((m, i) => {
                  const vals = m.history.map((h) => h.best_result_raw as number);
                  const gain = vals[vals.length - 1] - vals[0];
                  return (
                    <div
                      key={m.lift}
                      style={{
                        padding: "14px 14px 14px 0",
                        borderRight: i % 2 === 0 ? "1px solid #ebe5d8" : "none",
                        borderTop: i > 1 ? "1px solid #ebe5d8" : "none",
                        paddingLeft: i % 2 === 1 ? 16 : 0,
                      }}
                    >
                      <div className="font-mono uppercase text-muted" style={{ fontSize: 9, letterSpacing: "0.8px" }}>
                        {m.lift}
                      </div>
                      <div className="flex items-baseline gap-1 mt-1.5">
                        <span className="font-serif font-bold leading-none" style={{ fontSize: 26, color: "#9a6a1e" }}>
                          {m.latest.best_result_raw}
                        </span>
                        <span className="font-mono text-faint" style={{ fontSize: 9 }}>
                          {m.latest.best_result_unit ?? "lb"}
                        </span>
                      </div>
                      {vals.length > 1 && (
                        <div className="my-2" style={{ color: "#9a6a1e" }}>
                          <Sparkline data={vals} w={120} h={22} stroke="#9a6a1e" sw={1.6} fill="#9a6a1e" dot />
                        </div>
                      )}
                      <div className="font-mono" style={{ fontSize: 8.5, color: gain > 0 ? "#1d5536" : "#a39d8c" }}>
                        {vals.length > 1 ? `${gain >= 0 ? "+" : ""}${gain.toFixed(0)} ${m.latest.best_result_unit ?? "lb"} since first log` : "single entry"}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>

          <Card style={{ marginBottom: 22 }}>
            <K style={{ marginBottom: 14 }}>Weekly Classes · 12 wk</K>
            <MiniVol data={cfWeekly} color="#9a6a1e" labels={cfWeekLabels} />
          </Card>

          <Card pad={0}>
            <div style={{ padding: "16px 18px 8px" }}><K>Recent WODs</K></div>
            <div style={{ padding: "0 18px 12px" }}>
              {recentWods.length === 0 ? (
                <Empty message="No recent CrossFit entries." />
              ) : (
                recentWods.map((c, i) => (
                  <div key={i} className="ons-row flex items-center gap-3 border-t border-border-2" style={{ padding: "10px 6px", margin: "0 -6px" }}>
                    <span
                      className="grid place-items-center shrink-0"
                      style={{ width: 26, height: 26, borderRadius: 6, background: c.is_pr ? "#f3ead6" : "#f3ead6", color: "#9a6a1e" }}
                    >
                      <OnsIcon name="habits" size={15} stroke={1.7} />
                    </span>
                    <div className="flex-1">
                      <div style={{ fontSize: 13.5 }}>
                        {c.title}
                        {c.is_pr && <span className="text-green ml-1.5" style={{ fontSize: 11 }}>★ PR</span>}
                      </div>
                      <div className="font-mono text-faint mt-px" style={{ fontSize: 10.5 }}>
                        {c.barbell_lift ? `${c.barbell_lift} · ` : ""}
                        {c.best_result_raw != null ? `${c.best_result_raw} ${c.best_result_unit ?? ""}`.trim() : "—"}
                      </div>
                    </div>
                    <span className="font-mono text-muted" style={{ fontSize: 10 }}>
                      {c.date.slice(5)}
                    </span>
                  </div>
                ))
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
