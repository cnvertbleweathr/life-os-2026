"use client";

import { useEffect, useState } from "react";
import { cfbApi, parseSeasonRois, type CfbTeam, type CfbTeamDetail, type CfbMatchupResult, type CfbMatchupError, type CfbScheduleGame, type CfbPick } from "@/lib/api";
import {
  Card, PageHead, K, Pill, Watermark, Empty, Loading, ErrorState,
} from "@/components/ui/primitives";
import { TeamLogo } from "@/components/ui/TeamLogo";
import { Sparkline } from "@/components/ui/viz";

// ── Strength data types ───────────────────────────────────────────────────────

interface StrengthRow {
  team: string;
  season: number;
  week: number;
  off_raw: number;
  def_raw: number;
}

async function fetchStrength(season: number, teams: string[]): Promise<StrengthRow[]> {
  const params = new URLSearchParams({ season: String(season), teams: teams.join(",") });
  const base = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api";
  const res = await fetch(`${base}/cfb/strength?${params}`);
  if (!res.ok) throw new Error(`strength fetch failed: ${res.status}`);
  return res.json();
}

interface StrengthSummary {
  offPct: number | null;
  defPct: number | null;
  offScore: number | null;
  defScore: number | null;
  wkTrend: number | null;
}

const TIER_COLORS: Record<string, string> = {
  ELITE: "#1d5536", STRONG: "#2f6b43", NEUTRAL: "#736e5f", FADE: "#9a6a1e", STRONG_FADE: "#a8473a",
};

function Mono({ children, c = "#736e5f", s = 10 }: { children: React.ReactNode; c?: string; s?: number }) {
  return <span className="font-mono" style={{ fontSize: s, color: c }}>{children}</span>;
}

function Crest({ name, size = 22 }: { name: string; size?: number }) {
  return <TeamLogo team={name} px={size} />;
}

function MetricBar({ label, value, lo, hi, fmt, invert }: {
  label: string; value: number | null; lo: number; hi: number; fmt?: (v: number) => string; invert?: boolean;
}) {
  if (value == null) {
    return (
      <div className="mb-[13px]">
        <div className="flex justify-between items-baseline mb-[5px]">
          <span className="text-ink" style={{ fontSize: 12.5 }}>{label}</span>
          <Mono s={11} c="#a39d8c">no data</Mono>
        </div>
        <div className="rounded overflow-hidden" style={{ height: 5, background: "#efebe1" }} />
      </div>
    );
  }
  const pct = Math.max(0.04, Math.min(1, (value - lo) / (hi - lo)));
  const good = invert ? value <= (lo + hi) / 2 : value >= (lo + hi) / 2;
  const col = good ? "#1d5536" : "#9a6a1e";
  return (
    <div className="mb-[13px]">
      <div className="flex justify-between items-baseline mb-[5px]">
        <span className="text-ink" style={{ fontSize: 12.5 }}>{label}</span>
        <Mono s={11} c={col}>{fmt ? fmt(value) : value.toFixed(2)}</Mono>
      </div>
      <div className="rounded overflow-hidden" style={{ height: 5, background: "#efebe1" }}>
        <div className="rounded" style={{ width: `${pct * 100}%`, height: "100%", background: col, transition: "width .4s" }} />
      </div>
    </div>
  );
}

function StrengthTile({ label, value, delta, isGoodHigh = true }: {
  label: string; value: number | null; delta?: number | null; isGoodHigh?: boolean;
}) {
  const hasVal = value != null;
  const good = hasVal && (isGoodHigh ? (value as number) >= 0 : (value as number) <= 0);
  const color = !hasVal ? "#a39d8c" : good ? "#1d5536" : "#9a6a1e";
  return (
    <div style={{ background: "#faf8f4", border: "1px solid #ebe5d8", borderRadius: 8, padding: "10px 12px", marginBottom: 8 }}>
      <Mono s={8.5} c="#a39d8c">{label}</Mono>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginTop: 4 }}>
        <span className="font-mono" style={{ fontSize: 18, fontWeight: 700, color }}>
          {hasVal ? (value as number).toFixed(3) : "—"}
        </span>
        {delta != null && Math.abs(delta) > 0.001 && (
          <Mono s={9} c={delta >= 0 ? "#1d5536" : "#a8473a"}>
            {delta >= 0 ? "▲" : "▼"}{Math.abs(delta).toFixed(3)}
          </Mono>
        )}
      </div>
    </div>
  );
}

function MiniBar({ pct, color = "#1d5536" }: { pct: number; color?: string }) {
  const w = Math.max(4, Math.min(100, pct));
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
      <div style={{ width: 40, height: 4, background: "#efebe1", borderRadius: 2, overflow: "hidden", flexShrink: 0 }}>
        <div style={{ width: `${w}%`, height: "100%", background: color, borderRadius: 2 }} />
      </div>
    </div>
  );
}

function GameDrill({ g, season, onClose }: { g: CfbScheduleGame; season: number; onClose: () => void }) {
  const [rows, setRows] = useState<StrengthRow[] | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);

  useEffect(() => {
    setRows(null);
    setLoadErr(null);
    fetchStrength(season, [g.away_team, g.home_team])
      .then(setRows)
      .catch((e: Error) => setLoadErr(e.message));
  }, [g.away_team, g.home_team, season]);

  const awayRows = (rows ?? []).filter(r => r.team === g.away_team).sort((a, b) => a.week - b.week);
  const homeRows = (rows ?? []).filter(r => r.team === g.home_team).sort((a, b) => a.week - b.week);

  const awayLast  = awayRows[awayRows.length - 1] ?? null;
  const awayFirst = awayRows[0] ?? null;
  const homeLast  = homeRows[homeRows.length - 1] ?? null;
  const homeFirst = homeRows[0] ?? null;

  const allOff = (rows ?? []).map(r => r.off_raw);
  const allDef = (rows ?? []).map(r => r.def_raw);
  const pctile = (v: number | null, arr: number[]) => {
    if (v == null || arr.length === 0) return null;
    return Math.round((arr.filter(x => x <= v).length / arr.length) * 100);
  };

  const awayOffPct   = pctile(awayLast?.off_raw ?? null, allOff);
  const awayDefPct   = pctile(awayLast?.def_raw ?? null, allDef);
  const awayOffDelta = (awayLast && awayFirst) ? awayLast.off_raw - awayFirst.off_raw : null;
  const awayDefDelta = (awayLast && awayFirst) ? awayLast.def_raw - awayFirst.def_raw : null;
  const homeOffPct   = pctile(homeLast?.off_raw ?? null, allOff);
  const homeDefPct   = pctile(homeLast?.def_raw ?? null, allDef);
  const homeOffDelta = (homeLast && homeFirst) ? homeLast.off_raw - homeFirst.off_raw : null;
  const homeDefDelta = (homeLast && homeFirst) ? homeLast.def_raw - homeFirst.def_raw : null;

  const awayOff = awayRows.map(r => r.off_raw);
  const awayDef = awayRows.map(r => r.def_raw);
  const homeOff = homeRows.map(r => r.off_raw);
  const homeDef = homeRows.map(r => r.def_raw);

  const time = g.start_date
    ? new Date(g.start_date).toLocaleString("en-US", { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })
    : "TBD";

  return (
    <div style={{ background: "#ffffff", border: "1px solid #e6e3dc", borderRadius: 10, padding: "16px 18px", marginBottom: 14 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Crest name={g.away_team} size={20} />
          <span className="font-serif" style={{ fontSize: 14, fontWeight: 700 }}>{g.away_team} @ {g.home_team}</span>
          <Crest name={g.home_team} size={20} />
          {(g as any).conference_game && <Mono s={8.5} c="#a39d8c">CONF</Mono>}
          {(g as any).neutral_site && <Mono s={8.5} c="#a39d8c">NEUTRAL</Mono>}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Mono s={10} c="#a39d8c">{time}</Mono>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 16, color: "#a39d8c", lineHeight: 1, padding: "2px 4px" }}>✕</button>
        </div>
      </div>

      {loadErr ? (
        <ErrorState message={loadErr} />
      ) : !rows ? (
        <Loading label="Loading strength data…" />
      ) : (
        <>
          <div style={{ display: "flex", borderTop: "1px solid #ebe5d8", borderBottom: "1px solid #ebe5d8", paddingTop: 14, paddingBottom: 14, marginBottom: 16 }}>
            <div style={{ flex: 1, minWidth: 0, paddingRight: 14 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                <Crest name={g.away_team} size={26} />
                <div>
                  <div className="font-serif" style={{ fontSize: 14, fontWeight: 700, color: "#1a2420" }}>{g.away_team}</div>
                  <Mono s={9} c="#a39d8c">AWAY</Mono>
                </div>
              </div>
              <StrengthTile label="OFF %ILE" value={awayOffPct} isGoodHigh />
              <StrengthTile label="DEF %ILE" value={awayDefPct} isGoodHigh />
              <StrengthTile label="OFF SCORE" value={awayLast?.off_raw ?? null} delta={awayOffDelta} isGoodHigh />
              <StrengthTile label="DEF SCORE" value={awayLast?.def_raw ?? null} delta={awayDefDelta} isGoodHigh />
            </div>
            <div style={{ width: 1, background: "#ebe5d8", flexShrink: 0 }} />
            <div style={{ flex: 1, minWidth: 0, paddingLeft: 14 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                <Crest name={g.home_team} size={26} />
                <div>
                  <div className="font-serif" style={{ fontSize: 14, fontWeight: 700, color: "#1a2420" }}>{g.home_team}</div>
                  <Mono s={9} c="#a39d8c">HOME</Mono>
                </div>
              </div>
              <StrengthTile label="OFF %ILE" value={homeOffPct} isGoodHigh />
              <StrengthTile label="DEF %ILE" value={homeDefPct} isGoodHigh />
              <StrengthTile label="OFF SCORE" value={homeLast?.off_raw ?? null} delta={homeOffDelta} isGoodHigh />
              <StrengthTile label="DEF SCORE" value={homeLast?.def_raw ?? null} delta={homeDefDelta} isGoodHigh />
            </div>
          </div>

          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
              <K>Season Efficiency Trend · {season}</K>
              <div style={{ display: "flex", gap: 14 }}>
                {[{ color: "#1d5536", label: "Off PPA" }, { color: "#a8473a", label: "Def PPA" }].map(({ color, label }) => (
                  <div key={label} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <div style={{ width: 14, height: 2, background: color, borderRadius: 1 }} />
                    <Mono s={9} c="#a39d8c">{label}</Mono>
                  </div>
                ))}
              </div>
            </div>
            <div style={{ display: "flex", gap: 16 }}>
              {[
                { team: g.away_team, off: awayOff, def: awayDef },
                { team: g.home_team, off: homeOff, def: homeDef },
              ].map(({ team, off, def }) => (
                <div key={team} style={{ flex: 1, minWidth: 0 }}>
                  <Mono s={9} c="#a39d8c">{team.toUpperCase()}</Mono>
                  <div style={{ position: "relative", marginTop: 4, height: 60 }}>
                    {off.length > 0 && <Sparkline data={off} w={200} h={60} stroke="#1d5536" fill="#1d5536" sw={1.8} dot />}
                    {def.length > 0 && (
                      <div style={{ position: "absolute", top: 0, left: 0 }}>
                        <Sparkline data={def} w={200} h={60} stroke="#a8473a" fill="#a8473a" sw={1.8} dot />
                      </div>
                    )}
                    {off.length === 0 && def.length === 0 && <div style={{ paddingTop: 20 }}><Mono s={9} c="#a39d8c">no data</Mono></div>}
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", marginTop: 2 }}>
                    <Mono s={8.5} c="#a39d8c">Wk 1</Mono>
                    <Mono s={8.5} c="#a39d8c">Wk {Math.max(awayRows.length, homeRows.length)}</Mono>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ── TeamProfile — full detail panel ──────────────────────────────────────────

function TeamProfile({ team, onClose }: { team: CfbTeam; onClose: () => void }) {
  const [detail, setDetail] = useState<CfbTeamDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [strengthRows, setStrengthRows] = useState<StrengthRow[] | null>(null);

  useEffect(() => {
    setDetail(null);
    setLoadError(null);
    setStrengthRows(null);
    cfbApi.team(team.team).then(setDetail).catch((e) => setLoadError(e.message));
    const curSeason = new Date().getFullYear();
    fetchStrength(curSeason, [team.team]).then(setStrengthRows).catch(() => setStrengthRows([]));
  }, [team.team]);

  const curSeason = new Date().getFullYear();

  if (loadError) return <Card accent><ErrorState message={loadError} /></Card>;

  const seasonRois = detail?.profile?.season_rois_json
    ? parseSeasonRois(detail.profile.season_rois_json as string)
    : [];

  const allSeasonRois = (() => {
    if (!detail) return seasonRois;
    const hasCurrent = seasonRois.some(r => r.season === curSeason);
    if (hasCurrent) return seasonRois;
    return [...seasonRois, { season: curSeason, roi: null as any }];
  })();

  const maxAbsRoi = allSeasonRois.length
    ? Math.max(...allSeasonRois.map((r) => Math.abs(r.roi ?? 0)), 10)
    : 10;

  const adv = detail?.advanced_stats;

  const curRows = (strengthRows ?? []).filter(r => r.team === team.team).sort((a, b) => a.week - b.week);
  const latestStr = curRows[curRows.length - 1] ?? null;
  const offTrend = curRows.map(r => r.off_raw);
  const defTrend = curRows.map(r => r.def_raw);

  // Deduplicate recent games, limit to 10, include current season
  const recentGames = (() => {
    if (!detail) return [];
    const seen = new Set<string>();
    const unique: typeof detail.recent_games = [];
    for (const g of detail.recent_games) {
      const key = `${g.away_team}@${g.home_team}:${g.week}:${(g as any).season ?? ""}`;
      if (!seen.has(key)) { seen.add(key); unique.push(g); }
    }
    return unique.slice(0, 10);
  })();

  return (
    <Card accent style={{ position: "relative", overflow: "hidden" }}>
      <Watermark size={210} opacity={0.04} />
      <div className="relative">
        <div className="flex items-center gap-[13px] mb-4">
          <Crest name={team.team} size={42} />
          <div className="flex-1 min-w-0">
            <div className="font-serif font-bold text-ink leading-tight" style={{ fontSize: 23 }}>{team.team}</div>
            <div className="flex items-center gap-2 mt-1">
              {team.seasons_profitable >= 3 && <Mono s={9.5} c="#1d5536">● CONSISTENTLY PROFITABLE</Mono>}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ background: "none", border: "none", cursor: "pointer", fontSize: 18, color: "#a39d8c", lineHeight: 1, padding: "4px 6px", alignSelf: "flex-start" }}
          >
            ✕
          </button>
        </div>

        <div className="grid grid-cols-4 border-t border-b border-border-2 mb-[18px]">
          {[
            ["WIN RATE", `${team.win_rate.toFixed(1)}%`, team.win_rate >= 55],
            ["ROI", `${team.roi_pct >= 0 ? "+" : ""}${team.roi_pct.toFixed(1)}%`, team.roi_pct >= 0],
            ["PROFIT YRS", `${team.seasons_profitable}/4`, team.seasons_profitable >= 3],
            ["GAMES", String(team.total_bets), false],
          ].map(([l, v, hot], i) => (
            <div key={i} style={{ padding: "12px 0", borderLeft: i ? "1px solid #ebe5d8" : "none", paddingLeft: i ? 14 : 0 }}>
              <Mono s={8.5} c="#a39d8c">{l as string}</Mono>
              <div className="font-serif font-bold mt-1" style={{ fontSize: 20, color: hot ? "#1d5536" : "#232a22" }}>{v as string}</div>
            </div>
          ))}
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
          <K>{curSeason} Season Efficiency</K>
          <span className="font-mono text-faint" style={{ fontSize: 8.5 }}>CFBD PPA · current season</span>
        </div>
        {strengthRows === null ? (
          <div style={{ padding: "16px 0" }}><Loading label="Loading current season data…" /></div>
        ) : curRows.length === 0 ? (
          <Empty message={`No ${curSeason} season strength data yet.`} />
        ) : (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 14 }}>
              {[
                { label: `Off PPA · Wk ${latestStr?.week ?? "—"}`, value: latestStr?.off_raw ?? null },
                { label: `Def PPA · Wk ${latestStr?.week ?? "—"}`, value: latestStr?.def_raw ?? null },
              ].map(({ label, value }) => {
                const isGood = value != null && value >= 0;
                const color = value == null ? "#a39d8c" : isGood ? "#1d5536" : "#9a6a1e";
                return (
                  <div key={label} style={{ background: "#faf8f4", border: "1px solid #ebe5d8", borderRadius: 7, padding: "9px 11px" }}>
                    <Mono s={8.5} c="#a39d8c">{label}</Mono>
                    <div className="font-mono" style={{ fontSize: 16, fontWeight: 700, marginTop: 4, color }}>
                      {value != null ? (value >= 0 ? "+" : "") + value.toFixed(3) : "—"}
                    </div>
                  </div>
                );
              })}
            </div>
            <div style={{ marginBottom: 18 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <Mono s={8.5} c="#a39d8c">SEASON TREND</Mono>
                <div style={{ display: "flex", gap: 12 }}>
                  {[{ color: "#1d5536", label: "Offense" }, { color: "#a8473a", label: "Defense" }].map(({ color, label }) => (
                    <div key={label} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                      <div style={{ width: 12, height: 2, background: color, borderRadius: 1 }} />
                      <Mono s={8.5} c="#a39d8c">{label}</Mono>
                    </div>
                  ))}
                </div>
              </div>
              <div style={{ position: "relative", height: 52 }}>
                {offTrend.length > 0 && <Sparkline data={offTrend} w={280} h={52} stroke="#1d5536" fill="#1d5536" sw={1.8} dot />}
                {defTrend.length > 0 && (
                  <div style={{ position: "absolute", top: 0, left: 0 }}>
                    <Sparkline data={defTrend} w={280} h={52} stroke="#a8473a" fill="#a8473a" sw={1.8} dot />
                  </div>
                )}
              </div>
            </div>
          </>
        )}

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
          <K>Prior-Season Efficiency</K>
          <span className="font-mono text-faint" style={{ fontSize: 8.5 }}>cfbd.advanced_stats · {curSeason - 1}</span>
        </div>
        {!detail ? (
          <div style={{ padding: "16px 0" }}><Loading label="Loading team detail…" /></div>
        ) : !adv ? (
          <Empty message="No advanced stats found for prior season." />
        ) : (
          <>
            <MetricBar label="Offensive PPA" value={adv.off_ppa} lo={-0.1} hi={0.5} fmt={(v) => (v >= 0 ? "+" : "") + v.toFixed(3)} />
            <MetricBar label="Defensive PPA (lower is better)" value={adv.def_ppa} lo={-0.1} hi={0.5} invert fmt={(v) => (v >= 0 ? "+" : "") + v.toFixed(3)} />
            <MetricBar label="Offensive success rate" value={adv.off_success_rate} lo={0.3} hi={0.55} fmt={(v) => (v * 100).toFixed(1) + "%"} />
            <MetricBar label="Def success rate (lower better)" value={adv.def_success_rate} lo={0.3} hi={0.55} invert fmt={(v) => (v * 100).toFixed(1) + "%"} />
            <MetricBar label="Defensive havoc rate" value={adv.def_havoc_total} lo={0.1} hi={0.25} fmt={(v) => (v * 100).toFixed(1) + "%"} />
            <MetricBar label="Rush offense PPA" value={adv.off_rush_ppa} lo={-0.1} hi={0.3} fmt={(v) => (v >= 0 ? "+" : "") + v.toFixed(3)} />
          </>
        )}

        <K style={{ margin: "18px 0 10px" }}>Backtested ROI by season</K>
        {!detail ? (
          <div className="py-2" />
        ) : allSeasonRois.length === 0 ? (
          <Empty message="No season-by-season ROI breakdown available." />
        ) : (
          <div className="flex items-end gap-[10px]" style={{ height: 56 }}>
            {allSeasonRois.map((r) => {
              const roi = r.roi;
              const h = roi != null ? (Math.abs(roi) / maxAbsRoi) * 46 : 0;
              const pos = roi != null && roi >= 0;
              const isCurrent = r.season === curSeason;
              return (
                <div key={r.season} className="flex-1 flex flex-col items-center justify-end" style={{ height: "100%" }}>
                  <Mono s={8.5} c={roi == null ? "#a39d8c" : pos ? "#1d5536" : "#a8473a"}>
                    {roi == null ? (isCurrent ? "YTD" : "—") : `${pos ? "+" : ""}${roi.toFixed(1)}`}
                  </Mono>
                  <div
                    className="w-full rounded-sm mt-[3px]"
                    style={{
                      height: Math.max(3, h),
                      background: roi == null ? "#e6e3dc" : pos ? "#1d5536" : "#a8473a",
                      opacity: isCurrent ? 0.6 : 0.85,
                      border: isCurrent ? "1px dashed #a39d8c" : "none",
                    }}
                  />
                  <Mono s={8.5} c={isCurrent ? "#1d5536" : "#a39d8c"}>'{String(r.season).slice(2)}</Mono>
                </div>
              );
            })}
          </div>
        )}

        <K style={{ margin: "18px 0 10px" }}>Recent Games · last 10</K>
        {!detail ? (
          <div className="py-2" />
        ) : recentGames.length === 0 ? (
          <Empty message="No recent game context found." />
        ) : (
          <div className="flex flex-col gap-2">
            {recentGames.map((g, i) => (
              <div key={i} className="flex items-center justify-between" style={{ fontSize: 11.5 }}>
                <span className="text-muted">
                  {g.away_team} @ {g.home_team} · Wk {g.week}{(g as any).season ? ` · ${(g as any).season}` : ""}
                </span>
                <span className="font-mono" style={{ fontSize: 10, color: g.spread_result === "covered" ? "#1d5536" : g.spread_result === "missed" ? "#a8473a" : "#a39d8c" }}>
                  {g.spread != null ? (g.spread > 0 ? `+${g.spread}` : g.spread) : "—"} · {g.spread_result ?? "—"}
                </span>
              </div>
            ))}
          </div>
        )}

        <div className="mt-4">
          <Mono s={8.5} c="#a39d8c">WALK-FORWARD · NO LOOKAHEAD · cfbd.team_profiles + cfbd.advanced_stats</Mono>
        </div>
      </div>
    </Card>
  );
}

// ── TeamsView ──────────────────────────────────────────────────────────────────

type TeamSort = "roi" | "win" | "off_pct" | "def_pct" | "off_score" | "def_score" | "wk_trend";

function TeamsView({ teams }: { teams: CfbTeam[] }) {
  const [sort, setSort] = useState<TeamSort>("roi");
  const [selName, setSelName] = useState<string | null>(null);
  const [strengthMap, setStrengthMap] = useState<Map<string, StrengthSummary>>(new Map());
  const [strengthLoading, setStrengthLoading] = useState(false);
  const [strengthLoaded, setStrengthLoaded] = useState(false);

  const curSeason = new Date().getFullYear();
  const needsStrength = ["off_pct", "def_pct", "off_score", "def_score", "wk_trend"].includes(sort);

  useEffect(() => {
    if (strengthLoaded || strengthLoading) return;
    if (!needsStrength) return;

    setStrengthLoading(true);
    const allTeams = teams.map(t => t.team);
    const CHUNK = 10;
    const chunks: string[][] = [];
    for (let i = 0; i < allTeams.length; i += CHUNK) chunks.push(allTeams.slice(i, i + CHUNK));

    Promise.all(chunks.map(ch => fetchStrength(curSeason, ch).catch(() => [] as StrengthRow[])))
      .then(results => {
        const all: StrengthRow[] = results.flat();
        const allOff = all.map(r => r.off_raw);
        const allDef = all.map(r => r.def_raw);
        const pctile = (v: number, arr: number[]) =>
          arr.length === 0 ? null : Math.round((arr.filter(x => x <= v).length / arr.length) * 100);

        const map = new Map<string, StrengthSummary>();
        for (const team of allTeams) {
          const rows = all.filter(r => r.team === team).sort((a, b) => a.week - b.week);
          const last = rows[rows.length - 1] ?? null;
          const prev = rows.length >= 2 ? rows[rows.length - 2] : null;
          map.set(team, {
            offPct:   last ? pctile(last.off_raw, allOff) : null,
            defPct:   last ? pctile(last.def_raw, allDef) : null,
            offScore: last?.off_raw ?? null,
            defScore: last?.def_raw ?? null,
            wkTrend:  (last && prev) ? last.off_raw - prev.off_raw : null,
          });
        }
        setStrengthMap(map);
        setStrengthLoaded(true);
      })
      .finally(() => setStrengthLoading(false));
  }, [sort, strengthLoaded, strengthLoading, teams, curSeason, needsStrength]);

  const getStr = (team: string): StrengthSummary =>
    strengthMap.get(team) ?? { offPct: null, defPct: null, offScore: null, defScore: null, wkTrend: null };

  const sorted = [...teams].sort((a, b) => {
    switch (sort) {
      case "roi":       return b.roi_pct - a.roi_pct;
      case "win":       return b.win_rate - a.win_rate;
      case "off_pct":   return (getStr(b.team).offPct ?? -1) - (getStr(a.team).offPct ?? -1);
      case "def_pct":   return (getStr(b.team).defPct ?? -1) - (getStr(a.team).defPct ?? -1);
      case "off_score": return (getStr(b.team).offScore ?? -999) - (getStr(a.team).offScore ?? -999);
      case "def_score": return (getStr(b.team).defScore ?? -999) - (getStr(a.team).defScore ?? -999);
      case "wk_trend":  return (getStr(b.team).wkTrend ?? -999) - (getStr(a.team).wkTrend ?? -999);
      default:          return 0;
    }
  });

  const sel = selName ? teams.find(t => t.team === selName) ?? null : null;

  const SORT_OPTS: [TeamSort, string][] = [
    ["roi",       "ROI %"],
    ["win",       "Win %"],
    ["off_pct",   "OFF %ILE"],
    ["def_pct",   "DEF %ILE"],
    ["off_score", "OFF Score"],
    ["def_score", "DEF Score"],
    ["wk_trend",  "Wk Trend"],
  ];

  return (
    <div className="grid gap-[22px] items-start" style={{ gridTemplateColumns: sel ? "1.3fr 1fr" : "1fr" }}>
      <Card pad={0}>
        <div style={{ padding: "16px 18px 10px" }}>
          <div className="flex justify-between items-center flex-wrap gap-2 mb-3">
            <K>Team Performance · {teams.length} profiled</K>
            {needsStrength && strengthLoading && <Mono s={9} c="#a39d8c">Loading efficiency data…</Mono>}
          </div>
          <div className="flex gap-[5px] flex-wrap">
            {SORT_OPTS.map(([k, l]) => (
              <Pill key={k} active={sort === k} onClick={() => setSort(k as TeamSort)}>{l}</Pill>
            ))}
          </div>
        </div>

        {/* Column headers */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "20px 24px 1fr 56px 50px 52px 52px 68px",
          gap: 6,
          padding: "6px 26px 6px 18px",
          borderTop: "1px solid #ebe5d8",
          borderBottom: "2px solid #ebe5d8",
        }}>
          <span />
          <span />
          <Mono s={8} c="#a39d8c">TEAM</Mono>
          <div style={{ textAlign: "right" }}><Mono s={8} c={sort === "roi" ? "#1d5536" : "#a39d8c"}>ROI%</Mono></div>
          <div style={{ textAlign: "right" }}><Mono s={8} c={sort === "win" ? "#1d5536" : "#a39d8c"}>WIN%</Mono></div>
          <div style={{ textAlign: "right" }}><Mono s={8} c={["off_pct","off_score"].includes(sort) ? "#1d5536" : "#a39d8c"}>OFF</Mono></div>
          <div style={{ textAlign: "right" }}><Mono s={8} c={["def_pct","def_score"].includes(sort) ? "#1d5536" : "#a39d8c"}>DEF</Mono></div>
          <div style={{ textAlign: "right" }}><Mono s={8} c={sort === "wk_trend" ? "#1d5536" : "#a39d8c"}>WK TREND</Mono></div>
        </div>

        <div style={{ padding: "0 18px 14px", maxHeight: 680, overflowY: "auto" }}>
          {sorted.map((t, i) => {
            const on = t.team === selName;
            const str = getStr(t.team);
            const wkTrend = str.wkTrend;
            return (
              <button
                key={t.team}
                onClick={() => setSelName(prev => prev === t.team ? null : t.team)}
                style={{
                  display: "grid",
                  alignItems: "center",
                  gridTemplateColumns: "20px 24px 1fr 56px 50px 52px 52px 68px",
                  gap: 6,
                  width: "100%", textAlign: "left",
                  padding: "8px 8px", margin: "0 -8px",
                  borderRadius: 6,
                  background: on ? "#e9efe7" : "transparent",
                  boxShadow: on ? "inset 2px 0 0 #1d5536" : "none",
                  borderTop: "1px solid #ebe5d8",
                  border: "none", cursor: "pointer",
                }}
              >
                <span className="font-mono text-faint" style={{ fontSize: 9 }}>{i + 1}</span>
                <Crest name={t.team} size={20} />
                <span style={{ fontSize: 13, fontWeight: on ? 600 : 400, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.team}</span>

                {/* ROI% */}
                <div style={{ textAlign: "right" }}>
                  <span className="font-mono font-semibold" style={{ fontSize: 11, color: t.roi_pct >= 0 ? "#1d5536" : "#a8473a" }}>
                    {t.roi_pct >= 0 ? "+" : ""}{t.roi_pct.toFixed(1)}%
                  </span>
                </div>

                {/* Win% */}
                <div style={{ textAlign: "right" }}>
                  <span className="font-mono text-muted" style={{ fontSize: 11 }}>{t.win_rate.toFixed(0)}%</span>
                </div>

                {/* OFF %ILE + bar */}
                <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
                  {str.offPct != null ? (
                    <>
                      <span className="font-mono" style={{ fontSize: 10, color: str.offPct >= 50 ? "#1d5536" : "#9a6a1e" }}>{str.offPct}</span>
                      <MiniBar pct={str.offPct} color={str.offPct >= 50 ? "#1d5536" : "#9a6a1e"} />
                    </>
                  ) : <span className="font-mono" style={{ fontSize: 10, color: "#d4cfc5" }}>—</span>}
                </div>

                {/* DEF %ILE + bar */}
                <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
                  {str.defPct != null ? (
                    <>
                      <span className="font-mono" style={{ fontSize: 10, color: str.defPct >= 50 ? "#1d5536" : "#9a6a1e" }}>{str.defPct}</span>
                      <MiniBar pct={str.defPct} color={str.defPct >= 50 ? "#1d5536" : "#9a6a1e"} />
                    </>
                  ) : <span className="font-mono" style={{ fontSize: 10, color: "#d4cfc5" }}>—</span>}
                </div>

                {/* WK TREND */}
                <div style={{ textAlign: "right" }}>
                  {wkTrend != null ? (
                    <span className="font-mono" style={{ fontSize: 10, color: wkTrend >= 0 ? "#1d5536" : "#a8473a" }}>
                      {wkTrend >= 0 ? "▲" : "▼"}{Math.abs(wkTrend).toFixed(3)}
                    </span>
                  ) : <span className="font-mono" style={{ fontSize: 10, color: "#d4cfc5" }}>—</span>}
                </div>
              </button>
            );
          })}
        </div>
      </Card>

      {sel && (
        <div style={{ position: "sticky", top: 0 }}>
          <TeamProfile team={sel} onClose={() => setSelName(null)} />
        </div>
      )}
    </div>
  );
}

// ── Matchup Lab support components ────────────────────────────────────────────

function EdgeList({ items, color, label }: { items: string[]; color: string; label: string }) {
  if (items.length === 0) return null;
  return (
    <div className="mb-3">
      <Mono s={9} c={color}>{label}</Mono>
      <div className="flex flex-col gap-1 mt-1.5">
        {items.map((e, i) => (
          <div key={i} className="flex items-baseline gap-2">
            <span style={{ color, fontSize: 10 }}>●</span>
            <span style={{ fontSize: 12.5 }}>{e}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function MatchupResultCard({ result }: { result: CfbMatchupResult }) {
  const scoreColor = result.meets_publish_bar ? "#1d5536" : result.model_score > 0 ? "#9a6a1e" : "#a39d8c";
  return (
    <Card accent={result.meets_publish_bar} style={{ position: "relative", overflow: "hidden" }}>
      {result.meets_publish_bar && <Watermark size={180} opacity={0.04} />}
      <div className="relative">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <Crest name={result.matchup.split(" @ ")[0]} size={28} />
            <span className="font-serif font-bold" style={{ fontSize: 17 }}>{result.matchup}</span>
            <Crest name={result.matchup.split(" @ ")[1]} size={28} />
          </div>
          <span className="font-mono rounded-full" style={{ fontSize: 9, letterSpacing: "0.5px", textTransform: "uppercase", padding: "3px 10px", background: result.meets_publish_bar ? "#1d5536" : "#efebe1", color: result.meets_publish_bar ? "#fff" : "#736e5f" }}>
            {result.meets_publish_bar ? "would publish" : "below publish bar"}
          </span>
        </div>
        <div className="flex items-baseline gap-4 mb-4">
          <div>
            <Mono s={9}>MODEL SCORE</Mono>
            <div className="font-serif font-bold leading-none mt-1" style={{ fontSize: 34, color: scoreColor }}>{result.model_score}</div>
          </div>
          <div>
            <Mono s={9}>SUGGESTED BET</Mono>
            <div className="font-serif font-semibold mt-1" style={{ fontSize: 16 }}>{result.bet}</div>
          </div>
        </div>
        <div className="grid grid-cols-4 border-t border-b border-border-2 mb-4">
          {[
            ["PPA GAP",     result.ppa_gap     != null ? `${result.ppa_gap >= 0 ? "+" : ""}${result.ppa_gap.toFixed(3)}` : "—"],
            ["SP+ GAP",     result.sp_gap      != null ? `${result.sp_gap >= 0 ? "+" : ""}${result.sp_gap.toFixed(1)}` : "—"],
            ["RET GAP",     result.ret_gap     != null ? `${result.ret_gap >= 0 ? "+" : ""}${result.ret_gap.toFixed(3)}` : "—"],
            ["RECRUIT GAP", result.recruiting_gap != null ? `${result.recruiting_gap >= 0 ? "+" : ""}${result.recruiting_gap.toFixed(1)}` : "—"],
          ].map(([l, v], i) => (
            <div key={i} style={{ padding: "10px 0", borderLeft: i ? "1px solid #ebe5d8" : "none", paddingLeft: i ? 12 : 0 }}>
              <Mono s={8.5} c="#a39d8c">{l}</Mono>
              <div className="font-mono font-semibold mt-1" style={{ fontSize: 14 }}>{v}</div>
            </div>
          ))}
        </div>
        <EdgeList items={result.edges} color="#1d5536" label={`SIGNALS (${result.n_edges})`} />
        <EdgeList items={result.warnings} color="#9a6a1e" label="WARNINGS" />
        {result.edges.length === 0 && result.warnings.length === 0 && <Empty message="No qualifying signals for this matchup." />}
        {(result.home_coach || result.away_coach) && (
          <div className="mt-4 pt-4 border-t border-border-2">
            <Mono s={9} c="#a39d8c">COACHES</Mono>
            <div className="flex justify-between items-baseline mt-1.5" style={{ fontSize: 12.5 }}>
              <span>{result.home_coach ?? "—"} vs {result.away_coach ?? "—"}</span>
              {result.coach_h2h && <Mono s={10.5} c="#736e5f">H2H {result.coach_h2h.home_record}-{result.coach_h2h.away_record} ({result.coach_h2h.total} gm)</Mono>}
            </div>
          </div>
        )}
        <div className="mt-4"><Mono s={8.5} c="#a39d8c">score_game() · prior season {result.season - 1} · NOT a probability — ordinal ranking only</Mono></div>
      </div>
    </Card>
  );
}

function MatchupLab({ teams }: { teams: CfbTeam[] }) {
  const names = teams.map((t) => t.team).sort();
  const [home, setHome] = useState(names[0] ?? "");
  const [away, setAway] = useState(names[1] ?? "");
  const [spread, setSpread] = useState("-3.5");
  const [overUnder, setOverUnder] = useState("51.5");
  const [season, setSeason] = useState(String(new Date().getFullYear()));
  const [result, setResult] = useState<CfbMatchupResult | CfbMatchupError | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setLoading(true); setError(null); setResult(null);
    try {
      const r = await cfbApi.matchupLab({ home_team: home, away_team: away, spread: parseFloat(spread), over_under: overUnder ? parseFloat(overUnder) : undefined, season: season ? parseInt(season, 10) : undefined });
      setResult(r);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  return (
    <div className="grid gap-[22px]" style={{ gridTemplateColumns: "1fr 1.3fr" }}>
      <Card style={{ maxWidth: 420 }}>
        <K style={{ marginBottom: 14 }}>Matchup Simulator</K>
        <div className="flex flex-col gap-3">
          {[["HOME TEAM", home, setHome], ["AWAY TEAM", away, setAway]].map(([lbl, val, setter]) => (
            <div key={lbl as string}>
              <Mono s={9} c="#a39d8c">{lbl as string}</Mono>
              <select value={val as string} onChange={(e) => (setter as any)(e.target.value)} style={{ width: "100%", marginTop: 4, padding: "7px 9px", borderRadius: 6, border: "1px solid #e6e3dc", fontSize: 13 }}>
                {names.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
          ))}
          <div className="flex gap-3">
            <div className="flex-1">
              <Mono s={9} c="#a39d8c">SPREAD (NEG = HOME FAV)</Mono>
              <input value={spread} onChange={(e) => setSpread(e.target.value)} style={{ width: "100%", marginTop: 4, padding: "7px 9px", borderRadius: 6, border: "1px solid #e6e3dc", fontSize: 13 }} />
            </div>
            <div className="flex-1">
              <Mono s={9} c="#a39d8c">OVER/UNDER</Mono>
              <input value={overUnder} onChange={(e) => setOverUnder(e.target.value)} style={{ width: "100%", marginTop: 4, padding: "7px 9px", borderRadius: 6, border: "1px solid #e6e3dc", fontSize: 13 }} />
            </div>
          </div>
          <div>
            <Mono s={9} c="#a39d8c">SEASON</Mono>
            <input value={season} onChange={(e) => setSeason(e.target.value)} style={{ width: "100%", marginTop: 4, padding: "7px 9px", borderRadius: 6, border: "1px solid #e6e3dc", fontSize: 13 }} />
            <p className="text-faint mt-1.5 mb-0" style={{ fontSize: 10.5, lineHeight: 1.4 }}>Model uses prior-season stats (season − 1) — walk-forward, no lookahead.</p>
          </div>
          <button onClick={run} disabled={loading || !home || !away} style={{ marginTop: 4, padding: "10px 0", borderRadius: 8, border: "none", background: loading ? "#a39d8c" : "#1d5536", color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
            {loading ? "Scoring…" : "Run Model"}
          </button>
        </div>
      </Card>
      <div>
        {error && <ErrorState message={error} />}
        {!error && !result && <Card><Empty message="Pick two teams and run the model." detail="Calls the real score_game() walk-forward model directly." /></Card>}
        {result && "error" in result && (
          <Card accent>
            <K color="#a8473a" style={{ marginBottom: 8 }}>{result.error === "no_advanced_stats" ? "No data for this matchup" : "Request failed"}</K>
            <p style={{ fontSize: 13, lineHeight: 1.5 }}>{result.message}</p>
          </Card>
        )}
        {result && !("error" in result) && <MatchupResultCard result={result} />}
      </div>
    </div>
  );
}

// ── This Week: picks-only with inline GameDrill ───────────────────────────────

function PickCardDrillable({ p, isOfficial = true, season }: { p: CfbPick; isOfficial?: boolean; season: number }) {
  const [expanded, setExpanded] = useState(false);
  const isTierRisk = p.bet_type === "FADE_TIER_RISK";
  const accentColor = !isOfficial ? "#a39d8c" : isTierRisk ? "#9a6a1e" : "#1d5536";
  const [awayName, homeName] = p.matchup.split(" @ ");

  const fakeGame: CfbScheduleGame = {
    game_id: 0,
    season,
    week: p.week ?? 1,
    away_team: awayName,
    home_team: homeName,
    start_date: null,
  } as any;

  const WARNING_LABELS: Record<string, string> = {
    "ret_low_home": "Low returning production for home team",
    "ret_low_away": "Low returning production for away team",
    "coach_change": "Head coach change this offseason",
    "coach_change+low_ret": "Coach change + low returning production",
    "SP+_disagrees": "SP+ rating disagrees with this bet",
    "tier_FADE": "Bet team has a FADE historical tier",
    "tier_STRONG_FADE": "Bet team has a STRONG FADE historical tier",
    "home_havoc_vs_bet": "Home defense havoc rate works against this bet",
    "away_havoc_vs_bet": "Away defense havoc rate works against this bet",
  };

  return (
    <div>
      <Card accent={isOfficial} accentColor={accentColor} style={{ position: "relative", overflow: "hidden", opacity: isOfficial ? 1 : 0.82, background: isOfficial ? undefined : "#faf8f4" }}>
        <button
          onClick={() => setExpanded(prev => !prev)}
          style={{ display: "block", width: "100%", background: "none", border: "none", cursor: "pointer", textAlign: "left", padding: 0 }}
        >
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2 min-w-0">
              <Crest name={awayName} size={20} />
              <span className="truncate font-serif font-bold" style={{ fontSize: 15 }}>{p.matchup}</span>
              <Crest name={homeName} size={20} />
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {!isOfficial && (
                <span style={{ fontSize: 9, fontFamily: "monospace", textTransform: "uppercase", letterSpacing: "0.06em", color: "#a39d8c", border: "1px solid #d4cfc5", borderRadius: 3, padding: "1px 5px" }}>watch</span>
              )}
              <span className="font-mono" style={{ fontSize: 13, color: accentColor }}>{p.stars} Model: {p.model_score}</span>
              <span style={{ fontSize: 14, color: expanded ? accentColor : "#c4bfb5" }}>{expanded ? "▾" : "▸"}</span>
            </div>
          </div>
          <div className="flex items-baseline justify-between mb-2 flex-wrap gap-1">
            <span style={{ fontSize: 14, fontWeight: 600 }}>{p.bet}</span>
            <Mono s={10.5}>{p.line}{p.ou && p.ou !== "N/A" ? ` · O/U ${p.ou}` : ""}</Mono>
          </div>
        </button>

        {isTierRisk && <Mono s={9} c={accentColor}>⚠ Bet is on a team with a STRONG_FADE historical tier in this situation</Mono>}
        <p className="text-muted" style={{ fontSize: 12, lineHeight: 1.5, margin: "8px 0 0" }}>{p.edge}</p>

        {p.warnings.length > 0 && (
          <div className="flex flex-col gap-1 mt-2">
            {p.warnings.map((w, i) => <Mono key={i} s={10} c="#9a6a1e">⚠️ {WARNING_LABELS[w] ?? w}</Mono>)}
          </div>
        )}

        {!expanded && (
          <div style={{ marginTop: 10, paddingTop: 8, borderTop: "1px solid #ebe5d8" }}>
            <Mono s={8.5} c="#c4bfb5">▸ CLICK TO SEE STRENGTH COMPARISON</Mono>
          </div>
        )}
      </Card>

      {expanded && (
        <div style={{ marginTop: -6 }}>
          <GameDrill g={fakeGame} season={season} onClose={() => setExpanded(false)} />
        </div>
      )}
    </div>
  );
}

function SlateView() {
  const now = new Date();
  const [season] = useState(now.getFullYear());
  const [picks, setPicks] = useState<CfbPick[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    cfbApi.picks().then(setPicks).catch((e) => setError(e.message));
  }, []);

  const picksWeek = picks?.[0]?.week;
  const picksSeason = picks?.[0]?.season;

  if (error) return <ErrorState message={error} />;
  if (!picks) return <Loading label="Loading picks…" />;
  if (picks.length === 0) return (
    <Card>
      <Empty
        message="No qualifying picks yet."
        detail="Either lines haven't posted for this week, or nothing clears the model's publish threshold — that's the model correctly saying 'no strong signal,' not missing data."
      />
    </Card>
  );

  const official  = picks.filter(p => p.meets_publish_bar);
  const watchlist = picks.filter(p => !p.meets_publish_bar);

  const Divider = ({ label }: { label: string }) => (
    <div style={{ display: "flex", alignItems: "center", gap: 8, margin: "12px 0 6px" }}>
      <div style={{ flex: 1, height: 1, background: "#e5e0d4" }} />
      <span style={{ fontSize: 9, fontFamily: "monospace", textTransform: "uppercase", letterSpacing: "0.08em", color: "#a39d8c" }}>{label}</span>
      <div style={{ flex: 1, height: 1, background: "#e5e0d4" }} />
    </div>
  );

  return (
    <div style={{ maxWidth: 760, margin: "0 auto" }}>
      <div className="flex justify-between items-center mb-4">
        <K color="#1d5536">{picksSeason ?? season} Week {picksWeek} · model v3 walk-forward</K>
        <Mono s={9} c="#a39d8c">CLICK ANY PICK TO SEE STRENGTH COMPARISON</Mono>
      </div>

      {official.length > 0 && (
        <>
          <Divider label={`Official Picks (${official.length})`} />
          <div className="flex flex-col gap-3">
            {official.map((p, i) => <PickCardDrillable key={`off-${i}`} p={p} isOfficial={true} season={picksSeason ?? season} />)}
          </div>
        </>
      )}

      {watchlist.length > 0 && (
        <>
          <Divider label={`Watch List · Below Publish Bar (${watchlist.length})`} />
          <div className="flex flex-col gap-3">
            {watchlist.map((p, i) => <PickCardDrillable key={`watch-${i}`} p={p} isOfficial={false} season={picksSeason ?? season} />)}
          </div>
        </>
      )}
    </div>
  );
}

// ── Page root ─────────────────────────────────────────────────────────────────

export default function CfbPage() {
  const [teams, setTeams] = useState<CfbTeam[] | null>(null);
  const [tab, setTab] = useState<"slate" | "lab" | "teams">("slate");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    cfbApi.teams().then(setTeams).catch((e) => setError(e.message));
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!teams) return <Loading />;

  const TABS: Array<[string, string]> = [
    ["slate", "This Week"],
    ["lab",   "Matchup Lab"],
    ["teams", "Teams"],
  ];

  return (
    <div style={{ padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" }}>
      <PageHead
        title="CFB Betting"
        kicker="The Degenerates' Corner · walk-forward validated"
        right={
          <div className="flex gap-1 rounded-full" style={{ background: "#fbfaf5", border: "1px solid #e6e3dc", padding: 4 }}>
            {TABS.map(([k, l]) => (
              <button
                key={k}
                onClick={() => setTab(k as any)}
                style={{ fontSize: 12, fontWeight: 500, padding: "7px 15px", background: tab === k ? "#1d5536" : "transparent", color: tab === k ? "#fff" : "#736e5f", border: "none", cursor: "pointer", borderRadius: "9999px" }}
              >
                {l}
              </button>
            ))}
          </div>
        }
      />

      {tab === "slate" && <SlateView />}
      {tab === "lab"   && <MatchupLab teams={teams} />}
      {tab === "teams" && <TeamsView teams={teams} />}
    </div>
  );
}
