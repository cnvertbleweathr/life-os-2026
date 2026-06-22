"use client";

import { useEffect, useState } from "react";
import { cfbApi, parseSeasonRois, type CfbTeam, type CfbTeamDetail } from "@/lib/api";
import {
  Card, PageHead, Stat, K, Pill, Watermark, Empty, Loading, ErrorState,
} from "@/components/ui/primitives";
import { TeamLogo } from "@/components/ui/TeamLogo";

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

function TeamProfile({ team }: { team: CfbTeam }) {
  const [detail, setDetail] = useState<CfbTeamDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    setDetail(null);
    setLoadError(null);
    cfbApi.team(team.team).then(setDetail).catch((e) => setLoadError(e.message));
  }, [team.team]);

  const tierColor = TIER_COLORS[team.tier] ?? "#736e5f";

  if (loadError) {
    return (
      <Card accent>
        <ErrorState message={loadError} />
      </Card>
    );
  }

  const seasonRois = detail?.profile?.season_rois_json
    ? parseSeasonRois(detail.profile.season_rois_json as string)
    : [];
  const maxAbsRoi = seasonRois.length
    ? Math.max(...seasonRois.map((r) => Math.abs(r.roi ?? 0)), 10)
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
              <span
                className="font-mono text-white rounded-full"
                style={{ fontSize: 9, letterSpacing: "0.5px", textTransform: "uppercase", background: tierColor, padding: "2px 9px" }}
              >
                {team.tier}
              </span>
              {team.seasons_profitable >= 3 && (
                <Mono s={9.5} c="#1d5536">● CONSISTENTLY PROFITABLE</Mono>
              )}
            </div>
          </div>
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

        <div className="flex justify-between items-baseline mb-3">
          <K>Prior-Season Efficiency</K>
          <span className="font-mono text-faint" style={{ fontSize: 8.5 }}>cfbd.advanced_stats</span>
        </div>
        {!detail ? (
          <div className="py-4"><Loading label="Loading team detail..." /></div>
        ) : !adv ? (
          <Empty message="No advanced stats found for this team's prior season." />
        ) : (
          <>
            <MetricBar label="Offensive PPA" value={adv.off_ppa} lo={-0.1} hi={0.5} fmt={(v) => (v >= 0 ? "+" : "") + v.toFixed(3)} />
            <MetricBar label="Defensive PPA (lower is better)" value={adv.def_ppa} lo={-0.1} hi={0.5} invert fmt={(v) => (v >= 0 ? "+" : "") + v.toFixed(3)} />
            <MetricBar label="Offensive success rate" value={adv.off_success_rate} lo={0.3} hi={0.55} fmt={(v) => (v * 100).toFixed(1) + "%"} />
            <MetricBar label="Defensive success rate (lower is better)" value={adv.def_success_rate} lo={0.3} hi={0.55} invert fmt={(v) => (v * 100).toFixed(1) + "%"} />
            <MetricBar label="Defensive havoc rate" value={adv.def_havoc_total} lo={0.1} hi={0.25} fmt={(v) => (v * 100).toFixed(1) + "%"} />
            <MetricBar label="Rush offense PPA" value={adv.off_rush_ppa} lo={-0.1} hi={0.3} fmt={(v) => (v >= 0 ? "+" : "") + v.toFixed(3)} />
          </>
        )}

        <K style={{ margin: "18px 0 10px" }}>Backtested ROI by season</K>
        {!detail ? (
          <div className="py-2" />
        ) : seasonRois.length === 0 ? (
          <Empty message="No season-by-season ROI breakdown available." />
        ) : (
          <div className="flex items-end gap-[10px]" style={{ height: 56 }}>
            {seasonRois.map((r) => {
              const roi = r.roi;
              const h = roi != null ? (Math.abs(roi) / maxAbsRoi) * 46 : 0;
              const pos = roi != null && roi >= 0;
              return (
                <div key={r.season} className="flex-1 flex flex-col items-center justify-end" style={{ height: "100%" }}>
                  <Mono s={8.5} c={roi == null ? "#a39d8c" : pos ? "#1d5536" : "#a8473a"}>
                    {roi == null ? "—" : `${pos ? "+" : ""}${roi.toFixed(1)}`}
                  </Mono>
                  <div
                    className="w-full rounded-sm mt-[3px]"
                    style={{
                      height: Math.max(3, h),
                      background: roi == null ? "#e6e3dc" : pos ? "#1d5536" : "#a8473a",
                      opacity: 0.85,
                    }}
                  />
                  <Mono s={8.5} c="#a39d8c">'{String(r.season).slice(2)}</Mono>
                </div>
              );
            })}
          </div>
        )}

        <K style={{ margin: "18px 0 10px" }}>Recent Games · prior season</K>
        {!detail ? (
          <div className="py-2" />
        ) : detail.recent_games.length === 0 ? (
          <Empty message="No recent game context found." />
        ) : (
          <div className="flex flex-col gap-2">
            {detail.recent_games.slice(0, 6).map((g, i) => (
              <div key={i} className="flex items-center justify-between" style={{ fontSize: 11.5 }}>
                <span className="text-muted">
                  {g.away_team} @ {g.home_team} · Wk {g.week}
                </span>
                <span
                  className="font-mono"
                  style={{
                    fontSize: 10,
                    color: g.spread_result === "covered" ? "#1d5536" : g.spread_result === "missed" ? "#a8473a" : "#a39d8c",
                  }}
                >
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

function TeamsView({ teams }: { teams: CfbTeam[] }) {
  const [sort, setSort] = useState<"roi" | "win">("roi");
  const sorted = [...teams].sort((a, b) =>
    sort === "roi" ? b.roi_pct - a.roi_pct : b.win_rate - a.win_rate
  );
  const [selName, setSelName] = useState(sorted[0]?.team ?? "");
  const sel = teams.find((t) => t.team === selName) || sorted[0];

  return (
    <div className="grid gap-[22px] items-start" style={{ gridTemplateColumns: "1.55fr 1fr" }}>
      <Card pad={0}>
        <div className="flex justify-between items-center" style={{ padding: "16px 18px 12px" }}>
          <K>Team Performance · {teams.length} profiled</K>
          <div className="flex gap-[7px]">
            <Pill active={sort === "roi"} onClick={() => setSort("roi")}>ROI</Pill>
            <Pill active={sort === "win"} onClick={() => setSort("win")}>Win %</Pill>
          </div>
        </div>
        <div className="ons-scroll" style={{ padding: "0 18px 14px", maxHeight: 640, overflowY: "auto" }}>
          {sorted.map((t, i) => {
            const on = t.team === selName;
            return (
              <button
                key={t.team}
                className="ons-tap w-full text-left flex items-center gap-[11px] border-none cursor-pointer border-t border-border-2"
                onClick={() => setSelName(t.team)}
                style={{
                  padding: "9px 8px", margin: "0 -8px", borderRadius: 6,
                  background: on ? "#e9efe7" : "transparent",
                  boxShadow: on ? "inset 2px 0 0 #1d5536" : "none",
                  borderTop: "1px solid #ebe5d8",
                }}
              >
                <span className="font-mono text-faint" style={{ fontSize: 10, width: 16 }}>{i + 1}</span>
                <Crest name={t.team} size={20} />
                <span className="flex-1" style={{ fontSize: 13, fontWeight: on ? 600 : 400 }}>{t.team}</span>
                <span className="font-mono uppercase" style={{ fontSize: 9, color: TIER_COLORS[t.tier] ?? "#736e5f", width: 70 }}>{t.tier}</span>
                <span className="font-mono text-muted" style={{ fontSize: 11.5, width: 50, textAlign: "right" }}>{t.win_rate.toFixed(0)}%</span>
                <span className="font-mono font-semibold" style={{ fontSize: 11.5, color: t.roi_pct >= 0 ? "#1d5536" : "#a8473a", width: 58, textAlign: "right" }}>
                  {t.roi_pct >= 0 ? "+" : ""}{t.roi_pct.toFixed(1)}%
                </span>
              </button>
            );
          })}
        </div>
      </Card>
      <div className="sticky top-0">
        {sel && <TeamProfile team={sel} />}
      </div>
    </div>
  );
}

function MatchupLab() {
  return (
    <Card style={{ maxWidth: 640 }}>
      <K style={{ marginBottom: 12 }}>Matchup Simulator</K>
      <Empty
        message="Not wired to real data yet."
        detail="The real score_game() logic (backtest_walk_forward.py) combines prior-season PPA gap, success-rate interaction, recruiting context, team tier, returning production, and several filters — it's not something to approximate with a simplified formula. Building this properly means porting the actual scoring function, not guessing at it."
      />
    </Card>
  );
}

function Slate() {
  return (
    <Empty
      message="No games this week — preseason."
      detail="The weekly slate will auto-populate when the 2026 season opens and todays_picks.json starts getting generated."
    />
  );
}

export default function CfbPage() {
  const [teams, setTeams] = useState<CfbTeam[] | null>(null);
  const [tab, setTab] = useState<"slate" | "lab" | "teams">("teams");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    cfbApi.teams().then(setTeams).catch((e) => setError(e.message));
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!teams) return <Loading />;

  const TABS: Array<[string, string]> = [
    ["slate", "This Week"],
    ["lab", "Matchup Lab"],
    ["teams", "Teams"],
  ];

  return (
    <div className="ons-page" style={{ padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" }}>
      <PageHead
        title="CFB Betting"
        kicker="The Degenerates' Corner · walk-forward validated"
        right={
          <div className="flex gap-1 rounded-full" style={{ background: "#fbfaf5", border: "1px solid #e6e3dc", padding: 4 }}>
            {TABS.map(([k, l]) => (
              <button
                key={k}
                className="ons-tap border-none cursor-pointer rounded-full"
                onClick={() => setTab(k as any)}
                style={{
                  fontSize: 12, fontWeight: 500, padding: "7px 15px",
                  background: tab === k ? "#1d5536" : "transparent",
                  color: tab === k ? "#fff" : "#736e5f",
                }}
              >
                {l}
              </button>
            ))}
          </div>
        }
      />

      <div style={{ borderTop: "1.5px solid #232a22", borderBottom: "1px solid #e6e3dc", marginBottom: 28 }}>
        <div className="flex justify-between items-center" style={{ padding: "12px 0 4px" }}>
          <K color="#1d5536">2026 Season · Live Tracker</K>
          <span className="font-mono" style={{ fontSize: 9, color: "#9a6a1e", border: "1px solid rgba(154,106,30,0.33)", borderRadius: 999, padding: "2px 9px" }}>
            PRESEASON
          </span>
        </div>
        <div className="grid grid-cols-4">
          <Stat label="Graded Picks" value={0} />
          <Stat label="Record" value="0–0" />
          <Stat label="Win Rate" value="—" />
          <Stat label="ROI" value="—" last />
        </div>
        <div style={{ padding: "0 0 12px" }}>
          <span className="font-mono text-faint" style={{ fontSize: 9.5 }}>
            MODEL LOCKED FROM 4-SEASON WALK-FORWARD BACKTEST · 224–94 · 70.4% · +34.5% ROI (318 BETS, 4/4)
          </span>
        </div>
      </div>

      {tab === "slate" && <Slate />}
      {tab === "lab" && <MatchupLab />}
      {tab === "teams" && <TeamsView teams={teams} />}
    </div>
  );
}
