"use client";

// Goals (Logbook Color). Every goal from goals/2026.yaml via /goals/progress, grouped by domain.
// Pace is computed only for goals with a live number (current_value + target); goals with no data
// source say "Not wired", never "behind" (critique problem 1).

import { useEffect, useState } from "react";
import { goalsApi, type Goal } from "@/lib/api";
import { PageHead, Loading, ErrorState } from "@/components/ui/primitives";

const DOMAIN: Record<string, [string, string]> = {
  fitness: ["l-run", "Fitness"], personal: ["l-read", "Personal"], family: ["l-plan", "Family"],
  finance: ["l-wx", "Finance"], professional: ["l-check", "Professional"],
};
const DAY = 86_400_000;
const LABELS: Record<string, string> = {
  date_night_per_week: "Date night every week", hsa: "HSA", monthly_savings_usd: "Save $2,000 a month", roth_ira: "Roth IRA",
  bodyweight_lbs_max: "Bodyweight under 190 lb", crossfit_classes: "160 CrossFit classes", marathon_completed: "Run a marathon",
  running_miles: "Run 350 miles", squat_max_lbs: "Squat 350 lb", fiction_books_goal: "Read 5 fiction", fiction_pages_10: "10 fiction pages a day",
  meditation: "Meditate every day", nonfiction_pages_10: "10 nonfiction pages a day", pushups_100: "100 pushups a day",
  spotify_minutes_goal: "50,000 Spotify minutes", github_commits: "100 GitHub commits", migrations_completed: "100 migrations",
  nonfiction_books_goal: "Read 5 nonfiction", promotion: "Promotion", ps_revenue_usd: "PS revenue $1M",
};
const labelOf = (g: Goal) => LABELS[g.goal_key] ?? g.label;

function yearClock() {
  const now = new Date(), y = now.getFullYear();
  const start = new Date(y, 0, 1).getTime(), end = new Date(y + 1, 0, 1).getTime();
  const frac = (now.getTime() - start) / (end - start);
  return { y, frac, daysLeft: Math.ceil((end - now.getTime()) / DAY), weeksLeft: (end - now.getTime()) / DAY / 7, weeksGone: (now.getTime() - start) / DAY / 7 };
}

type State = { cls: "ok" | "risk" | "off" | "none"; label: string; needs: string };
function pace(g: Goal, c: ReturnType<typeof yearClock>): State {
  if (g.current_value == null || g.target_numeric == null) return { cls: "none", label: "Not wired", needs: "–" };
  const target = g.target_numeric, cur = g.current_value, left = Math.max(0, target - cur);
  if (left === 0) return { cls: "ok", label: "Done", needs: "–" };
  if (target === 1) return { cls: "risk", label: "Not yet", needs: "1 to go" };
  const perWeek = left / Math.max(c.weeksLeft, 0.1), avg = cur / Math.max(c.weeksGone, 0.1), expected = target * c.frac;
  // Daily goals (one per day of the year): compare days needed with days left.
  if (target >= 365) return left > c.daysLeft
    ? { cls: "off", label: "Out of reach", needs: `${Math.round(left)} d, ${c.daysLeft} left` }
    : { cls: cur >= expected ? "ok" : "risk", label: cur >= expected ? "On track" : "Behind", needs: `${Math.round(left)} of ${c.daysLeft} d` };
  const needs = perWeek >= 1 ? `${perWeek >= 10 ? Math.round(perWeek) : perWeek.toFixed(1)}/wk` : `1 per ${Math.round(7 / perWeek)} d`;
  if (cur >= expected) return { cls: "ok", label: "On track", needs };
  if (avg > 0 ? perWeek > avg * 3 : left > target * 0.5) return { cls: "off", label: "Out of reach", needs };
  return { cls: "risk", label: "Behind", needs };
}
const num = (x: number) => (Math.abs(x) >= 1000 ? x.toLocaleString("en-US", { maximumFractionDigits: 0 }) : String(+x.toFixed(2)));
const source = (d?: string | null) => (d?.startsWith("auto:") ? d.slice(5).trim().replace(/^./, (m) => m.toUpperCase()) : "Manual");

export default function GoalsPage() {
  const [goals, setGoals] = useState<Goal[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [clock, setClock] = useState<ReturnType<typeof yearClock> | null>(null);

  useEffect(() => {
    setClock(yearClock()); // client-only, so server and client render the same markup
    goalsApi.progress().then(setGoals).catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="ons-page" style={{ padding: "34px 44px 48px" }}><ErrorState message={error} /></div>;
  if (!goals || !clock) return <Loading label="Loading goals…" />;

  const states = goals.map((g) => [g, pace(g, clock)] as const);
  const wired = states.filter(([, s]) => s.cls !== "none");
  const count = (cls: State["cls"]) => wired.filter(([, s]) => s.cls === cls).length;
  const domains = Array.from(new Set(goals.map((g) => g.domain)));
  const worst = wired.filter(([, s]) => s.cls === "off").map(([g]) => labelOf(g));
  const good = wired.filter(([, s]) => s.cls === "ok").map(([g]) => labelOf(g));

  return (
    <div className="ons-page" style={{ padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" }}>
      <PageHead
        title="Goals"
        kicker={`${clock.y} · ${goals.length} goals · ${clock.daysLeft} days left · ${Math.round(clock.frac * 100)}% of the year gone`}
        sub={
          <>
            <b>{wired.length} of {goals.length} goals have live data:</b> {count("ok")} on track, {count("risk")} behind, {count("off")} out of reach.
            {good.length > 0 && <> On track: {good.join(", ")}.</>}
            {worst.length > 0 && <> Out of reach at this year&apos;s rate: {worst.join(", ")}.</>}
            {goals.length - wired.length > 0 && <> The other {goals.length - wired.length} have no data source wired yet.</>}
          </>
        }
      />

      <div className="ons-tiles" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))" }}>
        {([["ok", "On track"], ["risk", "Behind"], ["off", "Out of reach"], ["none", "Not wired"]] as const).map(([cls, label]) => (
          <section key={cls} className="ons-tile"><h2>{label}</h2><div className="big">{cls === "none" ? goals.length - wired.length : count(cls)}</div><p><span className={`ons-badge ${cls}`}>{label}</span></p></section>
        ))}
      </div>

      <div className="ons-col">
        {domains.map((d) => {
          const [cls, name] = DOMAIN[d] ?? ["l-plan", d];
          const rows = states.filter(([g]) => g.domain === d).sort((a, b) => Number(b[1].cls !== "none") - Number(a[1].cls !== "none"));
          return (
            <section key={d} className="ons-card" aria-labelledby={`d-${d}`}>
              <div className="ons-ch"><h2 id={`d-${d}`}>{name}</h2><span className="aside">{rows.filter(([, s]) => s.cls !== "none").length} of {rows.length} with live data</span></div>
              <div style={{ overflowX: "auto" }}>
                <table className="ons-table">
                  <thead><tr><th>Goal</th><th className="hide-p">Progress · line is today</th><th className="r">Now</th><th className="r">Needs</th><th className="r">State</th><th className="hide-p">Source</th></tr></thead>
                  <tbody>
                    {rows.map(([g, s]) => {
                      const live = s.cls !== "none";
                      const pct = live && g.target_numeric ? Math.min(100, (g.current_value! / g.target_numeric) * 100) : 0;
                      return (
                        <tr key={g.goal_key} className={cls}>
                          <td><div className="ons-goal"><i style={live ? undefined : { background: "var(--control)" }} /><div>{labelOf(g)}</div></div></td>
                          <td className="hide-p">{live ? <div className="ons-bar"><b style={{ width: `${pct}%` }} /><i style={{ left: `${clock.frac * 100}%` }} /></div> : <span className="text-muted">–</span>}</td>
                          <td className="r ons-n">{live ? `${num(g.current_value!)} of ${num(g.target_numeric!)}` : g.target_numeric != null ? `– of ${num(g.target_numeric)}` : "–"}</td>
                          <td className="r ons-n">{s.needs}</td>
                          <td className="r"><span className={`ons-badge ${s.cls}`}>{s.label}</span></td>
                          <td className="hide-p text-muted" style={{ fontSize: 13 }}>{source(g.description)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          );
        })}
      </div>
      <p className="ons-note">&ldquo;Out of reach&rdquo; means the rate needed is more than three times this year&apos;s average. Goals marked Manual have no pipeline yet; they stay &ldquo;Not wired&rdquo; until one feeds them. Targets come from goals/{clock.y}.yaml.</p>
    </div>
  );
}
