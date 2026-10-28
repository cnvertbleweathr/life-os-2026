"use client";

import { useEffect, useState } from "react";
import { sportsApi, type SportsToday, type TeamNews } from "@/lib/api";
import { Card, PageHead, K, Empty, Loading, ErrorState } from "@/components/ui/primitives";
import { GameRow, TeamMark } from "@/components/sports/GameRow";

// Scores refresh while anything is live; the API caches ESPN for 60s, so
// polling faster than that buys nothing.
const LIVE_POLL_MS = 60_000;

function SectionHead({ title, color, right }: { title: string; color: string; right?: string }) {
  return (
    <div className="flex justify-between items-center mb-4" style={{ borderTop: `2.5px solid ${color}`, paddingTop: 12 }}>
      <K color="#232a22" style={{ fontSize: 11, letterSpacing: "1.5px" }}>{title}</K>
      {right && <span className="font-mono text-faint" style={{ fontSize: 9 }}>{right}</span>}
    </div>
  );
}

export default function SportsPage() {
  const [data, setData] = useState<SportsToday | null>(null);
  const [news, setNews] = useState<TeamNews | null>(null);
  const [newsError, setNewsError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [teamFilter, setTeamFilter] = useState<string | null>(null);

  useEffect(() => {
    sportsApi.today().then(setData).catch((e) => setError(e.message));
    sportsApi.teamNews().then(setNews).catch((e) => setNewsError(e.message));
  }, []);

  useEffect(() => {
    if (!data?.any_live) return;
    const t = setInterval(() => {
      sportsApi.today().then(setData).catch(() => { /* keep last good scores */ });
    }, LIVE_POLL_MS);
    return () => clearInterval(t);
  }, [data?.any_live]);

  if (error) return <ErrorState message={error} />;
  if (!data) return <Loading label="Loading scores…" />;

  const { my_teams, upcoming, top, all, fetched_at, errors } = data;
  const fetchedLabel = new Date(fetched_at).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  const liveCount = all.filter((g) => g.is_live).length;
  const articles = (news?.articles ?? []).filter((a) => !teamFilter || a.team === teamFilter);

  return (
    <div className="ons-page" style={{ padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" }}>
      <PageHead
        title="Sports"
        kicker="Scores · Schedules · News — via ESPN"
        right={
          <div className="font-mono text-right text-faint" style={{ fontSize: 9.5 }}>
            UPDATED {fetchedLabel}
            {data.any_live && " · AUTO-REFRESH"}<br />
            {my_teams.length} OF YOUR TEAMS TODAY · {liveCount} LIVE
          </div>
        }
      />

      <div className="ons-stack grid gap-[22px] items-start" style={{ gridTemplateColumns: "1.4fr 1fr" }}>
        <div>
          <SectionHead title="My Teams Today" color="#1d5536" />
          <Card pad={0} style={{ marginBottom: 22 }}>
            <div style={{ padding: "4px 18px 12px" }}>
              {my_teams.length === 0 ? (
                <Empty message="None of your teams are playing today." />
              ) : (
                my_teams.map((g) => <GameRow key={g.id} g={g} />)
              )}
            </div>
          </Card>

          <SectionHead title="Coming Up" color="#3a5f7a" right="NEXT GAME PER TEAM" />
          <Card pad={0} style={{ marginBottom: 22 }}>
            <div style={{ padding: "4px 18px 12px" }}>
              {upcoming.length === 0 ? (
                <Empty message="No upcoming games scheduled." detail="Offseason teams drop off until ESPN posts their schedule." />
              ) : (
                upcoming.map((g) => <GameRow key={g.id} g={g} withDay />)
              )}
            </div>
          </Card>

          <SectionHead title="Top Games Today" color="#9a6a1e" right="POSTSEASON · NATIONAL TV · RANKED" />
          <Card pad={0} style={{ marginBottom: 22 }}>
            <div style={{ padding: "4px 18px 12px" }}>
              {top.length === 0 ? (
                <Empty message="No games today." />
              ) : (
                top.map((g, i) => <GameRow key={g.id} g={g} rank={i + 1} />)
              )}
            </div>
          </Card>

          <K style={{ marginBottom: 12 }}>All Games Today · {all.length}</K>
          <Card pad={0}>
            <div className="ons-scroll" style={{ padding: "4px 18px 12px", maxHeight: 420, overflowY: "auto" }}>
              {all.length === 0 ? (
                <Empty message="Nothing on the board today." />
              ) : (
                all.map((g) => <GameRow key={g.id} g={g} />)
              )}
            </div>
          </Card>

          {errors.length > 0 && (
            <p className="font-mono text-faint mt-3" style={{ fontSize: 8.5, lineHeight: 1.5 }}>
              PARTIAL DATA — {errors.join(" · ")}
            </p>
          )}
        </div>

        <div>
          <SectionHead title="News · Your Teams" color="#3a5f7a" right="ESPN" />
          {news && news.teams.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-3">
              {[{ name: null as string | null, short: "All" as string | null, abbr: "ALL", logo: null as string | null }, ...news.teams].map((t) => {
                const active = teamFilter === t.name;
                return (
                  <button
                    key={t.name ?? "all"}
                    onClick={() => setTeamFilter(t.name)}
                    title={t.name ?? "All teams"}
                    className="ons-tap font-mono flex items-center gap-1"
                    style={{
                      fontSize: 9, borderRadius: 999, padding: "3px 9px",
                      color: active ? "#fff" : "#736e5f",
                      background: active ? "#1d5536" : "transparent",
                      border: `1px solid ${active ? "#1d5536" : "#e6e3dc"}`,
                    }}
                  >
                    {t.logo && <TeamMark side={{ logo: t.logo, abbr: t.abbr ?? "", name: t.name ?? "" }} px={12} />}
                    {t.short ?? t.abbr}
                  </button>
                );
              })}
            </div>
          )}
          <Card pad={0}>
            <div style={{ padding: "4px 18px 12px" }}>
              {newsError ? (
                <Empty message="Couldn't load news." detail={newsError} />
              ) : news === null ? (
                <Empty message="Loading…" />
              ) : articles.length === 0 ? (
                <Empty message="No recent team news." />
              ) : (
                articles.slice(0, 15).map((a) => (
                  <a
                    key={a.url}
                    href={a.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="ons-row flex items-start gap-3 no-underline text-inherit cursor-pointer border-t border-border-2"
                    style={{ padding: "11px 6px", margin: "0 -6px" }}
                  >
                    {a.team_logo && (
                      <span style={{ marginTop: 2 }}>
                        <TeamMark side={{ logo: a.team_logo, abbr: a.team_abbr ?? "", name: a.team }} px={18} />
                      </span>
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="text-ink" style={{ fontSize: 13, lineHeight: 1.4 }}>{a.title}</div>
                      {a.description && (
                        <div className="text-muted mt-0.5" style={{ fontSize: 11.5, lineHeight: 1.4 }}>
                          {a.description.length > 140 ? `${a.description.slice(0, 140)}…` : a.description}
                        </div>
                      )}
                      <div className="font-mono text-faint mt-1" style={{ fontSize: 9.5 }}>
                        {a.team}
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
    </div>
  );
}
