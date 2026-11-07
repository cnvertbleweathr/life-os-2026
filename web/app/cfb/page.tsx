"use client";

import { Fragment, useEffect, useState } from "react";
import {
  cfbApi, parseSeasonRois,
  type CfbTeam, type CfbTeamDetail, type CfbMatchupResult, type CfbMatchupError,
  type CfbPick, type CfbTeamTrend, type CfbTrendGame, type CfbWeeks, type CfbLiveTracker, type CfbScheduleGame,
} from "@/lib/api";
import {
  Card, PageHead, K, Pill, Watermark, Empty, Loading, ErrorState,
} from "@/components/ui/primitives";
import { TeamLogo } from "@/components/ui/TeamLogo";
import { PixelScene } from "@/components/ui/PixelScene";

// ── Palette ───────────────────────────────────────────────────────────────────

const GOOD = "var(--hue)";
const WARN = "var(--warn)";
const BAD = "var(--neg)";
const FAINT = "var(--faint)";
const EMPTY = "var(--control)";
const OFF_COLOR = "var(--hue)";
const DEF_COLOR = "var(--neg)";

function Mono({ children, c = "var(--muted)", s = 10 }: { children: React.ReactNode; c?: string; s?: number }) {
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
        <line x1={0} x2={w} y1={y(0)} y2={y(0)} stroke="var(--control)" strokeDasharray="3 3" strokeWidth={1} vectorEffect="non-scaling-stroke" />
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

function Tile({ label, main, mainColor = "var(--ink)", sub }: {
  label: string; main: React.ReactNode; mainColor?: string; sub?: React.ReactNode;
}) {
  return (
    <div style={{ background: "var(--raised)", border: "1px solid var(--rule)", borderRadius: 8, padding: "9px 11px" }}>
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
    <div style={{ background: "var(--sheet)", border: "1px solid var(--border)", borderRadius: 10, padding: "16px 18px", marginBottom: 14 }}>
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
          <div style={{ display: "flex", borderTop: "1px solid var(--rule)", paddingTop: 14 }}>
            {[{ team: awayTeam, side: "AWAY" }, { team: homeTeam, side: "HOME" }].map(({ team, side }, i) => {
              const t = trends.get(team);
              return (
                <div key={team} style={{ flex: 1, minWidth: 0, paddingLeft: i ? 14 : 0, paddingRight: i ? 0 : 14, borderLeft: i ? "1px solid var(--rule)" : "none" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                    <Crest name={team} size={26} />
                    <div>
                      <div className="font-serif" style={{ fontSize: 14, fontWeight: 700, color: "var(--ink)" }}>{team}</div>
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
        <div className="rounded overflow-hidden" style={{ height: 5, background: "var(--frame)" }} />
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
      <div className="rounded overflow-hidden" style={{ height: 5, background: "var(--frame)" }}>
        <div className="rounded" style={{ width: `${pct * 100}%`, height: "100%", background: col, transition: "width .4s" }} />
      </div>
    </div>
  );
}

function GameLog({ games }: { games: CfbTrendGame[] }) {
  const cols = "34px 1fr 64px 58px 58px";
  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: cols, gap: 6, paddingBottom: 4, borderBottom: "1px solid var(--rule)" }}>
        {["WK", "OPPONENT", "SCORE", "OFF", "DEF"].map((h, i) => (
          <div key={h} style={{ textAlign: i >= 2 ? "right" : "left" }}><Mono s={8} c={FAINT}>{h}</Mono></div>
        ))}
      </div>
      {games.map(g => {
        const has = g.points_for != null && g.points_against != null;
        const won = has && (g.points_for as number) > (g.points_against as number);
        return (
          <div key={g.week} style={{ display: "grid", gridTemplateColumns: cols, gap: 6, padding: "5px 0", borderBottom: "1px solid var(--raised)", alignItems: "center" }}>
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
            <div key={i} style={{ padding: "12px 0", borderLeft: i ? "1px solid var(--rule)" : "none", paddingLeft: i ? 14 : 0 }}>
              <Mono s={8.5} c={FAINT}>{l as string}</Mono>
              <div className="font-serif font-bold mt-1" style={{ fontSize: 20, color: hot ? GOOD : "var(--ink)" }}>{v as string}</div>
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
                      background: roi == null ? "var(--border)" : pos ? GOOD : BAD,
                      opacity: isCurrent ? 0.6 : 0.85,
                      border: isCurrent ? "1px dashed var(--faint)" : "none",
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
    <div style={{ width: 40, height: 4, background: "var(--frame)", borderRadius: 2, overflow: "hidden" }}>
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
      <span className="font-mono" style={{ fontSize: 11, color: "var(--ink)" }}>{total}</span>
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
    <div className="ons-stack grid gap-[22px] items-start" style={{ gridTemplateColumns: sel ? "1.45fr 1fr" : "1fr" }}>
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
              padding: "6px 26px 6px 18px", borderTop: "1px solid var(--rule)", borderBottom: "2px solid var(--rule)",
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
                      background: on ? "var(--hue-soft)" : "transparent",
                      boxShadow: on ? "inset 2px 0 0 var(--hue)" : "none",
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
  const scoreColor = result.meets_publish_bar ? "var(--hue)" : result.model_score > 0 ? "var(--warn)" : "var(--faint)";
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
          <span className="font-mono rounded-full" style={{ fontSize: 9, letterSpacing: "0.5px", textTransform: "uppercase", padding: "3px 10px", background: result.meets_publish_bar ? "var(--hue)" : "var(--frame)", color: result.meets_publish_bar ? "var(--hue-ink)" : "var(--muted)" }}>
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
            <div key={i} style={{ padding: "10px 0", borderLeft: i ? "1px solid var(--rule)" : "none", paddingLeft: i ? 12 : 0 }}>
              <Mono s={8.5} c="var(--faint)">{l}</Mono>
              <div className="font-mono font-semibold mt-1" style={{ fontSize: 14 }}>{v}</div>
            </div>
          ))}
        </div>
        <EdgeList items={result.edges} color="var(--hue)" label={`SIGNALS (${result.n_edges})`} />
        <EdgeList items={result.warnings} color="var(--warn)" label="WARNINGS" />
        {result.edges.length === 0 && result.warnings.length === 0 && <Empty message="No qualifying signals for this matchup." />}
        {(result.home_coach || result.away_coach) && (
          <div className="mt-4 pt-4 border-t border-border-2">
            <Mono s={9} c="var(--faint)">COACHES</Mono>
            <div className="flex justify-between items-baseline mt-1.5" style={{ fontSize: 12.5 }}>
              <span>{result.home_coach ?? "—"} vs {result.away_coach ?? "—"}</span>
              {result.coach_h2h && <Mono s={10.5} c="var(--muted)">H2H {result.coach_h2h.home_record}-{result.coach_h2h.away_record} ({result.coach_h2h.total} gm)</Mono>}
            </div>
          </div>
        )}
        <div className="mt-4"><Mono s={8.5} c="var(--faint)">score_game() · prior season {result.season - 1} · NOT a probability — ordinal ranking only</Mono></div>
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
    <div className="ons-stack grid gap-[22px]" style={{ gridTemplateColumns: "1fr 1.3fr" }}>
      <Card style={{ maxWidth: 420 }}>
        <K style={{ marginBottom: 14 }}>Matchup Simulator</K>
        <div className="flex flex-col gap-3">
          {[["HOME TEAM", home, setHome], ["AWAY TEAM", away, setAway]].map(([lbl, val, setter]) => (
            <div key={lbl as string}>
              <Mono s={9} c="var(--faint)">{lbl as string}</Mono>
              <select value={val as string} onChange={(e) => (setter as any)(e.target.value)} style={{ width: "100%", marginTop: 4, padding: "7px 9px", borderRadius: 6, border: "1px solid var(--border)", fontSize: 13 }}>
                {names.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
          ))}
          <div className="flex gap-3">
            <div className="flex-1">
              <Mono s={9} c="var(--faint)">SPREAD (NEG = HOME FAV)</Mono>
              <input value={spread} onChange={(e) => setSpread(e.target.value)} style={{ width: "100%", marginTop: 4, padding: "7px 9px", borderRadius: 6, border: "1px solid var(--border)", fontSize: 13 }} />
            </div>
            <div className="flex-1">
              <Mono s={9} c="var(--faint)">OVER/UNDER</Mono>
              <input value={overUnder} onChange={(e) => setOverUnder(e.target.value)} style={{ width: "100%", marginTop: 4, padding: "7px 9px", borderRadius: 6, border: "1px solid var(--border)", fontSize: 13 }} />
            </div>
          </div>
          <div>
            <Mono s={9} c="var(--faint)">SEASON</Mono>
            <input value={season} onChange={(e) => setSeason(e.target.value)} style={{ width: "100%", marginTop: 4, padding: "7px 9px", borderRadius: 6, border: "1px solid var(--border)", fontSize: 13 }} />
            <p className="text-faint mt-1.5 mb-0" style={{ fontSize: 10.5, lineHeight: 1.4 }}>Model uses prior-season stats (season − 1) — walk-forward, no lookahead.</p>
          </div>
          <button onClick={run} disabled={loading || !home || !away} style={{ marginTop: 4, padding: "10px 0", borderRadius: 8, border: "none", background: loading ? "var(--faint)" : "var(--hue)", color: "var(--hue-ink)", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
            {loading ? "Scoring…" : "Run Model"}
          </button>
        </div>
      </Card>
      <div>
        {error && <ErrorState message={error} />}
        {!error && !result && <Card><Empty message="Pick two teams and run the model." detail="Calls the real score_game() walk-forward model directly." /></Card>}
        {result && "error" in result && (
          <Card accent>
            <K color="var(--neg)" style={{ marginBottom: 8 }}>{result.error === "no_advanced_stats" ? "No data for this matchup" : "Request failed"}</K>
            <p style={{ fontSize: 13, lineHeight: 1.5 }}>{result.message}</p>
          </Card>
        )}
        {result && !("error" in result) && <MatchupResultCard result={result} />}
      </div>
    </div>
  );
}

// ── Degenerates Corner — College Football (Logbook Color) ───────────────────
// Header, summary tiles and the slate are built from real data only:
//   /cfb/weeks (which weeks exist), /cfb/slate per week (picks, outcomes, P&L),
//   /cfb/schedule (kickoff times), /cfb/live-tracker (season totals).
// Times are shown in Denver time. Backtest figures quote docs/SYSTEM_EXPLAINER.md.

const TZ = "America/Denver";
const WARNING_SHORT: Record<string, string> = {
  coach_change: "Coach change",
  "coach_change+low_ret": "Coach change, low returning",
  ret_low_home: "Low returning (home)",
  ret_low_away: "Low returning (away)",
  "SP+_disagrees": "SP+ disagrees",
  tier_FADE: "Fade tier",
  tier_STRONG_FADE: "Strong fade tier",
  home_havoc_vs_bet: "Home havoc vs bet",
  away_havoc_vs_bet: "Away havoc vs bet",
};

type Side = "dog" | "fav" | null;
interface ParsedPick {
  p: CfbPick; team: string; line: string; side: Side; opp: string; away: string; home: string; atHome: boolean | null;
  kick: Date | null; final: boolean;
}

function parsePick(p: CfbPick, kicks: Map<string, CfbScheduleGame>): ParsedPick {
  const [away, home] = p.matchup.split(" @ ");
  const m = p.bet.match(/^(.*?)\s+([+-]\d+(?:\.\d+)?|PK)\s*\((home|away)\s+(dog|fav)\)/i);
  const g = kicks.get(`${away}@${home}`);
  const kick = g?.start_date ? new Date(g.start_date) : null;
  if (!m) return { p, team: p.bet, line: "", side: null, opp: "", away, home, atHome: null, kick, final: !!g?.is_final };
  const where = m[3].toLowerCase();
  return {
    p, team: m[1], line: m[2].replace("-", "−"), side: m[4].toLowerCase() as Side,
    opp: where === "home" ? `v ${away}` : `at ${home}`, away, home, atHome: where === "home", kick, final: !!g?.is_final,
  };
}

const fmtTime = (d: Date) =>
  new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "numeric", minute: "2-digit" }).format(d).replace(" AM", " am").replace(" PM", " pm");
const fmtDay = (d: Date, opts: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat("en-US", { timeZone: TZ, ...opts }).format(d);
function denverHour(d: Date): number {
  const parts = new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "numeric", minute: "numeric", hourCycle: "h23" }).formatToParts(d);
  const h = +(parts.find(x => x.type === "hour")?.value ?? 0), m = +(parts.find(x => x.type === "minute")?.value ?? 0);
  return h + m / 60;
}
/** generated_at is a naive local (Denver) timestamp from the pipeline: show it as written. */
function fmtGenerated(s?: string): string {
  const m = s?.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  if (!m) return "";
  const d = new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]);
  const day = d.toLocaleDateString("en-US", { weekday: "short" });
  const h = d.getHours(), ap = h < 12 ? "am" : "pm", hh = ((h + 11) % 12) + 1;
  return `${day} ${hh}:${String(d.getMinutes()).padStart(2, "0")} ${ap}`;
}
const units = (x: number) => `${x >= 0 ? "+" : "−"}${Math.abs(x).toFixed(2)} u`;
const isGraded = (p: CfbPick) => p.outcome === "win" || p.outcome === "loss" || p.outcome === "push";
function record(ps: CfbPick[]) {
  const g = ps.filter(isGraded);
  const w = g.filter(p => p.outcome === "win").length, l = g.filter(p => p.outcome === "loss").length, push = g.filter(p => p.outcome === "push").length;
  return { n: ps.length, graded: g.length, w, l, push, pnl: g.reduce((a, p) => a + (p.pnl ?? 0), 0), label: `${w}–${l}${push ? `–${push}` : ""}` };
}
/** Signal text from the scorer, with raw keys such as "underdog_edge" turned into words. */
const edgeText = (e: string) => (/^[a-z]+(_[a-z+]+)+$/i.test(e) ? (e.charAt(0).toUpperCase() + e.slice(1)).replace(/_/g, " ") : e);
const plural = (n: number, one: string, many = one + "s") => `${n} ${n === 1 ? one : many}`;

function ResultBadge({ p }: { p: CfbPick }) {
  if (p.outcome === "win") return <span className="ons-badge ok">Covered</span>;
  if (p.outcome === "loss") return <span className="ons-badge off">Missed</span>;
  if (p.outcome === "push") return <span className="ons-badge none">Push</span>;
  return <span className="ons-badge none">Pending</span>;
}

function Check({ done }: { done: boolean }) {
  return done
    ? <svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" /><path d="M4.8 8.3l2.2 2.2 4.2-4.6" /></svg>
    : <svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.25" /></svg>;
}

// ── Kickoff strip ───────────────────────────────────────────────────────────

function KickoffStrip({ picks }: { picks: ParsedPick[] }) {
  const timed = picks.filter(x => x.kick).sort((a, b) => +a.kick! - +b.kick!);
  if (!timed.length) return <p className="ons-note" style={{ marginTop: 0 }}>Kickoff times aren't in the schedule yet.</p>;
  // Draw the busiest day; list any picks on other days underneath.
  const byDay = new Map<string, ParsedPick[]>();
  timed.forEach(x => { const k = fmtDay(x.kick!, { year: "numeric", month: "2-digit", day: "2-digit" }); byDay.set(k, [...(byDay.get(k) ?? []), x]); });
  const main = Array.from(byDay.values()).sort((a, b) => b.length - a.length)[0];
  const others = timed.filter(x => !main.includes(x));
  const hours = main.map(x => denverHour(x.kick!));
  const start = Math.min(9, Math.floor(Math.min(...hours))), end = Math.max(24, Math.ceil(Math.max(...hours) + 3.5));
  const span = end - start, pct = (h: number) => ((h - start) / span) * 100;
  const ticks: number[] = []; for (let h = start; h <= end; h += 3) ticks.push(h);
  const tickLabel = (h: number) => (h % 24 === 0 ? "midnight" : h === 12 ? "noon" : h < 12 ? `${h} am` : `${h - 12} pm`);
  return (
    <>
      <div className="ons-kick" style={{ height: main.length * 36 + 20 }} aria-label="Official picks by kickoff, Mountain time">
        {ticks.map(h => <div key={h} className="hr" style={{ left: `${pct(h)}%` }}><span style={h === ticks[ticks.length - 1] ? { transform: "translateX(-100%)" } : undefined}>{tickLabel(h)}</span></div>)}
        {main.map((x, i) => {
          const left = pct(denverHour(x.kick!));
          return (
            <Fragment key={i}>
              <div className="lab" style={{ top: i * 36 }}>{x.team} {x.line}</div>
              <div className={`g ${x.side ?? "fav"}`} style={{ top: i * 36, left: `${left}%`, width: `${Math.min(100 - left, (3.5 / span) * 100)}%` }}>
                <b>{fmtTime(x.kick!)}</b> {x.opp}
              </div>
            </Fragment>
          );
        })}
      </div>
      <div className="ons-legend">
        <span><i style={{ background: "var(--edge-mark)" }} />Underdog pick</span>
        <span><i style={{ background: "var(--ink-2)" }} />Favorite pick</span>
        {others.length > 0 && <span>Also: {others.map(x => `${fmtDay(x.kick!, { weekday: "short" })} ${fmtTime(x.kick!)} ${x.team}`).join(" · ")}</span>}
      </div>
    </>
  );
}

// ── Picks table (official or watch list), rows open the strength comparison ─

function PicksTable({ rows, season, week, watch = false }: { rows: ParsedPick[]; season: number; week: number; watch?: boolean }) {
  const [open, setOpen] = useState<number | null>(null);
  const anyGraded = rows.some(x => isGraded(x.p));
  const cols = 6 + (anyGraded ? 1 : 0) + (watch ? 1 : 0);
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="ons-table">
        <thead>
          <tr>
            <th>Kick</th><th>Pick</th><th className="r">Line</th><th className="hide-p">Side</th>
            <th className="r hide-p">Total</th><th className="r">Score</th>
            {watch && <th className="r hide-p">Signals</th>}
            <th className="hide-p">Why</th>
            {anyGraded && <th className="r">Result</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((x, i) => {
            const edges = x.p.edge.split(" · ").filter(Boolean).map(edgeText);
            const isOpen = open === i;
            return (
              <Fragment key={i}>
                <tr className={`click ${x.side ?? "fav"} ${isOpen ? "open" : ""}`} onClick={() => setOpen(isOpen ? null : i)}
                    aria-expanded={isOpen} tabIndex={0} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), setOpen(isOpen ? null : i))}>
                  <td className="ons-n">{x.kick ? <>{fmtTime(x.kick).replace(/ (am|pm)$/, "")}<span className="sub">{fmtDay(x.kick, { weekday: "short" })}</span></> : "–"}</td>
                  <td><span className="flex items-center gap-2"><Crest name={x.team} size={18} /><span>{x.team}<span className="sub">{x.opp}</span></span></span></td>
                  <td className="r ons-n">{x.line || "–"}</td>
                  <td className="hide-p">{x.side && <span className="ons-side">{x.side === "dog" ? "Underdog" : "Favorite"}</span>}</td>
                  <td className="r ons-n hide-p">{x.p.ou && x.p.ou !== "N/A" ? x.p.ou : "–"}</td>
                  <td className="r"><span className="ons-score"><s><b style={{ width: `${Math.min(100, x.p.model_score)}%` }} /></s><span className="ons-n">{x.p.model_score}</span></span></td>
                  {watch && <td className="r ons-n hide-p">{x.p.n_edges}</td>}
                  <td className="hide-p" style={{ fontSize: 13, color: "var(--ink-2)" }}>
                    {edges.slice(0, 2).join(" · ")}{edges.length > 2 ? ` +${edges.length - 2}` : ""}
                    {x.p.warnings.map(w => <span key={w} className="ons-badge risk" style={{ marginLeft: 6 }}>{WARNING_SHORT[w] ?? w}</span>)}
                  </td>
                  {anyGraded && (
                    <td className="r">
                      <ResultBadge p={x.p} />
                      {x.p.home_score != null && x.p.away_score != null && x.atHome != null && (() => {
                        const us = x.atHome ? x.p.home_score : x.p.away_score, them = x.atHome ? x.p.away_score : x.p.home_score;
                        return <span className="sub ons-n">{us > them ? "Won" : us < them ? "Lost" : "Tied"} {us}–{them}</span>;
                      })()}
                    </td>
                  )}
                </tr>
                {isOpen && (
                  <tr><td colSpan={cols} style={{ padding: "4px 0 12px", background: "transparent" }}>
                    <GameDrill awayTeam={x.away} homeTeam={x.home} season={season} week={week} onClose={() => setOpen(null)} />
                  </td></tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Summary tiles ───────────────────────────────────────────────────────────

function SummaryTiles({ tracker, weeks, official, current, lastGraded, curPicks, curGenerated }: {
  tracker: CfbLiveTracker | null; weeks: CfbWeeks; official: Map<number, CfbPick[]>; current: number; lastGraded: number | null;
  curPicks: ParsedPick[]; curGenerated: string;
}) {
  const chartWeeks = Array.from(official.entries()).filter(([wk, ps]) => ps.length && wk <= (lastGraded ?? 0)).sort((a, b) => a[0] - b[0]);
  const maxStack = Math.max(1, ...chartWeeks.map(([, ps]) => record(ps).w + record(ps).l));
  const firstPickWeek = weeks.weeks.find(w => (w.n_official ?? 0) > 0)?.week;
  const lastWeek = Math.max(14, current);
  const prev = lastGraded != null ? record(official.get(lastGraded) ?? []) : null;
  const cur = record(curPicks.map(x => x.p));
  const finals = curPicks.filter(x => x.final).length;
  const firstKick = curPicks.filter(x => x.kick).sort((a, b) => +a.kick! - +b.kick!)[0]?.kick;
  const watchCount = weeks.weeks.find(w => w.week === current)?.n_scored;
  const steps: Array<[boolean, string, string]> = [
    ...(prev && lastGraded !== current ? [[prev.graded === prev.n, `Week ${lastGraded} graded`, `${prev.label} · ${units(prev.pnl)}`] as [boolean, string, string]] : []),
    [curPicks.length > 0, "Picks set", curPicks.length ? `${curPicks.length} official${curGenerated ? ` · ${curGenerated}` : ""}` : "not yet"],
    [curPicks.length > 0 && finals === curPicks.length, "Games final", curPicks.length ? (finals ? `${finals} of ${curPicks.length}` : firstKick ? `first kick ${fmtDay(firstKick, { weekday: "short" })} ${fmtTime(firstKick)}` : "–") : "–"],
    [curPicks.length > 0 && cur.graded === curPicks.length, "Graded", curPicks.length ? `${cur.graded} of ${curPicks.length}${cur.graded ? ` · ${cur.label}` : ""}` : "–"],
  ];
  const done = steps.filter(s => s[0]).length;
  return (
    <div className="ons-tiles">
      <section className="ons-tile t t-edge" aria-labelledby="t-season">
        <h2 id="t-season">Season so far</h2>
        <div className="big n">{tracker?.total_pnl != null ? units(tracker.total_pnl) : "–"}</div>
        <p className="ons-n">{tracker && tracker.graded_picks ? `${tracker.wins}–${tracker.losses}${tracker.pushes ? `–${tracker.pushes}` : ""} · ${tracker.win_rate_pct}% · ROI ${tracker.roi_pct! >= 0 ? "+" : ""}${tracker.roi_pct}%` : "No graded picks yet"}</p>
        {chartWeeks.length > 0 && (
          <>
            <div className="ons-wk" style={{ height: Math.max(40, maxStack * 8) }} role="img"
                 aria-label={`Covered and missed picks by week: ${chartWeeks.map(([wk, ps]) => `week ${wk} ${record(ps).label}`).join(", ")}`}>
              {chartWeeks.map(([wk, ps]) => { const r = record(ps); return <div key={wk}>{Array.from({ length: r.w }, (_, i) => <i key={`w${i}`} className="w" />)}{Array.from({ length: r.l }, (_, i) => <i key={`l${i}`} className="l" />)}</div>; })}
            </div>
            <div className="ons-wkx" aria-hidden="true">{chartWeeks.map(([wk]) => <span key={wk}>{wk}</span>)}</div>
          </>
        )}
      </section>

      <section className="ons-tile" aria-labelledby="t-cal">
        <h2 id="t-cal">Where we are</h2>
        <div className="big">Week {current}</div>
        <p>{lastGraded ? `Weeks 1–${lastGraded} graded` : "Nothing graded yet"}{firstPickWeek ? `; picks began in Week ${firstPickWeek}.` : "."}</p>
        <div className="ons-seasonbar" role="img" aria-label={`Week ${current} of ${lastWeek}`}>
          {Array.from({ length: lastWeek }, (_, i) => {
            const wk = i + 1, info = weeks.weeks.find(w => w.week === wk);
            const cls = wk === current ? "now" : wk < current ? ((info?.n_official ?? 0) > 0 ? "done" : "none") : "";
            return <i key={wk} className={cls} title={`Week ${wk}`} />;
          })}
        </div>
        <div className="ons-seasonx" aria-hidden="true"><span>Wk 1</span><span>Wk {lastWeek}</span></div>
        <p className="tnote">{Array.from(official.values()).reduce((a, ps) => a + ps.length, 0)} official picks this season{watchCount ? ` · ${watchCount} games scored this week` : ""}</p>
      </section>

      <section className="ons-tile" aria-labelledby="t-run">
        <h2 id="t-run">This week's run</h2>
        <div className="big">{done} of {steps.length} done</div>
        <ol className="ons-steps">
          {steps.map(([ok, label, detail]) => <li key={label} className={ok ? "ok" : "todo"}><Check done={ok} /><b>{label}</b><span>{detail}</span></li>)}
        </ol>
      </section>

      <section className="ons-tile" aria-labelledby="t-model">
        <h2 id="t-model">The model</h2>
        <div className="big">7 signals</div>
        {/* Active signals and backtest: README "CFB Betting System" and docs/SYSTEM_EXPLAINER.md "The Numbers". */}
        <p>One deterministic scorer. Each signal was walk-forward tested on 2021–25 with no lookahead; 3 were cut in the July 2026 audit.</p>
        <p>A pick needs a score of 70+ and 4+ signals. Backtest 2021–25: 250–115 (68.5%), for reference only.</p>
      </section>
    </div>
  );
}

// ── Page root ─────────────────────────────────────────────────────────────────

export default function CfbPage() {
  const season = new Date().getFullYear();
  const [tab, setTab] = useState<"slate" | "watch" | "lab" | "teams">("slate");
  const [teams, setTeams] = useState<CfbTeam[] | null>(null);
  const [weeks, setWeeks] = useState<CfbWeeks | null>(null);
  const [slates, setSlates] = useState<Map<number, CfbPick[]> | null>(null);
  const [tracker, setTracker] = useState<CfbLiveTracker | null>(null);
  const [week, setWeek] = useState<number | null>(null);
  const [schedule, setSchedule] = useState<Map<number, CfbScheduleGame[]>>(new Map());
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    cfbApi.teams().then(setTeams).catch(() => {});
    cfbApi.liveTracker(season).then(setTracker).catch(() => {});
    cfbApi.weeks(season).then(async (w) => {
      setWeeks(w);
      const cur = w.current_week ?? (w.weeks.length ? w.weeks[w.weeks.length - 1].week : 1);
      setWeek(cur);
      const entries = await Promise.all(
        w.weeks.filter(x => (x.n_scored ?? 0) > 0 || x.week === cur).map(async (x) => {
          let s = await cfbApi.slate(season, x.week).catch(() => [] as CfbPick[]);
          if (!s.length && x.week === cur) s = await cfbApi.picks().catch(() => [] as CfbPick[]);
          return [x.week, s] as [number, CfbPick[]];
        }),
      );
      setSlates(new Map(entries));
    }).catch((e: Error) => setError(e.message));
  }, [season]);

  // Kickoff times for the current week (header) and the week being viewed.
  useEffect(() => {
    if (!weeks) return;
    const need = [weeks.current_week, week].filter((x): x is number => x != null && !schedule.has(x));
    need.forEach(wk => cfbApi.schedule(season, wk).then(g => setSchedule(m => new Map(m).set(wk, g))).catch(() => setSchedule(m => new Map(m).set(wk, []))));
  }, [weeks, week]); // eslint-disable-line react-hooks/exhaustive-deps

  if (error) return <div className="ons-page" style={{ padding: "34px 44px 48px" }}><ErrorState message={error} /></div>;
  if (!weeks || !slates || week == null) return <Loading label="Loading the slate…" />;

  const current = weeks.current_week ?? week;
  const official = new Map(Array.from(slates.entries()).map(([wk, ps]) => [wk, ps.filter(p => p.meets_publish_bar)]));
  const lastGraded = Array.from(official.entries()).filter(([, ps]) => ps.length && ps.every(isGraded)).map(([wk]) => wk).sort((a, b) => b - a)[0] ?? null;
  const parse = (wk: number, ps: CfbPick[]) => {
    const kicks = new Map((schedule.get(wk) ?? []).map(g => [`${g.away_team}@${g.home_team}`, g]));
    return ps.map(p => parsePick(p, kicks)).sort((a, b) => (a.kick && b.kick ? +a.kick - +b.kick : 0));
  };
  const curPicks = parse(current, official.get(current) ?? []);
  const curGenerated = fmtGenerated((slates.get(current) ?? []).map(p => p.generated_at).filter(Boolean).sort().pop());
  const dogs = curPicks.filter(x => x.side === "dog").length, favs = curPicks.filter(x => x.side === "fav").length;
  const kickDays = curPicks.filter(x => x.kick).map(x => fmtDay(x.kick!, { weekday: "long", month: "long", day: "numeric" }));
  const mainDay = kickDays.sort((a, b) => kickDays.filter(d => d === b).length - kickDays.filter(d => d === a).length)[0];
  const cur = record(curPicks.map(x => x.p));
  const seasonUnits = tracker?.total_pnl;

  const lede = !curPicks.length
    ? <>No official picks yet for Week {current}. Picks are set Monday to Wednesday.</>
    : <>
        {plural(curPicks.length, "pick")} {mainDay ? `for ${mainDay.split(",")[0]}` : "this week"}, <b>{plural(dogs, "underdog")} and {plural(favs, "favorite")}</b>, all from one deterministic model.
        {cur.graded > 0 && <> {cur.graded} of {curPicks.length} graded so far ({cur.label}, {units(cur.pnl)}).</>}
        {seasonUnits != null && <> The season is {seasonUnits >= 0 ? "up" : "down"} <b>{Math.abs(seasonUnits).toFixed(2)} units</b>{lastGraded ? <> through Week {lastGraded}</> : null}.</>}
      </>;

  const copySlate = async () => {
    const lines = [`Degenerates Corner · Week ${current}${mainDay ? ` · ${mainDay}` : ""}`,
      ...curPicks.map(x => `${x.kick ? fmtTime(x.kick) + "  " : ""}${x.team} ${x.line} ${x.opp} · score ${x.p.model_score}`)];
    try { await navigator.clipboard.writeText(lines.join("\n")); setCopied(true); setTimeout(() => setCopied(false), 1600); } catch {}
  };

  const viewAll = slates.get(week) ?? [];
  const viewOfficial = parse(week, viewAll.filter(p => p.meets_publish_bar));
  const viewWatch = parse(week, viewAll.filter(p => !p.meets_publish_bar && (p.model_score ?? 0) > 0)).sort((a, b) => b.p.model_score - a.p.model_score);
  const prevWeek = Array.from(official.entries()).filter(([wk, ps]) => wk < week && ps.length).map(([wk]) => wk).sort((a, b) => b - a)[0];
  const prevRows = prevWeek != null ? parse(prevWeek, official.get(prevWeek) ?? []) : [];
  const prevRec = record(prevRows.map(x => x.p));
  const weekInfo = new Map(weeks.weeks.map(w => [w.week, w]));
  const byWeek = Array.from(official.entries()).filter(([, ps]) => ps.length && ps.every(isGraded)).sort((a, b) => a[0] - b[0]).map(([wk, ps]) => [wk, record(ps)] as const);

  return (
    <div className="ons-page" style={{ padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" }}>
      <PageHead
        title="Degenerates Corner"
        titleSub="— College Football"
        kicker={`Week ${current}${mainDay ? ` · ${mainDay}` : ""} · DraftKings lines${curGenerated ? ` · picks set ${curGenerated}` : ""}`}
        sub={lede}
        right={
          <div className="flex gap-2">
            {lastGraded != null && <button className="ons-tap ons-btn" onClick={() => { setTab("slate"); setWeek(lastGraded); }}>Week {lastGraded} results</button>}
            <button className="ons-tap ons-btn pri" onClick={copySlate} disabled={!curPicks.length}>{copied ? "Copied" : "Copy slate"}</button>
          </div>
        }
        scene={<PixelScene scene="cfb" record={tracker && tracker.graded_picks ? `${tracker.wins}-${tracker.losses}` : ""} label="a ball carrier breaking upfield, the season record on the scoreboard" />}
      />

      <SummaryTiles tracker={tracker} weeks={weeks} official={official} current={current} lastGraded={lastGraded} curPicks={curPicks} curGenerated={curGenerated} />

      <div className="ons-tabs" role="tablist" aria-label="Degenerates Corner">
        {([["slate", "Slate"], ["watch", `Watch list · ${viewWatch.length}`], ["lab", "Matchup Lab"], ["teams", "Teams"]] as const).map(([k, l]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{l}</button>
        ))}
        {(tab === "slate" || tab === "watch") && (
          <div className="ons-tabs-end">
            <select className="ons-select" value={week} onChange={(e) => setWeek(parseInt(e.target.value, 10))} aria-label="Week">
              {Array.from({ length: Math.max(15, current) }, (_, i) => i + 1).map(wk => {
                const info = weekInfo.get(wk);
                return <option key={wk} value={wk} disabled={!slates.has(wk)}>Week {wk}{wk === current ? " (current)" : ""}{info?.n_official ? ` · ${info.n_official} picks` : ""}</option>;
              })}
            </select>
          </div>
        )}
      </div>

      {tab === "slate" && (
        viewAll.length === 0 ? (
          <div className="ons-card"><Empty message="No slate archived for this week." detail="generate_picks.py hasn't run for this week yet." /></div>
        ) : (
          <div className="ons-grid">
            <section className="ons-card s12" aria-labelledby="kick-h">
              <div className="ons-ch"><h2 id="kick-h">Week {week}, by kickoff</h2><span className="aside">Mountain time · bars are about 3½ hours</span></div>
              {viewOfficial.length ? <KickoffStrip picks={viewOfficial} /> : <p className="ons-note" style={{ marginTop: 0 }}>No game cleared the publish bar this week. That's the model saying there's no strong signal, not missing data.</p>}
            </section>

            <section className="ons-card s8" aria-labelledby="picks-h">
              <div className="ons-ch"><h2 id="picks-h">Official picks</h2><span className="aside">Line from our side · DraftKings · select a row for the strength comparison</span></div>
              {viewOfficial.length ? <PicksTable rows={viewOfficial} season={season} week={week} /> : <Empty message="No official picks this week." />}
              <p className="ons-note">Scores rank picks (70+ with 4+ signals publishes); they aren't probabilities.</p>
            </section>

            <div className="s4 ons-col">
              {prevWeek != null && (
                <section className="ons-card" aria-labelledby="prev-h">
                  <div className="ons-ch"><h2 id="prev-h">Week {prevWeek}</h2><span className="aside ons-n">{prevRec.label} · {units(prevRec.pnl)}</span></div>
                  <table className="ons-table"><tbody>
                    {prevRows.map((x, i) => <tr key={i}><td>{x.team} <span className="ons-n">{x.line}</span></td><td className="r"><ResultBadge p={x.p} /></td></tr>)}
                  </tbody></table>
                </section>
              )}
              {byWeek.length > 0 && (
                <section className="ons-card" aria-labelledby="wbw-h">
                  <div className="ons-ch"><h2 id="wbw-h">Week by week</h2><span className="aside">Official picks, 1 unit each</span></div>
                  <table className="ons-table">
                    <thead><tr><th>Week</th><th className="r">Record</th><th className="r">Units</th></tr></thead>
                    <tbody>
                      {byWeek.map(([wk, r]) => (
                        <tr key={wk} className="click" onClick={() => setWeek(wk)} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && setWeek(wk)}>
                          <td>Week {wk}</td><td className="r ons-n">{r.label}</td>
                          <td className="r ons-n" style={{ color: r.pnl >= 0 ? "var(--pos)" : "var(--neg)" }}>{units(r.pnl)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </section>
              )}
            </div>
          </div>
        )
      )}

      {tab === "watch" && (
        <section className="ons-card" aria-labelledby="watch-h">
          <div className="ons-ch"><h2 id="watch-h">Watch list · Week {week}</h2><span className="aside">Scored, but under the publish bar (score 65–69, or only 3 signals)</span></div>
          {viewWatch.length ? <PicksTable rows={viewWatch} season={season} week={week} watch /> : <Empty message="Nothing on the watch list this week." />}
        </section>
      )}

      {tab === "lab" && (teams ? <MatchupLab teams={teams} /> : <Loading label="Loading teams…" />)}
      {tab === "teams" && (teams ? <TeamsView teams={teams} /> : <Loading label="Loading teams…" />)}
    </div>
  );
}
