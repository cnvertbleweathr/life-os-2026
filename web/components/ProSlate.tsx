"use client";

// ── Degenerates Corner — NBA / NHL (Logbook Color) ──────────────────────────
// Real data only: /nba-nhl/{league}/slate (one day's logged games, graded in place) and
// /nba-nhl/{league}/record (season to date). Both read data/bets/{league}/history/<date>.json,
// written by scripts/nba_nhl_generate_picks.py at the morning sync.
// No rule has passed validation (docs/NBA_NHL_ATS_DATA.md → Edge validation), so every game is
// NO_BET. NBA games also carry the nba_totals_open_v1 paper test, shown as a paper entry, never a bet.
// Times are shown in Denver time, like the CFB slate.

import { useEffect, useState } from "react";
import { proApi, type ProGame, type ProLeague, type ProRecord, type ProSlate } from "@/lib/api";
import { PageHead, Empty, Loading, ErrorState } from "@/components/ui/primitives";
import { ProTeamLogo } from "@/components/ui/ProTeamLogo";
import { PixelScene } from "@/components/ui/PixelScene";
import teams from "@/lib/nba_nhl_teams.json";

const TZ = "America/Denver";
const NAME: Record<ProLeague, string> = { nba: "NBA", nhl: "NHL" };
const TEAMS = teams as Record<ProLeague, Record<string, { name: string; logo: string }>>;

const fmtTime = (iso: string) =>
  new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "numeric", minute: "2-digit" }).format(new Date(iso))
    .replace(" AM", " am").replace(" PM", " pm");
/** A YYYY-MM-DD slate date, shown as a calendar date (no time zone shift). */
const fmtDate = (d: string, opts: Intl.DateTimeFormatOptions) =>
  new Intl.DateTimeFormat("en-US", { timeZone: "UTC", ...opts }).format(new Date(`${d}T12:00:00Z`));
const minus = (s: string) => s.replace("-", "−");
const num = (x: number | null | undefined, d = 1) => (x == null ? "–" : minus(x > 0 ? `+${x.toFixed(d)}` : x.toFixed(d)));
const line = (x: number | null | undefined) => (x == null ? "–" : x === 0 ? "PK" : num(x, 1).replace(/\.0$/, ""));
const price = (x: number | null | undefined) => (x == null ? "" : minus(x > 0 ? `+${x}` : `${x}`));
const units = (x: number) => `${x >= 0 ? "+" : "−"}${Math.abs(x).toFixed(2)} u`;
const plural = (n: number, one: string, many = one + "s") => `${n} ${n === 1 ? one : many}`;

function Team({ league, code }: { league: ProLeague; code: string }) {
  const t = TEAMS[league][code];
  return <ProTeamLogo league={league} team={t?.logo ?? code} px={18} />;
}

const isFinal = (g: ProGame) => g.graded_at != null;
const isOff = (g: ProGame) => !!g.final_status && /POSTPONED|CANCEL/.test(g.final_status);

function Verdict({ g }: { g: ProGame }) {
  if (g.verdict !== "NO_BET") return <span className="ons-badge ok">{g.bet ?? g.verdict}</span>;
  if (g.paper?.fires) return <span className="ons-badge risk">Paper {g.paper.side === "OVER" ? "over" : "under"}</span>;
  return <span className="ons-badge none" style={{ whiteSpace: "nowrap" }}>No bet</span>;
}

function PaperResult({ g }: { g: ProGame }) {
  const o = g.paper?.outcome;
  if (!g.paper?.fires || !o) return null;
  return <span className={`ons-badge ${o === "win" ? "ok" : o === "loss" ? "off" : "none"}`}>{o === "win" ? "Won" : o === "loss" ? "Lost" : "Push"}</span>;
}

// ── Slate table ─────────────────────────────────────────────────────────────

function SlateTable({ league, games }: { league: ProLeague; games: ProGame[] }) {
  const nba = league === "nba";
  const model = nba && games.some(g => g.paper?.pred_total != null);
  const anyFinal = games.some(g => isFinal(g) || isOff(g));
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="ons-table">
        <thead>
          <tr>
            <th className="hide-p">Time</th><th>Game</th>
            <th className="r">{nba ? "Spread" : "Puck line"}</th>
            <th className="r">Total</th>
            <th className="r hide-p" title="Away price above, home below">Moneyline</th>
            {model && <th className="r hide-p">Model total</th>}
            <th>Call</th>
            {anyFinal && <th className="r">Final</th>}
          </tr>
        </thead>
        <tbody>
          {games.map(g => {
            const home = g.home_team, away = g.away_team;
            return (
              <tr key={g.game_id}>
                <td className="ons-n hide-p">{g.start_time ? fmtTime(g.start_time).replace(/ (am|pm)$/, "") : "–"}
                  {g.start_time && <span className="sub">{fmtTime(g.start_time).slice(-2)}</span>}</td>
                <td>
                  <span className="flex items-center gap-2"><Team league={league} code={away} /><span style={{ whiteSpace: "nowrap" }}><span className="hide-p">{TEAMS[league][away]?.name ?? away}</span><span className="show-p">{away}</span></span></span>
                  <span className="flex items-center gap-2" style={{ marginTop: 4 }}><Team league={league} code={home} />
                    <span style={{ whiteSpace: "nowrap" }}><span className="hide-p">{TEAMS[league][home]?.name ?? home}</span><span className="show-p">{home}</span>{g.neutral_site ? <span className="text-muted"> (neutral)</span> : null}</span></span>
                  {g.start_time && <span className="sub show-p ons-n">{fmtTime(g.start_time)}</span>}
                </td>
                <td className="r ons-n">
                  {g.home_spread == null ? "–" : <><span className="hide-p">{home} </span>{line(g.home_spread)}<span className="sub">{price(g.home_spread_price)}</span></>}
                </td>
                <td className="r ons-n">
                  {g.total == null ? "–" : <>{g.total}<span className="sub hide-p">{g.over_price != null ? `o ${price(g.over_price)}` : ""}</span></>}
                </td>
                <td className="r ons-n hide-p">
                  {g.home_ml == null ? "–" : <>{price(g.away_ml)}<span className="sub">{price(g.home_ml)}</span></>}
                </td>
                {model && (
                  <td className="r ons-n hide-p">
                    {g.paper?.pred_total != null ? <>{g.paper.pred_total.toFixed(1)}<span className="sub">{num(g.paper.gap)} vs line</span></> : "–"}
                  </td>
                )}
                <td>
                  <Verdict g={g} />
                  {g.captured_after_start && <span className="sub hide-p" title="The line was captured after tip-off, so it isn't a pregame price">After start</span>}
                </td>
                {anyFinal && (
                  <td className="r ons-n">
                    {isOff(g) ? <span className="ons-badge none">{/CANCEL/.test(g.final_status!) ? "Canceled" : "Postponed"}</span>
                      : isFinal(g) ? <>
                          {/* Stacked like the teams: away score on top, home below. */}
                          <span className="block">{g.away_score}</span>
                          <span className="block" style={{ marginTop: 4 }}>{g.home_score}{g.shootout ? " SO" : g.went_ot ? " OT" : ""}</span>
                          <PaperResult g={g} />
                          <span className="sub hide-p">close {line(g.closing_home_spread)} · {g.closing_total ?? "–"}</span>
                        </>
                      : <span className="text-muted">–</span>}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Summary tiles ───────────────────────────────────────────────────────────

function Check({ done }: { done: boolean }) {
  return done
    ? <svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" /><path d="M4.8 8.3l2.2 2.2 4.2-4.6" /></svg>
    : <svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.25" /></svg>;
}

function SummaryTiles({ league, slate, rec }: { league: ProLeague; slate: ProSlate; rec: ProRecord }) {
  const nba = league === "nba";
  const games = slate.games;
  const finals = games.filter(g => isFinal(g) || isOff(g)).length;
  const first = games.map(g => g.start_time).filter((x): x is string => !!x).sort()[0];
  const isToday = slate.date === slate.today;
  const steps: Array<[boolean, string, string]> = [
    [slate.logged, "Lines captured", slate.logged ? `${games.length}${slate.captured_at ? ` · ${fmtTime(slate.captured_at)}` : ""}` : "not yet"],
    [slate.logged, "Rules checked", slate.logged ? `${games.filter(g => g.verdict !== "NO_BET").length} bets${nba ? ` · ${games.filter(g => g.paper?.fires).length} paper` : ""}` : "–"],
    [games.length > 0 && finals === games.length, "Graded", games.length ? (finals ? `${finals} of ${games.length}` : first ? `first game ${fmtTime(first)}` : "–") : "–"],
  ];
  const done = steps.filter(s => s[0]).length;
  const decided = rec.paper_wins + rec.paper_losses;
  const days = rec.days.filter(d => d.paper_wins + d.paper_losses + d.paper_pushes > 0);
  return (
    <div className="ons-tiles">
      <section className="ons-tile t t-edge" aria-labelledby="t-season">
        <h2 id="t-season">{rec.season ? `${rec.season - 1}–${String(rec.season).slice(2)} so far` : "Season so far"}</h2>
        <div className="big">{plural(rec.bets, "bet")}</div>
        <p>No rule has passed validation, so nothing is bet. {plural(rec.games_logged, "game")} logged{rec.first_date ? ` since ${fmtDate(rec.first_date, { month: "short", day: "numeric" })}` : ""}, {rec.games_graded} graded.</p>
      </section>

      {nba ? (
        <section className="ons-tile" aria-labelledby="t-paper">
          <h2 id="t-paper">Paper test · totals at the open</h2>
          <div className={`big${rec.paper_graded ? " n" : ""}`}>{rec.paper_graded ? `${rec.paper_wins}–${rec.paper_losses}${rec.paper_pushes ? `–${rec.paper_pushes}` : ""}` : "0 entries"}</div>
          <p className={decided ? "ons-n" : undefined}>{decided ? `${rec.paper_win_pct}% · ROI ${num(rec.paper_roi)}% · ${units(rec.paper_pnl ?? 0)}` : rec.paper_entries ? `${plural(rec.paper_entries, "entry", "entries")}, none graded yet` : "No game has met the test yet"}</p>
          {rec.paper_clv_avg != null && <p className="ons-n">CLV {num(rec.paper_clv_avg, 2)} pts · beat the close {rec.paper_beat_close_pct}%</p>}
          {days.length > 0 && (
            <div className="ons-wk" style={{ height: 40 }} role="img"
                 aria-label={`Paper wins and losses by day: ${days.map(d => `${d.date} ${d.paper_wins}-${d.paper_losses}`).join(", ")}`}>
              {days.map(d => <div key={d.date}>{Array.from({ length: d.paper_wins }, (_, i) => <i key={`w${i}`} className="w" />)}{Array.from({ length: d.paper_losses }, (_, i) => <i key={`l${i}`} className="l" />)}</div>)}
            </div>
          )}
        </section>
      ) : (
        <section className="ons-tile" aria-labelledby="t-lines">
          <h2 id="t-lines">Lines on record</h2>
          <div className="big n">{rec.games_logged}</div>
          <p>Every game's puck line, moneyline and total as captured in the morning, with the close added after the final. That's the record a future rule gets graded against.</p>
          {rec.captured_after_start > 0 && <p className="tnote">{rec.captured_after_start} captured after puck drop (not pregame)</p>}
        </section>
      )}

      <section className="ons-tile" aria-labelledby="t-run">
        <h2 id="t-run">{isToday ? "Today's run" : `${fmtDate(slate.date, { weekday: "short", month: "short", day: "numeric" })} run`}</h2>
        <div className="big">{done} of {steps.length} done</div>
        <ol className="ons-steps">
          {steps.map(([ok, label, detail]) => <li key={label} className={ok ? "ok" : "todo"}><Check done={ok} /><b>{label}</b><span>{detail}</span></li>)}
        </ol>
      </section>

      <section className="ons-tile" aria-labelledby="t-model">
        <h2 id="t-model">The model</h2>
        <div className="big">No rules yet</div>
        {nba ? (
          <p>Every candidate edge (rest, travel, form, the spread and totals models) was walk-forward tested and rejected. The paper test takes the open total when our model is 12+ points off and both prices are −135 to +115. It was designed after seeing the data, so it runs on paper only.</p>
        ) : (
          <p>Every candidate edge (rest, xG, goalies, puck line and moneyline bands) was walk-forward tested and rejected. The closest, the rested team's moneyline against a back-to-back, was +4.1% out of sample with an interval that crosses zero.</p>
        )}
      </section>
    </div>
  );
}

// ── Page ────────────────────────────────────────────────────────────────────

export function ProSlatePage({ league }: { league: ProLeague }) {
  // ?date=YYYY-MM-DD opens a past slate (shareable); otherwise the API's today.
  const [day, setDay] = useState<string | undefined>(() =>
    typeof window === "undefined" ? undefined : new URLSearchParams(window.location.search).get("date") ?? undefined);
  const [slate, setSlate] = useState<ProSlate | null>(null);
  const [rec, setRec] = useState<ProRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { proApi.record(league).then(setRec).catch((e: Error) => setError(e.message)); }, [league]);
  useEffect(() => { proApi.slate(league, day).then(setSlate).catch((e: Error) => setError(e.message)); }, [league, day]);

  const pad = { padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" } as const;
  if (error) return <div className="ons-page" style={pad}><ErrorState message={error} /></div>;
  if (!slate || !rec) return <Loading label="Loading the slate…" />;

  const name = NAME[league];
  const nba = league === "nba";
  const games = slate.games;
  const isToday = slate.date === slate.today;
  const dayLong = fmtDate(slate.date, { weekday: "long", month: "long", day: "numeric" });
  const books = Array.from(new Set(games.map(g => g.book).filter(Boolean)));
  const paperToday = games.filter(g => g.paper?.fires).length;
  const finals = games.filter(isFinal).length;

  const lede = !slate.logged
    ? <>No lines logged for {isToday ? "today" : dayLong} yet. The morning sync captures every game's line at about 9 am.</>
    : <>
        {plural(games.length, "game")} {isToday ? "today" : `on ${dayLong.split(",")[0]}`}, <b>no bets</b>: no {name} rule has passed validation, so this page logs each line for the record.
        {nba && <> {paperToday ? <b>{plural(paperToday, "game")} met the paper totals test.</b> : "No game met the paper totals test."}</>}
        {finals > 0 && <> {finals} of {games.length} final.</>}
      </>;

  const recent = rec.days.slice(-10).reverse();

  return (
    <div className="ons-page" style={pad}>
      <PageHead
        title="Degenerates Corner"
        titleSub={`— ${name}`}
        kicker={`${dayLong}${books.length ? ` · ${books.join(", ")} lines` : ""}${slate.captured_at ? ` · captured ${fmtTime(slate.captured_at)}` : ""}`}
        sub={lede}
        right={
          <div className="flex gap-2">
            <button className="ons-tap ons-btn" disabled={!slate.previous_date} onClick={() => setDay(slate.previous_date ?? undefined)}>Previous day</button>
            {!isToday && <button className="ons-tap ons-btn" onClick={() => setDay(slate.today)}>Today</button>}
            <button className="ons-tap ons-btn" disabled={!slate.next_date} onClick={() => setDay(slate.next_date ?? undefined)}>Next day</button>
          </div>
        }
        scene={<PixelScene scene="sports" label={`a sports scene for the ${name} slate`} />}
      />

      <SummaryTiles league={league} slate={slate} rec={rec} />

      <div className="ons-grid">
        <section className="ons-card s8" aria-labelledby="slate-h">
          <div className="ons-ch">
            <h2 id="slate-h">{isToday ? "Today's slate" : fmtDate(slate.date, { weekday: "short", month: "short", day: "numeric" })}</h2>
            <span className="aside">Mountain time · lines as captured · {nba ? "spread" : "puck line"} is the home side</span>
          </div>
          {games.length ? <SlateTable league={league} games={games} />
            : <Empty message={slate.logged ? "No games this day." : "No lines logged for this day."} detail={slate.logged ? undefined : "nba_nhl_generate_picks.py hasn't run for this date."} />}
          {nba && games.length > 0 && <p className="ons-note">Model total is the regular-season totals model as of the morning, against the captured total. A paper entry needs a 12-point gap; it's tracked, never bet.</p>}
        </section>

        <div className="s4 ons-col">
          <section className="ons-card" aria-labelledby="days-h">
            <div className="ons-ch"><h2 id="days-h">Day by day</h2><span className="aside">{nba ? "Paper record" : "Games logged"}</span></div>
            {recent.length ? (
              <table className="ons-table">
                <thead><tr><th>Date</th><th className="r">Games</th><th className="r">{nba ? "Paper" : "Graded"}</th></tr></thead>
                <tbody>
                  {recent.map(d => (
                    // The row is a click target for the mouse; the button inside is the keyboard and screen-reader control.
                    <tr key={d.date} className="click" onClick={() => setDay(d.date)}>
                      <td>
                        <button type="button" className="ons-rowlink" onClick={(e) => { e.stopPropagation(); setDay(d.date); }}
                                aria-current={d.date === slate.date ? "date" : undefined}>
                          {fmtDate(d.date, { weekday: "short", month: "short", day: "numeric" })}
                        </button>
                        {d.date === slate.date && <span className="text-muted"> · shown</span>}
                      </td>
                      <td className="r ons-n">{d.games}</td>
                      <td className="r ons-n">{nba ? (d.paper_entries ? `${d.paper_wins}–${d.paper_losses}${d.paper_pushes ? `–${d.paper_pushes}` : ""}` : "–") : `${d.graded}`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <Empty message="Nothing logged this season yet." />}
          </section>
        </div>
      </div>
    </div>
  );
}
