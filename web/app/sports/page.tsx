"use client";

// Sports (Logbook Color). Neutral like the other Play pages, except college football, which keeps CFB tangerine
// and links to Degenerates Corner. Real data only: /sports/today and /sports/team-news (ESPN, cached 60 s).
// Fixes from docs/design/critique.md §12: one games table (no Top/All duplication) with league tabs and your
// teams pinned; your teams get a block of their own with result, next game and TV; times are Denver time;
// the winner is bold instead of the loser being greyed to 1.6:1; no arbitrary coloured rules; live is said in
// words as well as colour.

import { useEffect, useMemo, useState } from "react";
import { sportsApi, type SportsToday, type TeamNews, type Game } from "@/lib/api";
import { PageHead, Loading, ErrorState } from "@/components/ui/primitives";
import { PixelScene } from "@/components/ui/PixelScene";
import { TeamMark } from "@/components/sports/GameRow";
import { TZ, isoDenver, fmt, plural, join } from "@/lib/dates";

const LIVE_POLL_MS = 60_000; // the API caches ESPN for 60 s, so polling faster buys nothing
const PAGE = 25;
const LEAGUE: Record<string, string> = { nfl: "NFL", cfb: "College football", nba: "NBA", mlb: "MLB", nhl: "NHL", mls: "MLS" };

const time = (utc: string | null) => (utc ? new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "numeric", minute: "2-digit" }).format(new Date(utc)).replace(" AM", " am").replace(" PM", " pm") : "TBD");
const dayOf = (utc: string | null) => (utc ? isoDenver(new Date(utc)) : "");
const when = (g: Game, today: string) => {
  const d = dayOf(g.start_utc);
  return d === today ? time(g.start_utc) : `${fmt(d, { weekday: "short" })} ${time(g.start_utc)}`;
};
/** Status in words: "Live · 2nd 4:12", "Final", or the start time in Denver. */
const status = (g: Game, today: string) => (g.state === "pre" ? when(g, today) : g.state === "in" ? `Live · ${g.status_detail}` : g.status_detail || "Final");

/** ESPN's short name, unless it's only the city ("Orlando" for Orlando City SC beside the Magic). */
const nick = (s: Game["home"]) => (s.short && s.name.startsWith(s.short + " ") && s.name.split(" ").length > 2 ? s.name : s.short || s.name);

function mine(g: Game) {
  const home = g.home.name === g.my_team;
  const us = home ? g.home : g.away, them = home ? g.away : g.home;
  return { us, them, home };
}

export default function SportsPage() {
  const [data, setData] = useState<SportsToday | null>(null);
  const [news, setNews] = useState<TeamNews | null | false>(null);
  const [error, setError] = useState<string | null>(null);
  const [league, setLeague] = useState("all");
  const [team, setTeam] = useState("all");
  const [count, setCount] = useState(PAGE);

  useEffect(() => {
    sportsApi.today().then(setData).catch((e) => setError(e.message));
    sportsApi.teamNews().then(setNews).catch(() => setNews(false));
  }, []);

  useEffect(() => {
    if (!data?.any_live) return;
    const t = setInterval(() => { sportsApi.today().then(setData).catch(() => {}); }, LIVE_POLL_MS);
    return () => clearInterval(t);
  }, [data?.any_live]);

  const games = useMemo(() => {
    if (!data) return [];
    const order = (g: Game) => (g.my_team ? 0 : 1) * 10 + (g.is_live ? 0 : g.state === "pre" ? 1 : 2);
    return data.all.filter((g) => league === "all" || g.league === league)
      .sort((a, b) => order(a) - order(b) || (a.start_utc ?? "").localeCompare(b.start_utc ?? ""));
  }, [data, league]);

  if (error) return <div className="ons-page" style={{ padding: "34px 44px 48px" }}><ErrorState message={error} /></div>;
  if (!data) return <Loading label="Loading scores…" />;

  const today = data.date;
  const teams = news ? news.teams : [];
  const byTeam = new Map<string, Game>();
  [...data.my_teams, ...data.upcoming].forEach((g) => { if (g.my_team && !byTeam.has(g.my_team)) byTeam.set(g.my_team, g); });
  const allTeams = teams.length ? teams.map((t) => t.name) : Array.from(byTeam.keys());
  const idle = allTeams.filter((t) => !byTeam.has(t));
  const live = data.all.filter((g) => g.is_live);
  const todayMine = data.my_teams;
  const nextMine = [...data.my_teams.filter((g) => g.state !== "post"), ...data.upcoming].sort((a, b) => (a.start_utc ?? "").localeCompare(b.start_utc ?? ""))[0];
  const updated = new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "numeric", minute: "2-digit" }).format(new Date(data.fetched_at)).toLowerCase();
  const shortName = (g: Game) => nick(mine(g).us);
  const matchup = (g: Game) => { const { them, home } = mine(g); return `${shortName(g)} ${home ? "vs" : "at"} ${them.short || them.name}`; };
  const line = (g: Game) => `${matchup(g)}${g.state === "pre" ? ` ${dayOf(g.start_utc) === today ? time(g.start_utc) : `${fmt(dayOf(g.start_utc), { weekday: "long" })} ${time(g.start_utc)}`}` : g.state === "in" ? ` (live, ${g.status_detail})` : ` (${g.status_detail})`}`;
  const board = (() => { const g = live.find((x) => x.my_team) ?? todayMine.find((x) => x.state === "post") ?? nextMine; return g ? `${g.away.score ?? 0}-${g.home.score ?? 0}` : ""; })();
  const articles = news ? news.articles.filter((a) => team === "all" || a.team === team) : [];
  const leagues = Array.from(new Set(data.all.map((g) => g.league)));

  const lede = (
    <>
      {todayMine.length ? <><b>{todayMine.length} of your {allTeams.length} teams play today</b>: {join(todayMine.map(line))}.{" "}</> : <>None of your teams play today.{" "}</>}
      {data.upcoming.length > 0 && <>Next: {join(data.upcoming.map(line))}.{" "}</>}
      {idle.length > 0 && <>No game scheduled for {join(idle.map((t) => t.split(" ").slice(-1)[0]))}.</>}
    </>
  );

  return (
    <div className="ons-page" style={{ padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" }}>
      <PageHead
        title="Sports"
        kicker={`${fmt(today, { weekday: "long", month: "long", day: "numeric" })} · scores and news from ESPN · updated ${updated}${data.any_live ? ", refreshing every minute while a game is live" : ""}`}
        sub={lede}
        scene={<PixelScene scene="sports" data={{ board }} label={`a hockey player skates in and scores; the scoreboard reads ${board || "0-0"}`} />}
      />

      <div className="ons-tiles" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))" }}>
        <section className="ons-tile"><h2>Your teams today</h2><div className="big n">{todayMine.length} of {allTeams.length}</div><p>{todayMine.length ? join(todayMine.map(shortName)) : "No games today."}</p></section>
        <section className="ons-tile"><h2>Live now</h2><div className="big n">{live.length}</div><p>{live.length ? `${live.filter((g) => g.my_team).length} of them yours` : "Nothing in progress."}</p></section>
        <section className="ons-tile"><h2>Next up</h2><div className="big">{nextMine ? (nextMine.state === "in" ? "Live" : when(nextMine, today)) : "–"}</div><p>{nextMine ? matchup(nextMine) : "Nothing scheduled."}{nextMine?.broadcasts[0] ? ` · ${nextMine.broadcasts[0]}` : ""}</p></section>
        <section className="ons-tile"><h2>No game scheduled</h2><div className="big n">{idle.length}</div><p>{idle.length ? join(idle) : "Every team has a game on the schedule."}</p></section>
      </div>

      <div className="ons-grid">
        <section className="ons-card s8" aria-labelledby="mine-h">
          <div className="ons-ch"><h2 id="mine-h">Your teams</h2><span className="aside">Today&apos;s game, or the next one · Denver time</span></div>
          <table className="ons-table">
            <thead><tr><th>Team</th><th>Game</th><th className="r">When</th><th className="r">Score</th><th className="r hide-p">TV</th></tr></thead>
            <tbody>
              {[...allTeams].sort((a, b) => (byTeam.get(a)?.start_utc ?? "9") .localeCompare(byTeam.get(b)?.start_utc ?? "9")).map((t) => {
                const g = byTeam.get(t), info = teams.find((x) => x.name === t);
                if (!g) return (
                  <tr key={t}><td><span className="ons-team">{info && <TeamMark side={{ logo: info.logo, abbr: info.abbr ?? "", name: t }} px={20} />}{t}</span></td><td className="text-muted" colSpan={4}>No game scheduled{info ? ` (${info.league.toUpperCase()})` : ""}</td></tr>
                );
                const { us, them, home } = mine(g), started = g.state !== "pre";
                const result = g.state === "post" ? (us.winner ? "W" : them.winner ? "L" : "T") : null;
                return (
                  <tr key={t}>
                    <td><span className="ons-team"><TeamMark side={us} px={20} />{nick(us)}{us.record && <span className="text-muted ons-n hide-p" style={{ fontSize: 12, whiteSpace: "nowrap" }}>{us.record}</span>}</span></td>
                    <td>{home ? "vs" : "at"} {them.short || them.name}<span className="sub">{LEAGUE[g.league] ?? g.league_label}{g.venue ? <span className="hide-p"> · {g.venue}</span> : null}</span></td>
                    <td className="r" style={{ whiteSpace: "nowrap", color: g.is_live ? "var(--neg)" : undefined, fontWeight: g.is_live ? 600 : undefined }}>{status(g, today)}</td>
                    <td className="r ons-n" style={{ whiteSpace: "nowrap" }}>{started ? <>{result && <span className={`ons-badge ${result === "W" ? "ok" : result === "L" ? "off" : "none"}`} style={{ marginRight: 6 }}>{result}</span>}{us.score ?? "–"}–{them.score ?? "–"}</> : "–"}</td>
                    <td className="r hide-p text-muted" style={{ fontSize: 13 }}>{g.broadcasts.slice(0, 2).join(", ") || "–"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>

        <section className="ons-card s4" aria-labelledby="news-h">
          <div className="ons-ch"><h2 id="news-h">News</h2>
            {news && news.teams.length > 0 && <select className="ons-select" value={team} onChange={(e) => setTeam(e.target.value)} aria-label="Team"><option value="all">All your teams</option>{news.teams.map((t) => <option key={t.name} value={t.name}>{t.name}</option>)}</select>}
          </div>
          {news === false ? <p className="ons-note m-0">Couldn&apos;t load news.</p> : news === null ? <p className="ons-note m-0">Loading news…</p> : articles.length === 0 ? <p className="ons-note m-0">No recent stories{team !== "all" ? ` for ${team}` : ""}.</p> : (
            <ul className="ons-news">
              {articles.slice(0, 8).map((a) => (
                <li key={a.url}>
                  <a href={a.url} target="_blank" rel="noreferrer">{a.title}</a>
                  <span>{a.team}{a.published ? ` · ${fmt(isoDenver(new Date(a.published)), { month: "short", day: "numeric" })}` : ""}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="ons-note">ESPN&apos;s team feeds include league-wide stories, filed under the team whose feed they came from.</p>
        </section>

        <section className="ons-card s12" aria-labelledby="all-h">
          <div className="ons-ch"><h2 id="all-h">All games today</h2><span className="aside">{plural(data.all.length, "game")} · your teams first · times in Denver</span></div>
          <div className="ons-tabs" role="tablist" aria-label="League" style={{ marginBottom: 8 }}>
            {["all", ...leagues].map((l) => <button key={l} type="button" role="tab" aria-selected={league === l} onClick={() => { setLeague(l); setCount(PAGE); }}>{l === "all" ? "All" : LEAGUE[l] ?? l}<span className="text-muted" style={{ fontWeight: 400 }}> · {l === "all" ? data.all.length : data.all.filter((g) => g.league === l).length}</span></button>)}
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="ons-table ons-games">
              <thead><tr><th>Away</th><th className="r">Score</th><th>Home</th><th className="r">Status</th><th className="hide-p">League · TV</th></tr></thead>
              <tbody>
                {games.slice(0, count).map((g) => {
                  const started = g.state !== "pre";
                  const side = (s: Game["home"]) => <span className="ons-team" style={{ fontWeight: s.winner ? 600 : 400 }}><TeamMark side={s} px={18} />{s.rank ? <span className="text-muted ons-n" style={{ fontSize: 12 }}>{s.rank}</span> : null}{s.short || s.name}</span>;
                  return (
                    <tr key={g.id} className={g.my_team ? "is-mine" : undefined}>
                      <td>{side(g.away)}</td>
                      <td className="r ons-n" style={{ whiteSpace: "nowrap" }}>{started ? `${g.away.score ?? "–"}–${g.home.score ?? "–"}` : "–"}</td>
                      <td>{side(g.home)}</td>
                      <td className="r" style={{ whiteSpace: "nowrap", color: g.is_live ? "var(--neg)" : undefined, fontWeight: g.is_live ? 600 : undefined }}>
                        {g.link ? <a className="ons-quietlink" href={g.link} target="_blank" rel="noreferrer">{status(g, today)}</a> : status(g, today)}
                      </td>
                      <td className="hide-p">
                        {g.league === "cfb" ? <a href="/cfb" className="ons-side l-edge" style={{ textDecoration: "none" }}>CFB</a> : <span className="text-muted" style={{ fontSize: 13 }}>{LEAGUE[g.league] ?? g.league_label}</span>}
                        <span className="text-muted" style={{ fontSize: 13 }}>{g.broadcasts.length ? ` · ${g.broadcasts.slice(0, 2).join(", ")}` : ""}{g.my_team ? " · yours" : ""}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {games.length > count && <button type="button" className="ons-tap ons-btn" style={{ marginTop: 12 }} onClick={() => setCount((n) => n + PAGE)}>Show {Math.min(PAGE, games.length - count)} more of {games.length - count}</button>}
          {data.errors.length > 0 && <p className="ons-note">Some leagues didn&apos;t load: {data.errors.join("; ")}.</p>}
        </section>
      </div>
    </div>
  );
}
