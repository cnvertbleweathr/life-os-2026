"use client";

import { useEffect, useState } from "react";
import {
  cfbApi, parseSeasonRois,
  type CfbTeam, type CfbTeamDetail, type CfbMatchupResult, type CfbMatchupError,
  type CfbPick, type CfbTeamTrend, type CfbTrendGame, type CfbWeeks,
} from "@/lib/api";
import {
  Card, PageHead, K, Pill, Watermark, Empty, Loading, ErrorState,
} from "@/components/ui/primitives";
import { TeamLogo } from "@/components/ui/TeamLogo";

// ── Palette ───────────────────────────────────────────────────────────────────

const GOOD = "#1d5536";
const WARN = "#9a6a1e";
const BAD = "#a8473a";
const FAINT = "#a39d8c";
const EMPTY = "#d4cfc5";
const OFF_COLOR = "#1d5536";
const DEF_COLOR = "#a8473a";

function Mono({ children, c = "#736e5f", s = 10 }: { children: React.ReactNode; c?: string; s?: number }) {
  return <span className="font-mono" style={{ fontSize: s, color: c }}>{children}</span>;
}

function Crest({ name, size = 22 }: { name: string; size?: number }) {
  return <TeamLogo team={name} px={size} />;
}

const signed = (v: number, d = 3) => `${v >= 0 ? "+" : ""}${v.toFixed(d)}`;

/** ▲/▼ trend value. All trends from /cfb/team-trends are signed so
 *  positive = improving, regardless of offense/defense/points. */
function TrendValue({ v, d = 3, s = 10, unit = "" }: { v: number | null | undefined; d?: number; s?: number; unit?: string }) {
  if (v == null) return <span className="font-mono" style={{ fontSize: s, color: EMPTY }}>—</span>;
  const flat = Math.abs(v) < Math.pow(10, -d) / 2;
  const color = flat ? FAINT : v > 0 ? GOOD : BAD;
  return (
    <span className="font-mono" style={{ fontSize: s, color }}>
      {flat ? "•" : v > 0 ? "▲" : "▼"}{Math.abs(v).toFixed(d)}{unit}
    </span>
  );
}

// ── Team-trends cache (one fetch per season/week cut) ─────────────────────────

const trendCache = new Map<string, Promise<Map<string, CfbTeamTrend>>>();

function loadTrends(season: number, throughWeek?: number): Promise<Map<string, CfbTeamTrend>> {
  const key = `${season}:${throughWeek ?? "all"}`;
  let p = trendCache.get(key);
  if (!p) {
    p = cfbApi.teamTrends(season, { throughWeek })
      .then(rows => new Map(rows.map(r => [r.team, r])))
      .catch(e => { trendCache.delete(key); throw e; });
    trendCache.set(key, p);
  }
  return p;
}

// ── Season trend chart: off & def PPA on ONE shared scale ─────────────────────

function TrendChart({ games, w = 300, h = 70 }: { games: CfbTrendGame[]; w?: number; h?: number }) {
  const off = games.map(g => g.off_ppa);
  const def = games.map(g => g.def_ppa);
  const vals = [...off, ...def].filter((v): v is number => v != null);
  if (vals.length === 0) return <Mono s={9} c={FAINT}>no games yet</Mono>;

  const padL = 4, padR = 4, padT = 6, padB = 6;
  const hi = Math.max(...vals, 0.1);
  const lo = Math.min(...vals, -0.1);
  const n = games.length;
  const x = (i: number) => padL + (n === 1 ? (w - padL - padR) / 2 : (i * (w - padL - padR)) / (n - 1));
  const y = (v: number) => padT + ((hi - v) / (hi - lo)) * (h - padT - padB);
  const path = (series: (number | null)[]) =>
    series.map((v, i) => (v == null ? null : `${x(i).toFixed(1)} ${y(v).toFixed(1)}`))
      .filter(Boolean).map((p, i) => (i ? "L" : "M") + p).join(" ");

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ display: "block", height: h }}>
        <line x1={0} x2={w} y1={y(0)} y2={y(0)} stroke="#d9d3c5" strokeDasharray="3 3" strokeWidth={1} vectorEffect="non-scaling-stroke" />
        <path d={path(def)} fill="none" stroke={DEF_COLOR} strokeWidth={1.8} vectorEffect="non-scaling-stroke" />
        <path d={path(off)} fill="none" stroke={OFF_COLOR} strokeWidth={1.8} vectorEffect="non-scaling-stroke" />
        {off.map((v, i) => v != null && <circle key={`o${i}`} cx={x(i)} cy={y(v)} r={2} fill={OFF_COLOR} />)}
        {def.map((v, i) => v != null && <circle key={`d${i}`} cx={x(i)} cy={y(v)} r={2} fill={DEF_COLOR} />)}
      </svg>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 2 }}>
        <Mono s={8.5} c={FAINT}>Wk {games[0].week}</Mono>
        <Mono s={8.5} c={FAINT}>dashed = 0 PPA</Mono>
        <Mono s={8.5} c={FAINT}>Wk {games[n - 1].week}</Mono>
      </div>
    </div>
  );
}

function ChartLegend() {
  return (
    <div style={{ display: "flex", gap: 12 }}>
      {[{ color: OFF_COLOR, label: "Off PPA (higher = better)" }, { color: DEF_COLOR, label: "Def PPA allowed (lower = better)" }].map(({ color, label }) => (
        <div key={label} style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <div style={{ width: 12, height: 2, background: color, borderRadius: 1 }} />
          <Mono s={8.5} c={FAINT}>{label}</Mono>
        </div>
      ))}
    </div>
  );
}

// ── Shared stat tile ─────────────────────────────────────────────────────────

function Tile({ label, main, mainColor = "#232a22", sub }: {
  label: string; main: React.ReactNode; mainColor?: string; sub?: React.ReactNode;
}) {
  return (
    <div style={{ background: "#faf8f4", border: "1px solid #ebe5d8", borderRadius: 8, padding: "9px 11px" }}>
      <Mono s={8.5} c={FAINT}>{label}</Mono>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginTop: 4, flexWrap: "wrap" }}>
        <span className="font-mono" style={{ fontSize: 17, fontWeight: 700, color: mainColor }}>{main}</span>
        {sub}
      </div>
    </div>
  );
}

const pctColor = (p: number | null | undefined) => (p == null ? FAINT : p >= 50 ? GOOD : WARN);

/** The four-tile trend block used in BOTH the Teams profile and the
 *  This Week drill, so the two tabs always show the same numbers. */
function TrendTiles({ t }: { t: CfbTeamTrend }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
      <Tile
        label="OFFENSE · PPA/PLAY"
        main={t.off_avg != null ? signed(t.off_avg) : "—"}
        mainColor={t.off_avg == null ? FAINT : t.off_avg >= 0.15 ? GOOD : WARN}
        sub={<><Mono s={9} c={pctColor(t.off_pct)}>{t.off_pct ?? "—"} %ile</Mono><TrendValue v={t.off_trend} s={9} /></>}
      />
      <Tile
        label="DEFENSE · PPA ALLOWED"
        main={t.def_avg != null ? signed(t.def_avg) : "—"}
        mainColor={t.def_avg == null ? FAINT : t.def_avg <= 0.15 ? GOOD : WARN}
        sub={<><Mono s={9} c={pctColor(t.def_pct)}>{t.def_pct ?? "—"} %ile</Mono><TrendValue v={t.def_trend} s={9} /></>}
      />
      <Tile
        label="POINTS FOR"
        main={t.points_for ?? "—"}
        sub={<><Mono s={9} c={FAINT}>{t.ppg != null ? `${t.ppg.toFixed(1)}/g` : ""}</Mono><TrendValue v={t.pf_trend} d={1} s={9} /></>}
      />
      <Tile
        label="POINTS AGAINST"
        main={t.points_against ?? "—"}
        sub={<><Mono s={9} c={FAINT}>{t.papg != null ? `${t.papg.toFixed(1)}/g` : ""}</Mono><TrendValue v={t.pa_trend} d={1} s={9} /></>}
      />
    </div>
  );
}

const TREND_FOOTNOTE = "▲▼ = last 3 games vs first 3 games, signed so ▲ is always improvement · %ile = season avg vs all FBS";

// ── This Week drill: strength comparison for one matchup ─────────────────────

function GameDrill({ awayTeam, homeTeam, season, week, onClose }: {
  awayTeam: string; homeTeam: string; season: number; week: number; onClose: () => void;
}) {
  const [trends, setTrends] = useState<Map<string, CfbTeamTrend> | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  // Use only games played BEFORE this week, so past weeks show what the
  // teams looked like going into the game (no lookahead).
  const throughWeek = Math.max(0, week - 1);

  useEffect(() => {
    setTrends(null);
    setLoadErr(null);
    loadTrends(season, throughWeek).then(setTrends).catch((e: Error) => setLoadErr(e.message));
  }, [season, throughWeek]);

  return (
    <div style={{ background: "#ffffff", border: "1px solid #e6e3dc", borderRadius: 10, padding: "16px 18px", marginBottom: 14 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <div>
          <K>Season to date · entering Week {week}</K>
          <div style={{ marginTop: 3 }}><Mono s={8.5} c={FAINT}>games through Wk {throughWeek}</Mono></div>
        </div>
        <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 16, color: FAINT, lineHeight: 1, padding: "2px 4px" }}>✕</button>
      </div>

      {loadErr ? (
        <ErrorState message={loadErr} />
      ) : !trends ? (
        <Loading label="Loading season trends…" />
      ) : (
        <>
          <div style={{ display: "flex", borderTop: "1px solid #ebe5d8", paddingTop: 14 }}>
            {[{ team: awayTeam, side: "AWAY" }, { team: homeTeam, side: "HOME" }].map(({ team, side }, i) => {
              const t = trends.get(team);
              return (
                <div key={team} style={{ flex: 1, minWidth: 0, paddingLeft: i ? 14 : 0, paddingRight: i ? 0 : 14, borderLeft: i ? "1px solid #ebe5d8" : "none" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                    <Crest name={team} size={26} />
                    <div>
                      <div className="font-serif" style={{ fontSize: 14, fontWeight: 700, color: "#1a2420" }}>{team}</div>
                      <Mono s={9} c={FAINT}>{side}{t ? ` · ${t.games} GAMES` : ""}</Mono>
                    </div>
                  </div>
                  {!t ? (
                    <Empty message={throughWeek === 0 ? "Week 1 — no games played yet." : "No PPA data for this team yet."} />
                  ) : (
                    <>
                      <TrendTiles t={t} />
                      <div style={{ marginTop: 12 }}>
                        <TrendChart games={t.game_log} w={260} h={60} />
                      </div>
                    </>
                  )}
                </div>
              );
            })}
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 12, flexWrap: "wrap", gap: 6 }}>
            <ChartLegend />
            <Mono s={8.5} c={FAINT}>{TREND_FOOTNOTE}</Mono>
          </div>
        </>
      )}
    </div>
  );
}

// ── TeamProfile — full detail panel ──────────────────────────────────────────

function MetricBar({ label, value, lo, hi, fmt, invert }: {
  label: string; value: number | null; lo: number; hi: number; fmt?: (v: number) => string; invert?: boolean;
}) {
  if (value == null) {
    return (
      <div className="mb-[13px]">
        <div className="flex justify-between items-baseline mb-[5px]">
          <span className="text-ink" style={{ fontSize: 12.5 }}>{label}</span>
          <Mono s={11} c={FAINT}>no data</Mono>
        </div>
        <div className="rounded overflow-hidden" style={{ height: 5, background: "#efebe1" }} />
      </div>
    );
  }
  const pct = Math.max(0.04, Math.min(1, (value - lo) / (hi - lo)));
  const good = invert ? value <= (lo + hi) / 2 : value >= (lo + hi) / 2;
  const col = good ? GOOD : WARN;
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

function GameLog({ games }: { games: CfbTrendGame[] }) {
  const cols = "34px 1fr 64px 58px 58px";
  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: cols, gap: 6, paddingBottom: 4, borderBottom: "1px solid #ebe5d8" }}>
        {["WK", "OPPONENT", "SCORE", "OFF", "DEF"].map((h, i) => (
          <div key={h} style={{ textAlign: i >= 2 ? "right" : "left" }}><Mono s={8} c={FAINT}>{h}</Mono></div>
        ))}
      </div>
      {games.map(g => {
        const has = g.points_for != null && g.points_against != null;
        const won = has && (g.points_for as number) > (g.points_against as number);
        return (
          <div key={g.week} style={{ display: "grid", gridTemplateColumns: cols, gap: 6, padding: "5px 0", borderBottom: "1px solid #f3efe6", alignItems: "center" }}>
            <Mono s={10} c={FAINT}>{g.week}</Mono>
            <span style={{ fontSize: 11.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {g.venue === "away" ? "@ " : g.venue === "home" ? "vs " : ""}{g.opponent ?? "—"}
            </span>
            <div style={{ textAlign: "right" }}>
              {has
                ? <Mono s={10} c={won ? GOOD : BAD}>{won ? "W" : "L"} {g.points_for}-{g.points_against}</Mono>
                : <Mono s={10} c={EMPTY}>—</Mono>}
            </div>
            <div style={{ textAlign: "right" }}>
              {g.off_ppa != null ? <Mono s={10} c={g.off_ppa >= 0.15 ? GOOD : WARN}>{signed(g.off_ppa, 2)}</Mono> : <Mono s={10} c={EMPTY}>—</Mono>}
            </div>
            <div style={{ textAlign: "right" }}>
              {g.def_ppa != null ? <Mono s={10} c={g.def_ppa <= 0.15 ? GOOD : WARN}>{signed(g.def_ppa, 2)}</Mono> : <Mono s={10} c={EMPTY}>—</Mono>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function TeamProfile({ team, trend, trendsReady, season, onClose }: {
  team: CfbTeam; trend: CfbTeamTrend | null; trendsReady: boolean; season: number; onClose: () => void;
}) {
  const [detail, setDetail] = useState<CfbTeamDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    setDetail(null);
    setLoadError(null);
    cfbApi.team(team.team).then(setDetail).catch((e) => setLoadError(e.message));
  }, [team.team]);

  if (loadError) return <Card accent><ErrorState message={loadError} /></Card>;

  const seasonRois = detail?.profile?.season_rois_json
    ? parseSeasonRois(detail.profile.season_rois_json as string)
    : [];

  const allSeasonRois = (() => {
    if (!detail) return seasonRois;
    if (seasonRois.some(r => r.season === season)) return seasonRois;
    return [...seasonRois, { season, roi: null as any }];
  })();

  const maxAbsRoi = allSeasonRois.length
    ? Math.max(...allSeasonRois.map((r) => Math.abs(r.roi ?? 0)), 10)
    : 10;

  const adv = detail?.advanced_stats;

  return (
    <Card accent style={{ position: "relative", overflow: "hidden" }}>
      <Watermark size={210} opacity={0.04} />
      <div className="relative">
        <div className="flex items-center gap-[13px] mb-4">
          <Crest name={team.team} size={42} />
          <div className="flex-1 min-w-0">
            <div className="font-serif font-bold text-ink leading-tight" style={{ fontSize: 23 }}>{team.team}</div>
            <div className="flex items-center gap-2 mt-1">
              {team.seasons_profitable >= 3 && <Mono s={9.5} c={GOOD}>● CONSISTENTLY PROFITABLE</Mono>}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ background: "none", border: "none", cursor: "pointer", fontSize: 18, color: FAINT, lineHeight: 1, padding: "4px 6px", alignSelf: "flex-start" }}
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
              <Mono s={8.5} c={FAINT}>{l as string}</Mono>
              <div className="font-serif font-bold mt-1" style={{ fontSize: 20, color: hot ? GOOD : "#232a22" }}>{v as string}</div>
            </div>
          ))}
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
          <K>{season} Season Trend</K>
          <span className="font-mono text-faint" style={{ fontSize: 8.5 }}>
            {trend ? `${trend.games} games · thru Wk ${trend.last_week}` : "cfbd.ppa_games + cfbd.games"}
          </span>
        </div>
        {!trendsReady ? (
          <div style={{ padding: "16px 0" }}><Loading label="Loading season trend…" /></div>
        ) : !trend ? (
          <Empty message={`No ${season} games in the warehouse for ${team.team} yet.`} />
        ) : (
          <>
            <TrendTiles t={trend} />
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", margin: "14px 0 6px" }}>
              <Mono s={8.5} c={FAINT}>NET PPA {trend.net_avg != null ? signed(trend.net_avg) : "—"} · NET TREND</Mono>
              <TrendValue v={trend.net_trend} s={9} />
            </div>
            <TrendChart games={trend.game_log} w={320} h={70} />
            <div style={{ margin: "6px 0 14px" }}><ChartLegend /></div>
            <GameLog games={trend.game_log} />
            <div style={{ margin: "8px 0 18px" }}><Mono s={8} c={FAINT}>{TREND_FOOTNOTE}</Mono></div>
          </>
        )}

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
          <K>Prior-Season Efficiency</K>
          <span className="font-mono text-faint" style={{ fontSize: 8.5 }}>cfbd.advanced_stats · {season - 1}</span>
        </div>
        {!detail ? (
          <div style={{ padding: "16px 0" }}><Loading label="Loading team detail…" /></div>
        ) : !adv ? (
          <Empty message="No advanced stats found for prior season." />
        ) : (
          <>
            <MetricBar label="Offensive PPA" value={adv.off_ppa} lo={-0.1} hi={0.5} fmt={(v) => signed(v)} />
            <MetricBar label="Defensive PPA (lower is better)" value={adv.def_ppa} lo={-0.1} hi={0.5} invert fmt={(v) => signed(v)} />
            <MetricBar label="Offensive success rate" value={adv.off_success_rate} lo={0.3} hi={0.55} fmt={(v) => (v * 100).toFixed(1) + "%"} />
            <MetricBar label="Def success rate (lower better)" value={adv.def_success_rate} lo={0.3} hi={0.55} invert fmt={(v) => (v * 100).toFixed(1) + "%"} />
            <MetricBar label="Defensive havoc rate" value={adv.def_havoc_total} lo={0.1} hi={0.25} fmt={(v) => (v * 100).toFixed(1) + "%"} />
            <MetricBar label="Rush offense PPA" value={adv.off_rush_ppa} lo={-0.1} hi={0.3} fmt={(v) => signed(v)} />
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
              const isCurrent = r.season === season;
              return (
                <div key={r.season} className="flex-1 flex flex-col items-center justify-end" style={{ height: "100%" }}>
                  <Mono s={8.5} c={roi == null ? FAINT : pos ? GOOD : BAD}>
                    {roi == null ? (isCurrent ? "YTD" : "—") : `${pos ? "+" : ""}${roi.toFixed(1)}`}
                  </Mono>
                  <div
                    className="w-full rounded-sm mt-[3px]"
                    style={{
                      height: Math.max(3, h),
                      background: roi == null ? "#e6e3dc" : pos ? GOOD : BAD,
                      opacity: isCurrent ? 0.6 : 0.85,
                      border: isCurrent ? "1px dashed #a39d8c" : "none",
                    }}
                  />
                  <Mono s={8.5} c={isCurrent ? GOOD : FAINT}>'{String(r.season).slice(2)}</Mono>
                </div>
              );
            })}
          </div>
        )}

        <div className="mt-4">
          <Mono s={8.5} c={FAINT}>WALK-FORWARD · NO LOOKAHEAD · cfbd.team_profiles + cfbd.ppa_games + cfbd.games</Mono>
        </div>
      </div>
    </Card>
  );
}

// ── TeamsView ──────────────────────────────────────────────────────────────────

type TeamSort =
  | "roi" | "win" | "off_pct" | "def_pct"
  | "off_trend" | "def_trend" | "net_trend"
  | "pf" | "pa" | "pdiff";

const SORT_OPTS: [TeamSort, string][] = [
  ["roi",       "ROI %"],
  ["win",       "Win %"],
  ["off_pct",   "Off %ile"],
  ["def_pct",   "Def %ile"],
  ["off_trend", "Off Trend"],
  ["def_trend", "Def Trend"],
  ["net_trend", "Net Trend"],
  ["pf",        "Pts For"],
  ["pa",        "Pts Against"],
  ["pdiff",     "Pt Diff"],
];

function MiniBar({ pct, color }: { pct: number; color: string }) {
  const w = Math.max(4, Math.min(100, pct));
  return (
    <div style={{ width: 40, height: 4, background: "#efebe1", borderRadius: 2, overflow: "hidden" }}>
      <div style={{ width: `${w}%`, height: "100%", background: color, borderRadius: 2 }} />
    </div>
  );
}

function PctCell({ v }: { v: number | null | undefined }) {
  if (v == null) return <div style={{ textAlign: "right" }}><Mono s={10} c={EMPTY}>—</Mono></div>;
  const c = pctColor(v);
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
      <Mono s={10} c={c}>{v}</Mono>
      <MiniBar pct={v} color={c} />
    </div>
  );
}

function PointsCell({ total, perGame }: { total: number | null | undefined; perGame: number | null | undefined }) {
  if (total == null) return <div style={{ textAlign: "right" }}><Mono s={10} c={EMPTY}>—</Mono></div>;
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 1 }}>
      <span className="font-mono" style={{ fontSize: 11, color: "#232a22" }}>{total}</span>
      <Mono s={8.5} c={FAINT}>{perGame != null ? `${perGame.toFixed(1)}/g` : ""}</Mono>
    </div>
  );
}

const TEAM_COLS = "20px 24px minmax(110px,1fr) 56px 44px 50px 50px 60px 60px 60px 52px 52px";

function TeamsView({ teams }: { teams: CfbTeam[] }) {
  const season = new Date().getFullYear();
  const [sort, setSort] = useState<TeamSort>("roi");
  const [selName, setSelName] = useState<string | null>(null);
  const [trends, setTrends] = useState<Map<string, CfbTeamTrend> | null>(null);
  const [trendErr, setTrendErr] = useState<string | null>(null);

  useEffect(() => {
    loadTrends(season).then(setTrends).catch((e: Error) => setTrendErr(e.message));
  }, [season]);

  const tr = (team: string) => trends?.get(team) ?? null;
  // Missing values always sort to the bottom regardless of direction.
  const num = (v: number | null | undefined, dir: 1 | -1) => (v == null ? Infinity : -dir * v);

  const keyFor = (t: CfbTeam): number => {
    const s = tr(t.team);
    switch (sort) {
      case "roi":       return num(t.roi_pct, 1);
      case "win":       return num(t.win_rate, 1);
      case "off_pct":   return num(s?.off_pct, 1);
      case "def_pct":   return num(s?.def_pct, 1);
      case "off_trend": return num(s?.off_trend, 1);
      case "def_trend": return num(s?.def_trend, 1);
      case "net_trend": return num(s?.net_trend, 1);
      case "pf":        return num(s?.ppg, 1);
      case "pa":        return num(s?.papg, -1);   // fewest allowed first
      case "pdiff":     return num(s && s.ppg != null && s.papg != null ? s.ppg - s.papg : null, 1);
    }
  };
  const sorted = [...teams].sort((a, b) => keyFor(a) - keyFor(b));
  const sel = selName ? teams.find(t => t.team === selName) ?? null : null;

  const hdr = (label: string, active: boolean) => (
    <div style={{ textAlign: "right" }}><Mono s={8} c={active ? GOOD : FAINT}>{label}</Mono></div>
  );

  return (
    <div className="grid gap-[22px] items-start" style={{ gridTemplateColumns: sel ? "1.45fr 1fr" : "1fr" }}>
      <Card pad={0}>
        <div style={{ padding: "16px 18px 10px" }}>
          <div className="flex justify-between items-center flex-wrap gap-2 mb-3">
            <K>Team Performance · {teams.length} profiled</K>
            {!trends && !trendErr && <Mono s={9} c={FAINT}>Loading {season} trends…</Mono>}
            {trendErr && <Mono s={9} c={BAD}>Trend data failed: {trendErr}</Mono>}
          </div>
          <div className="flex gap-[5px] flex-wrap">
            {SORT_OPTS.map(([k, l]) => (
              <Pill key={k} active={sort === k} onClick={() => setSort(k)}>{l}</Pill>
            ))}
          </div>
          <div style={{ marginTop: 10 }}>
            <Mono s={8.5} c={FAINT}>
              OFF/DEF = {season} season-avg PPA percentile · TREND = last 3 vs first 3 games (▲ improving) · PF/PA = season point totals, per game below
            </Mono>
          </div>
        </div>

        <div style={{ overflowX: "auto" }}>
          <div style={{ minWidth: 720 }}>
            <div style={{
              display: "grid", gridTemplateColumns: TEAM_COLS, gap: 6,
              padding: "6px 26px 6px 18px", borderTop: "1px solid #ebe5d8", borderBottom: "2px solid #ebe5d8",
            }}>
              <span /><span />
              <Mono s={8} c={FAINT}>TEAM</Mono>
              {hdr("ROI%", sort === "roi")}
              {hdr("WIN%", sort === "win")}
              {hdr("OFF", sort === "off_pct")}
              {hdr("DEF", sort === "def_pct")}
              {hdr("OFF TREND", sort === "off_trend" || sort === "net_trend")}
              {hdr("DEF TREND", sort === "def_trend" || sort === "net_trend")}
              {hdr("NET TREND", sort === "net_trend")}
              {hdr("PF", sort === "pf" || sort === "pdiff")}
              {hdr("PA", sort === "pa" || sort === "pdiff")}
            </div>

            <div style={{ padding: "0 18px 14px", maxHeight: 680, overflowY: "auto" }}>
              {sorted.map((t, i) => {
                const on = t.team === selName;
                const s = tr(t.team);
                return (
                  <button
                    key={t.team}
                    onClick={() => setSelName(prev => prev === t.team ? null : t.team)}
                    style={{
                      display: "grid", alignItems: "center", gridTemplateColumns: TEAM_COLS, gap: 6,
                      width: "100%", textAlign: "left", padding: "8px 8px", margin: "0 -8px", borderRadius: 6,
                      background: on ? "#e9efe7" : "transparent",
                      boxShadow: on ? "inset 2px 0 0 #1d5536" : "none",
                      border: "none", cursor: "pointer",
                    }}
                  >
                    <span className="font-mono text-faint" style={{ fontSize: 9 }}>{i + 1}</span>
                    <Crest name={t.team} size={20} />
                    <span style={{ fontSize: 13, fontWeight: on ? 600 : 400, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.team}</span>
                    <div style={{ textAlign: "right" }}>
                      <span className="font-mono font-semibold" style={{ fontSize: 11, color: t.roi_pct >= 0 ? GOOD : BAD }}>
                        {t.roi_pct >= 0 ? "+" : ""}{t.roi_pct.toFixed(1)}%
                      </span>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <span className="font-mono text-muted" style={{ fontSize: 11 }}>{t.win_rate.toFixed(0)}%</span>
                    </div>
                    <PctCell v={s?.off_pct} />
                    <PctCell v={s?.def_pct} />
                    <div style={{ textAlign: "right" }}><TrendValue v={s?.off_trend} /></div>
                    <div style={{ textAlign: "right" }}><TrendValue v={s?.def_trend} /></div>
                    <div style={{ textAlign: "right" }}><TrendValue v={s?.net_trend} /></div>
                    <PointsCell total={s?.points_for} perGame={s?.ppg} />
                    <PointsCell total={s?.points_against} perGame={s?.papg} />
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </Card>

      {sel && (
        <div style={{ position: "sticky", top: 0 }}>
          <TeamProfile team={sel} trend={tr(sel.team)} trendsReady={trends != null || trendErr != null} season={season} onClose={() => setSelName(null)} />
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

// ── This Week: picks for any 2026 week, with inline GameDrill ─────────────────

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

function OutcomeBadge({ p }: { p: CfbPick }) {
  if (!p.outcome || p.outcome === "ungradeable") return null;
  const map = {
    win:     { label: "WIN",     bg: GOOD,      fg: "#fff" },
    loss:    { label: "LOSS",    bg: BAD,       fg: "#fff" },
    push:    { label: "PUSH",    bg: "#efebe1", fg: "#736e5f" },
    pending: { label: "PENDING", bg: "#efebe1", fg: "#736e5f" },
  } as const;
  const m = map[p.outcome];
  const [away, home] = p.matchup.split(" @ ");
  const score = p.home_score != null && p.away_score != null ? `${away} ${p.away_score} – ${home} ${p.home_score}` : null;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      {score && <Mono s={9.5} c="#736e5f">{score}</Mono>}
      <span className="font-mono" style={{ fontSize: 9, letterSpacing: "0.5px", padding: "2px 7px", borderRadius: 9999, background: m.bg, color: m.fg }}>{m.label}</span>
    </span>
  );
}

function PickCardDrillable({ p, isOfficial = true, season, week }: { p: CfbPick; isOfficial?: boolean; season: number; week: number }) {
  const [expanded, setExpanded] = useState(false);
  const isTierRisk = p.bet_type === "FADE_TIER_RISK";
  const accentColor = !isOfficial ? FAINT : isTierRisk ? WARN : GOOD;
  const [awayName, homeName] = p.matchup.split(" @ ");

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
                <span style={{ fontSize: 9, fontFamily: "monospace", textTransform: "uppercase", letterSpacing: "0.06em", color: FAINT, border: "1px solid #d4cfc5", borderRadius: 3, padding: "1px 5px" }}>watch</span>
              )}
              <span className="font-mono" style={{ fontSize: 13, color: accentColor }}>{p.stars} Model: {p.model_score}</span>
              <span style={{ fontSize: 14, color: expanded ? accentColor : "#c4bfb5" }}>{expanded ? "▾" : "▸"}</span>
            </div>
          </div>
          <div className="flex items-baseline justify-between mb-2 flex-wrap gap-1">
            <span style={{ fontSize: 14, fontWeight: 600 }}>{p.bet}</span>
            <span className="flex items-center gap-3">
              <OutcomeBadge p={p} />
              <Mono s={10.5}>{p.line}{p.ou && p.ou !== "N/A" ? ` · O/U ${p.ou}` : ""}</Mono>
            </span>
          </div>
        </button>

        {isTierRisk && <Mono s={9} c={accentColor}>⚠ Bet is on a team with a STRONG_FADE historical tier in this situation</Mono>}
        <p className="text-muted" style={{ fontSize: 12, lineHeight: 1.5, margin: "8px 0 0" }}>{p.edge}</p>

        {p.warnings.length > 0 && (
          <div className="flex flex-col gap-1 mt-2">
            {p.warnings.map((w, i) => <Mono key={i} s={10} c={WARN}>⚠️ {WARNING_LABELS[w] ?? w}</Mono>)}
          </div>
        )}

        {!expanded && (
          <div style={{ marginTop: 10, paddingTop: 8, borderTop: "1px solid #ebe5d8" }}>
            <Mono s={8.5} c="#c4bfb5">▸ CLICK TO SEE SEASON-TO-DATE STRENGTH COMPARISON</Mono>
          </div>
        )}
      </Card>

      {expanded && (
        <div style={{ marginTop: -6 }}>
          <GameDrill awayTeam={awayName} homeTeam={homeName} season={season} week={week} onClose={() => setExpanded(false)} />
        </div>
      )}
    </div>
  );
}

const REGULAR_SEASON_WEEKS = 15;

function WeekRecord({ picks }: { picks: CfbPick[] }) {
  const graded = picks.filter(p => p.outcome === "win" || p.outcome === "loss" || p.outcome === "push");
  if (graded.length === 0) return null;
  const w = graded.filter(p => p.outcome === "win").length;
  const l = graded.filter(p => p.outcome === "loss").length;
  const push = graded.filter(p => p.outcome === "push").length;
  const pnl = graded.reduce((a, p) => a + (p.pnl ?? 0), 0);
  return (
    <Mono s={10} c={pnl >= 0 ? GOOD : BAD}>
      OFFICIAL {w}-{l}{push ? `-${push}` : ""} · {pnl >= 0 ? "+" : ""}{pnl.toFixed(2)}u
    </Mono>
  );
}

function SlateView() {
  const season = new Date().getFullYear();
  const [weeks, setWeeks] = useState<CfbWeeks | null>(null);
  const [week, setWeek] = useState<number | null>(null);
  const [picks, setPicks] = useState<CfbPick[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showAllWatch, setShowAllWatch] = useState(false);

  // 1. Which weeks have archived slates, and which week is "current"?
  useEffect(() => {
    cfbApi.weeks(season)
      .then(w => {
        setWeeks(w);
        const fallback = w.weeks.length ? w.weeks[w.weeks.length - 1].week : 1;
        setWeek(w.current_week ?? fallback);
      })
      .catch((e: Error) => setError(e.message));
  }, [season]);

  // 2. Load the selected week. Archived slate first (has grades); fall back
  //    to todays_picks.json for the current week if it hasn't been archived.
  useEffect(() => {
    if (week == null || !weeks) return;
    setPicks(null);
    setShowAllWatch(false);
    setError(null);
    cfbApi.slate(season, week)
      .then(async (slate) => {
        if (slate.length === 0 && week === weeks.current_week) return cfbApi.picks();
        return slate;
      })
      .then(setPicks)
      .catch((e: Error) => setError(e.message));
  }, [season, week, weeks]);

  const available = new Map((weeks?.weeks ?? []).map(w => [w.week, w]));
  const maxWeek = Math.max(REGULAR_SEASON_WEEKS, ...Array.from(available.keys()));
  const weekOptions = Array.from({ length: maxWeek }, (_, i) => i + 1);

  const optionLabel = (wk: number) => {
    const info = available.get(wk);
    const cur = wk === weeks?.current_week ? " · current" : "";
    if (!info) return `Week ${wk} — no slate`;
    if (info.n_official == null) return `Week ${wk}${cur}`;
    return `Week ${wk}${cur} · ${info.n_official} official${info.graded ? " · graded" : ""}`;
  };

  const header = (
    <div className="flex justify-between items-center mb-4 flex-wrap gap-3">
      <div className="flex items-center gap-3">
        <K color={GOOD}>{season} ·</K>
        <select
          value={week ?? ""}
          onChange={(e) => setWeek(parseInt(e.target.value, 10))}
          disabled={!weeks}
          aria-label="Select week"
          className="font-mono"
          style={{ padding: "6px 10px", borderRadius: 8, border: "1px solid #d9d3c5", background: "#fbfaf5", color: GOOD, fontSize: 11.5, letterSpacing: "0.04em", cursor: "pointer" }}
        >
          {weekOptions.map(wk => (
            <option key={wk} value={wk} disabled={!available.has(wk)}>{optionLabel(wk)}</option>
          ))}
        </select>
        <Mono s={9.5} c={FAINT}>MODEL V3 WALK-FORWARD</Mono>
      </div>
      {picks && <WeekRecord picks={picks.filter(p => p.meets_publish_bar)} />}
    </div>
  );

  const body = (() => {
    if (error) return <ErrorState message={error} />;
    if (!weeks || week == null || !picks) return <Loading label="Loading picks…" />;
    if (picks.length === 0) {
      return (
        <Card>
          <Empty
            message={available.has(week) ? "No games scored this week." : "No slate archived for this week."}
            detail={
              available.has(week)
                ? "Nothing cleared the model's publish threshold — that's the model saying 'no strong signal,' not missing data."
                : "generate_picks.py hasn't been run for this week (future week, or the archive isn't on this machine)."
            }
          />
        </Card>
      );
    }

    const official = picks.filter(p => p.meets_publish_bar);
    const watchAll = picks
      .filter(p => !p.meets_publish_bar && (p.model_score ?? 0) > 0)
      .sort((a, b) => b.model_score - a.model_score);
    const defaultWatch = Math.max(0, 5 - official.length);
    const watchlist = showAllWatch ? watchAll : watchAll.slice(0, defaultWatch);

    const Divider = ({ label }: { label: string }) => (
      <div style={{ display: "flex", alignItems: "center", gap: 8, margin: "12px 0 6px" }}>
        <div style={{ flex: 1, height: 1, background: "#e5e0d4" }} />
        <span style={{ fontSize: 9, fontFamily: "monospace", textTransform: "uppercase", letterSpacing: "0.08em", color: FAINT }}>{label}</span>
        <div style={{ flex: 1, height: 1, background: "#e5e0d4" }} />
      </div>
    );

    return (
      <>
        {official.length > 0 ? (
          <>
            <Divider label={`Official Picks (${official.length})`} />
            <div className="flex flex-col gap-3">
              {official.map((p, i) => <PickCardDrillable key={`off-${week}-${i}`} p={p} isOfficial season={season} week={week} />)}
            </div>
          </>
        ) : (
          <Divider label="No official picks this week" />
        )}

        {watchAll.length > 0 && (
          <>
            <Divider label={`Watch List · Below Publish Bar (${showAllWatch ? watchAll.length : `${watchlist.length} of ${watchAll.length}`})`} />
            <div className="flex flex-col gap-3">
              {watchlist.map((p, i) => <PickCardDrillable key={`watch-${week}-${i}`} p={p} isOfficial={false} season={season} week={week} />)}
            </div>
            {watchAll.length > watchlist.length || showAllWatch ? (
              <button
                onClick={() => setShowAllWatch(v => !v)}
                className="font-mono"
                style={{ display: "block", margin: "12px auto 0", fontSize: 10, color: GOOD, background: "none", border: "1px solid #d9d3c5", borderRadius: 9999, padding: "5px 14px", cursor: "pointer" }}
              >
                {showAllWatch ? "SHOW TOP ONLY" : `SHOW ALL ${watchAll.length} SCORED GAMES`}
              </button>
            ) : null}
          </>
        )}
      </>
    );
  })();

  return (
    <div style={{ maxWidth: 760, margin: "0 auto" }}>
      {header}
      {body}
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
