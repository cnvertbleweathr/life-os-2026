"use client";

import { useEffect, useState } from "react";
import { sportsApi, type StreamsToday, type StreamMatch, type NewsArticle } from "@/lib/api";
import { Card, PageHead, K, Empty, Loading, ErrorState } from "@/components/ui/primitives";
import { ProTeamLogo } from "@/components/ui/ProTeamLogo";

import mlbLogos from "@/lib/mlb_team_logos.json";
import nbaLogos from "@/lib/nba_team_logos.json";
import nflLogos from "@/lib/nfl_team_logos.json";

const LOGO_MAPS: Record<string, Record<string, string>> = {
  mlb: mlbLogos,
  nba: nbaLogos,
  nfl: nflLogos,
};

// Your real 8 configured teams (scripts/fetch_streams.py MY_TEAMS), used to
// build per-team news queries the same way the old Streamlit Sports page
// did (fetch_team_news(query) called once per team). That per-team logic
// never made it into the FastAPI router — /sports/news today only takes a
// single generic q param. This queries it once per team and merges client-
// side as an honest interim, not a fake "it's done" state. Real fix is a
// dedicated /sports/team-news endpoint — tracked in the roadmap.
const MY_TEAM_QUERIES = [
  "Orlando Magic NBA",
  "Tampa Bay Buccaneers NFL",
  "Orlando City Soccer MLS",
  "Miami Marlins MLB",
  "Florida Panthers NHL",
  "Colorado Avalanche NHL",
  "Denver Nuggets NBA",
  "Colorado Rockies MLB",
];

// Maps streamed.pk's category strings to our logo-map league keys.
// Confirmed against live data 2026-06-21: "baseball" appears for MLB games.
// Other variants are reasonable guesses pending confirmation.
function detectLeague(category: string): string | null {
  const c = category.toLowerCase().replace(/[-_]/g, " ");
  if (c.includes("baseball") || c.includes("mlb")) return "mlb";
  if (c.includes("basketball") || c.includes("nba")) return "nba";
  if (c.includes("american football") || c.includes("nfl")) return "nfl";
  return null; // MLS, NHL, golf, fight, afl, rugby, tennis, cricket, etc. — not in scope
}

// streamed.pk team names are full ("Colorado Rockies"); our maps key on
// the short franchise name ("Rockies"). Actually test candidate suffixes
// against the real map keys rather than guessing a fixed word count —
// "Colorado Rockies" needs the 1-word suffix ("Rockies") to hit, while
// "Boston Red Sox" needs the 2-word suffix ("Red Sox") to hit.
function shortTeamName(fullName: string, league: string | null): string | null {
  if (!league) return null;
  const map = LOGO_MAPS[league];
  if (!map) return null;
  const words = fullName.trim().split(/\s+/);
  for (let n = 1; n <= Math.min(2, words.length); n++) {
    const candidate = words.slice(-n).join(" ");
    if (candidate in map) return candidate;
  }
  return null; // no match — let ProTeamLogo fall back to initials
}

function MatchCard({ m, accent }: { m: StreamMatch; accent?: boolean }) {
  const league = detectLeague(m.category);
  const homeShort = m.home_team ? shortTeamName(m.home_team, league) : null;
  const awayShort = m.away_team ? shortTeamName(m.away_team, league) : null;
  const showLogos = league && homeShort && awayShort;

  return (
    <a
      href={m.watch_url}
      target="_blank"
      rel="noopener noreferrer"
      className="ons-row flex items-center gap-3 no-underline text-inherit cursor-pointer border-t border-border-2"
      style={{ padding: "12px 6px", margin: "0 -6px" }}
    >
      {showLogos ? (
        <div className="flex items-center -space-x-1.5 shrink-0">
          <ProTeamLogo league={league!} team={awayShort!} px={22} />
          <ProTeamLogo league={league!} team={homeShort!} px={22} />
        </div>
      ) : null}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="truncate" style={{ fontSize: 13.5, fontWeight: accent ? 600 : 400 }}>
            {m.team_label ? m.team_label.replace(/^[^\s]+\s/, "") : m.title}
          </span>
          {m.is_live && (
            <span className="font-mono shrink-0" style={{ fontSize: 8.5, color: "#a8473a" }}>● LIVE</span>
          )}
        </div>
        <div className="text-faint mt-0.5 truncate" style={{ fontSize: 11 }}>
          {m.home_team && m.away_team ? `${m.away_team} @ ${m.home_team}` : m.title}
        </div>
      </div>
      <div className="text-right shrink-0">
        <div className="font-mono text-muted" style={{ fontSize: 10.5 }}>
          {m.is_live ? "NOW" : m.kickoff_local ?? "TBD"}
        </div>
        <div className="font-mono text-faint" style={{ fontSize: 8.5, marginTop: 2 }}>
          {m.category.replace(/-/g, " ")}
        </div>
      </div>
      <span
        className="ons-tap font-mono shrink-0"
        style={{
          fontSize: 9, color: m.is_live ? "#fff" : "#736e5f",
          background: m.is_live ? "#1d5536" : "transparent",
          border: `1px solid ${m.is_live ? "#1d5536" : "#e6e3dc"}`,
          borderRadius: 999, padding: "4px 10px",
        }}
      >
        WATCH
      </span>
    </a>
  );
}

export default function SportsPage() {
  const [streams, setStreams] = useState<StreamsToday | null>(null);
  const [news, setNews] = useState<NewsArticle[] | null>(null);
  const [newsError, setNewsError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    sportsApi.streams().then(setStreams).catch((e) => setError(e.message));

    // Fire one query per team, merge results. If NEWS_API_KEY isn't set
    // server-side, every call returns [] — that's the existing, correct
    // "Not configured" behavior elsewhere (Music page), not an error.
    Promise.all(MY_TEAM_QUERIES.map((q) => sportsApi.news(q).catch(() => [] as NewsArticle[])))
      .then((results) => {
        const seen = new Set<string>();
        const merged: NewsArticle[] = [];
        for (const batch of results) {
          for (const a of batch) {
            if (!seen.has(a.url)) {
              seen.add(a.url);
              merged.push(a);
            }
          }
        }
        merged.sort((a, b) => (b.published ?? "").localeCompare(a.published ?? ""));
        setNews(merged);
      })
      .catch((e) => setNewsError(e.message));
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!streams) return <Loading />;

  const { my_teams: myTeamsRaw, top5, popular, fetched_at } = streams;
  // fetch_streams.py hardcodes golf as always matching "my teams" (is_my_team
  // returns True for any golf category, unconditionally) — that's not an
  // actual team preference, just a quirk of the source script. Filter it
  // out here rather than show golf tournaments as if they were one of the
  // 8 real configured teams.
  const my_teams = myTeamsRaw.filter((m) => m.category.toLowerCase() !== "golf");
  const fetchedLabel = fetched_at
    ? new Date(fetched_at).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })
    : null;

  return (
    <div className="ons-page" style={{ padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" }}>
      <PageHead
        title="Sports"
        kicker="Live streams · via streamed.pk"
        right={
          <div className="font-mono text-right text-faint" style={{ fontSize: 9.5 }}>
            {fetchedLabel ? `UPDATED ${fetchedLabel}` : "NOT FETCHED YET"}<br />
            {my_teams.length} OF YOUR TEAMS TODAY
          </div>
        }
      />

      <div className="grid gap-[22px] items-start" style={{ gridTemplateColumns: "1fr 1fr" }}>
        {/* My Teams */}
        <div>
          <div className="mb-4" style={{ borderTop: "2.5px solid #1d5536", paddingTop: 12 }}>
            <K color="#232a22" style={{ fontSize: 11, letterSpacing: "1.5px" }}>My Teams Today</K>
          </div>
          <Card pad={0}>
            <div style={{ padding: "4px 18px 12px" }}>
              {my_teams.length === 0 ? (
                <Empty
                  message="None of your teams are playing today."
                  detail="Magic, Bucs, Orlando City, Marlins, Panthers, Avalanche, Nuggets, Rockies — checked against today's streamed.pk listings."
                />
              ) : (
                my_teams.map((m, i) => <MatchCard key={i} m={m} accent />)
              )}
            </div>
          </Card>
          <p className="font-mono text-faint mt-[10px]" style={{ fontSize: 8.5, lineHeight: 1.5 }}>
            STREAM LISTINGS ONLY — NO STANDINGS OR RECORD DATA SOURCE EXISTS YET.
            LOGOS COVER MLB/NBA/NFL ONLY — ORLANDO CITY (MLS) AND PANTHERS/AVALANCHE (NHL) SHOW INITIALS UNTIL A LOGO SOURCE IS ADDED.
          </p>
        </div>

        {/* Top 5 + Popular */}
        <div>
          <div className="flex justify-between items-center mb-4" style={{ borderTop: "2.5px solid #9a6a1e", paddingTop: 12 }}>
            <K color="#232a22" style={{ fontSize: 11, letterSpacing: "1.5px" }}>Top 5 Today</K>
            <span className="font-mono text-faint" style={{ fontSize: 9 }}>AI-RANKED · streamed.pk</span>
          </div>
          <Card pad={0} style={{ marginBottom: 22 }}>
            <div style={{ padding: "4px 18px 12px" }}>
              {top5.length === 0 ? (
                <Empty message="No top-5 picks today." />
              ) : (
                top5.map((m, i) => <MatchCard key={i} m={m} />)
              )}
            </div>
          </Card>

          <K style={{ marginBottom: 12 }}>Other Popular</K>
          <Card pad={0}>
            <div className="ons-scroll" style={{ padding: "4px 18px 12px", maxHeight: 320, overflowY: "auto" }}>
              {popular.length === 0 ? (
                <Empty message="No other popular streams today." />
              ) : (
                popular.map((m, i) => <MatchCard key={i} m={m} />)
              )}
            </div>
          </Card>
        </div>
      </div>

      {/* News — your teams only */}
      <div className="mt-[22px]">
        <div className="flex justify-between items-center mb-4" style={{ borderTop: "2.5px solid #3a5f7a", paddingTop: 12 }}>
          <K color="#232a22" style={{ fontSize: 11, letterSpacing: "1.5px" }}>News · Your Teams</K>
          <span className="font-mono text-faint" style={{ fontSize: 9 }}>NewsAPI · per-team query</span>
        </div>
        <Card pad={0}>
          <div style={{ padding: "4px 18px 12px" }}>
            {newsError ? (
              <Empty message="Couldn't load news." detail={newsError} />
            ) : news === null ? (
              <Empty message="Loading…" />
            ) : news.length === 0 ? (
              <Empty
                message="Not configured."
                detail="NEWS_API_KEY isn't set in .env — same dependency as Music. Once set, this section queries all 8 of your teams and merges results, but each team gets its own query rather than one generic sports search — a real /sports/team-news endpoint that does this server-side is on the roadmap to replace this client-side merge."
              />
            ) : (
              news.slice(0, 12).map((a, i) => (
                <a
                  key={i}
                  href={a.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="ons-row flex items-start gap-3 no-underline text-inherit cursor-pointer border-t border-border-2"
                  style={{ padding: "11px 6px", margin: "0 -6px" }}
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-ink" style={{ fontSize: 13, lineHeight: 1.4 }}>{a.title}</div>
                    <div className="font-mono text-faint mt-1" style={{ fontSize: 9.5 }}>
                      {a.source}
                      {a.published && ` · ${new Date(a.published).toLocaleDateString("en-US", { month: "short", day: "numeric" })}`}
                    </div>
                  </div>
                </a>
              ))
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
