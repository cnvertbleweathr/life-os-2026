"use client";

import { useEffect, useState } from "react";
import { cfbApi, parseSeasonRois, type CfbTeam, type CfbTeamDetail, type CfbMatchupResult, type CfbMatchupError, type CfbScheduleGame, type CfbPick } from "@/lib/api";
import {
  Card, PageHead, K, Pill, Watermark, Empty, Loading, ErrorState,
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
          <span
            className="font-mono rounded-full"
            style={{
              fontSize: 9, letterSpacing: "0.5px", textTransform: "uppercase",
              padding: "3px 10px",
              background: result.meets_publish_bar ? "#1d5536" : "#efebe1",
              color: result.meets_publish_bar ? "#fff" : "#736e5f",
            }}
          >
            {result.meets_publish_bar ? "would publish" : "below publish bar"}
          </span>
        </div>

        <div className="flex items-baseline gap-4 mb-4">
          <div>
            <Mono s={9}>MODEL SCORE</Mono>
            <div className="font-serif font-bold leading-none mt-1" style={{ fontSize: 34, color: scoreColor }}>
              {result.model_score}
            </div>
          </div>
          <div>
            <Mono s={9}>SUGGESTED BET</Mono>
            <div className="font-serif font-semibold mt-1" style={{ fontSize: 16 }}>{result.bet}</div>
          </div>
        </div>

        <div className="grid grid-cols-4 border-t border-b border-border-2 mb-4">
          {[
            ["PPA GAP", result.ppa_gap != null ? `${result.ppa_gap >= 0 ? "+" : ""}${result.ppa_gap.toFixed(3)}` : "—"],
            ["SP+ GAP", result.sp_gap != null ? `${result.sp_gap >= 0 ? "+" : ""}${result.sp_gap.toFixed(1)}` : "—"],
            ["RET GAP", result.ret_gap != null ? `${result.ret_gap >= 0 ? "+" : ""}${result.ret_gap.toFixed(3)}` : "—"],
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
        {result.edges.length === 0 && result.warnings.length === 0 && (
          <Empty message="No qualifying signals for this matchup — model requires a PPA edge above 0.15 as a baseline." />
        )}

        {(result.home_coach || result.away_coach) && (
          <div className="mt-4 pt-4 border-t border-border-2">
            <Mono s={9} c="#a39d8c">COACHES</Mono>
            <div className="flex justify-between items-baseline mt-1.5" style={{ fontSize: 12.5 }}>
              <span>{result.home_coach ?? "—"} vs {result.away_coach ?? "—"}</span>
              {result.coach_h2h && (
                <Mono s={10.5} c="#736e5f">
                  H2H {result.coach_h2h.home_record}-{result.coach_h2h.away_record} ({result.coach_h2h.total} gm)
                </Mono>
              )}
            </div>
          </div>
        )}

        <div className="mt-4">
          <Mono s={8.5} c="#a39d8c">
            score_game() · prior season {result.season - 1} · NOT a probability — ordinal ranking only
          </Mono>
        </div>
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
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const r = await cfbApi.matchupLab({
        home_team: home,
        away_team: away,
        spread: parseFloat(spread),
        over_under: overUnder ? parseFloat(overUnder) : undefined,
        season: season ? parseInt(season, 10) : undefined,
      });
      setResult(r);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid gap-[22px]" style={{ gridTemplateColumns: "1fr 1.3fr" }}>
      <Card style={{ maxWidth: 420 }}>
        <K style={{ marginBottom: 14 }}>Matchup Simulator</K>
        <div className="flex flex-col gap-3">
          <div>
            <Mono s={9} c="#a39d8c">HOME TEAM</Mono>
            <select
              className="ons-input w-full mt-1"
              value={home}
              onChange={(e) => setHome(e.target.value)}
              style={{ width: "100%", padding: "7px 9px", borderRadius: 6, border: "1px solid #e6e3dc", fontSize: 13 }}
            >
              {names.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
          <div>
            <Mono s={9} c="#a39d8c">AWAY TEAM</Mono>
            <select
              className="ons-input w-full mt-1"
              value={away}
              onChange={(e) => setAway(e.target.value)}
              style={{ width: "100%", padding: "7px 9px", borderRadius: 6, border: "1px solid #e6e3dc", fontSize: 13 }}
            >
              {names.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
          <div className="flex gap-3">
            <div className="flex-1">
              <Mono s={9} c="#a39d8c">SPREAD (NEG = HOME FAV)</Mono>
              <input
                className="ons-input w-full mt-1"
                value={spread}
                onChange={(e) => setSpread(e.target.value)}
                style={{ width: "100%", padding: "7px 9px", borderRadius: 6, border: "1px solid #e6e3dc", fontSize: 13 }}
              />
            </div>
            <div className="flex-1">
              <Mono s={9} c="#a39d8c">OVER/UNDER</Mono>
              <input
                className="ons-input w-full mt-1"
                value={overUnder}
                onChange={(e) => setOverUnder(e.target.value)}
                style={{ width: "100%", padding: "7px 9px", borderRadius: 6, border: "1px solid #e6e3dc", fontSize: 13 }}
              />
            </div>
          </div>
          <div>
            <Mono s={9} c="#a39d8c">SEASON</Mono>
            <input
              className="ons-input w-full mt-1"
              value={season}
              onChange={(e) => setSeason(e.target.value)}
              style={{ width: "100%", padding: "7px 9px", borderRadius: 6, border: "1px solid #e6e3dc", fontSize: 13 }}
            />
            <p className="text-faint mt-1.5 mb-0" style={{ fontSize: 10.5, lineHeight: 1.4 }}>
              Model uses prior-season stats (season − 1) — walk-forward, no lookahead.
            </p>
          </div>
          <button
            className="ons-tap cursor-pointer mt-1"
            onClick={run}
            disabled={loading || !home || !away}
            style={{
              padding: "10px 0", borderRadius: 8, border: "none",
              background: loading ? "#a39d8c" : "#1d5536", color: "#fff",
              fontSize: 13, fontWeight: 600,
            }}
          >
            {loading ? "Scoring…" : "Run Model"}
          </button>
        </div>
      </Card>

      <div>
        {error && <ErrorState message={error} />}
        {!error && !result && (
          <Card>
            <Empty
              message="Pick two teams and run the model."
              detail="Calls the real score_game() walk-forward model directly — no simplified approximation."
            />
          </Card>
        )}
        {result && "error" in result && (
          <Card accent>
            <K color="#a8473a" style={{ marginBottom: 8 }}>
              {result.error === "no_advanced_stats" ? "No data for this matchup" : "Request failed"}
            </K>
            <p style={{ fontSize: 13, lineHeight: 1.5 }}>{result.message}</p>
          </Card>
        )}
        {result && !("error" in result) && <MatchupResultCard result={result} />}
      </div>
    </div>
  );
}

function ScheduleGameRow({ g, showDateHeader }: { g: CfbScheduleGame; showDateHeader?: string }) {
  const time = g.start_date
    ? new Date(g.start_date).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })
    : "TBD";
  return (
    <>
      {showDateHeader && (
        <div
          className="font-mono uppercase text-faint"
          style={{ fontSize: 8.5, letterSpacing: "1px", padding: "12px 6px 4px" }}
        >
          {showDateHeader}
        </div>
      )}
      <div className="ons-row flex items-center gap-3 border-t border-border-2" style={{ padding: "11px 6px", margin: "0 -6px" }}>
        <span className="font-mono text-faint shrink-0" style={{ fontSize: 10, width: 56 }}>{time}</span>
        <div className="flex-1 flex items-center gap-2 min-w-0">
          <Crest name={g.away_team} size={20} />
          <span className="truncate" style={{ fontSize: 13.5 }}>{g.away_team}</span>
          <span className="text-faint shrink-0" style={{ fontSize: 13.5 }}>@</span>
          <Crest name={g.home_team} size={20} />
          <span className="truncate" style={{ fontSize: 13.5 }}>{g.home_team}</span>
        </div>
        {g.conference_game && (
          <span className="font-mono text-faint shrink-0" style={{ fontSize: 8.5 }}>CONF</span>
        )}
        {g.neutral_site && (
          <span className="font-mono text-faint shrink-0" style={{ fontSize: 8.5 }}>NEUTRAL</span>
        )}
      </div>
    </>
  );
}

// ── ScheduleColumn — right column of "This Week" ─────────────────────────────
// Same schedule-fetching logic that used to live inside Slate(), now a
// standalone column that receives season/week as props instead of owning
// that state itself, so PicksColumn (left column) can share the exact same
// selection and the two stay in sync.

function ScheduleColumn({
  season, week, onWeekChange, onSeasonChange,
}: {
  season: number; week: number;
  onWeekChange: (w: number) => void;
  onSeasonChange: (s: number) => void;
}) {
  const now = new Date();
  const [games, setGames] = useState<CfbScheduleGame[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(null);
    cfbApi.schedule(season, week)
      .then(setGames)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [season, week]);

  // CFBD's /games endpoint doesn't guarantee chronological order — confirmed
  // 2026-06-29, the raw response mixes 10am/1pm/5pm/6pm/8pm games with no
  // consistent pattern. Sort ascending by kickoff time for display; games
  // with no start_date (TBD) sort last rather than colliding with real
  // times at an arbitrary position.
  const sortedGames = games
    ? [...games].sort((a, b) => {
        if (!a.start_date && !b.start_date) return 0;
        if (!a.start_date) return 1;
        if (!b.start_date) return -1;
        return new Date(a.start_date).getTime() - new Date(b.start_date).getTime();
      })
    : null;

  return (
    <Card pad={0}>
      <div className="flex justify-between items-center" style={{ padding: "16px 18px 12px" }}>
        <K>Schedule · {season} Week {week}</K>
        <div className="flex items-center gap-2">
          <select
            value={week}
            onChange={(e) => onWeekChange(parseInt(e.target.value, 10))}
            style={{ padding: "5px 8px", borderRadius: 6, border: "1px solid #e6e3dc", fontSize: 12 }}
          >
            {Array.from({ length: 15 }, (_, i) => i + 1).map((w) => (
              <option key={w} value={w}>Week {w}</option>
            ))}
          </select>
          <select
            value={season}
            onChange={(e) => onSeasonChange(parseInt(e.target.value, 10))}
            style={{ padding: "5px 8px", borderRadius: 6, border: "1px solid #e6e3dc", fontSize: 12 }}
          >
            {[now.getFullYear(), now.getFullYear() + 1].map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
      </div>
      <div style={{ padding: "0 18px 14px" }}>
        {loading ? (
          <Loading label="Fetching schedule from CFBD…" />
        ) : error ? (
          <ErrorState message={error} />
        ) : !sortedGames || sortedGames.length === 0 ? (
          <Empty
            message={`No games found for ${season} Week ${week}.`}
            detail="Either CFBD hasn't published this far-out week yet, or CFBD_API_TOKEN isn't set in .env — both are normal, not errors. Schedule is independent of betting lines, so it can populate before sportsbooks post Week 1 spreads."
          />
        ) : (
          sortedGames.map((g, i) => {
            // Show a date header before the first game of each new calendar
            // day (in the viewer's local time, matching how `time` itself is
            // displayed) -- otherwise two correctly-sorted games on different
            // days both show a bare time like "5:00 PM" with nothing to tell
            // them apart, which looks shuffled even though it isn't. CFBD's
            // "Week 1" genuinely spans multiple days (Thu-Wed), so this isn't
            // an edge case -- it's the normal shape of the data.
            const dayKey = g.start_date
              ? new Date(g.start_date).toDateString()
              : "tbd";
            const prevDayKey = i > 0
              ? (sortedGames[i - 1].start_date
                  ? new Date(sortedGames[i - 1].start_date as string).toDateString()
                  : "tbd")
              : null;
            const isNewDay = dayKey !== prevDayKey;
            const dateLabel = g.start_date
              ? new Date(g.start_date).toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" })
              : "Date TBD";
            return (
              <ScheduleGameRow
                key={g.game_id}
                g={g}
                showDateHeader={isNewDay ? dateLabel : undefined}
              />
            );
          })
        )}
      </div>
      <div style={{ padding: "0 18px 14px" }}>
        <p className="font-mono text-faint m-0" style={{ fontSize: 8.5, lineHeight: 1.5 }}>
          SCHEDULE ONLY — NO BETTING LINES YET. USE MATCHUP LAB TO SCORE ANY OF THESE GAMES ONCE YOU HAVE A REAL SPREAD.
        </p>
      </div>
    </Card>
  );
}

// ── PicksColumn — left column of "This Week" ─────────────────────────────────
//
// Renders data/bets/todays_picks.json via GET /cfb/picks. Takes the SAME
// season/week selection as ScheduleColumn so the two columns always agree
// on which week is being viewed.
//
// IMPORTANT, real constraint (confirmed 2026-06-29): todays_picks.json
// holds exactly ONE week's picks at a time — it's overwritten every run,
// with no history directory and no results-grading step anywhere in the
// codebase yet. So "show me last week's picks" or "show me what the model
// said 3 weeks ago" isn't something this can honestly do right now — that
// data doesn't exist on disk. What this CAN honestly do is compare the
// fetched picks' own (season, week) against what's selected in the
// dropdowns, and say clearly which of three states we're in:
//   1. selected week matches the picks file → show the real picks
//   2. selected week is earlier than the picks file's week → past week,
//      not archived (archival is planned, not yet built)
//   3. selected week is later than the picks file's week → future week,
//      picks haven't been generated yet
// This is a deliberately honest stand-in for the real archive/grading
// system, not a feature in itself — see ROADMAP.md.

function PickCard({ p }: { p: CfbPick }) {
  const isTierRisk = p.bet_type === "FADE_TIER_RISK";
  const accentColor = isTierRisk ? "#9a6a1e" : "#1d5536";
  const [awayName, homeName] = p.matchup.split(" @ ");

  return (
    <Card accent accentColor={accentColor} style={{ position: "relative", overflow: "hidden" }}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <Crest name={awayName} size={20} />
          <span className="truncate font-serif font-bold" style={{ fontSize: 15 }}>{p.matchup}</span>
          <Crest name={homeName} size={20} />
        </div>
        <span className="font-mono shrink-0" style={{ fontSize: 13, color: accentColor }}>
          {p.stars} {p.model_score}%
        </span>
      </div>

      <div className="flex items-baseline justify-between mb-2 flex-wrap gap-1">
        <span style={{ fontSize: 14, fontWeight: 600 }}>{p.bet}</span>
        <Mono s={10.5}>
          {p.line}{p.ou && p.ou !== "N/A" ? ` · O/U ${p.ou}` : ""}
        </Mono>
      </div>

      {isTierRisk && (
        // FIXED 2026-06-29: this used to read "FADE — betting against the
        // favorite," which was true under the old (buggy) reversal logic
        // but is false now -- the bet above IS on the STRONG_FADE-tiered
        // team, this is a risk note about that team's own history, not a
        // description of a different bet.
        <Mono s={9} c={accentColor}>⚠ Bet is on a team with a STRONG_FADE historical tier in this situation</Mono>
      )}

      <p className="text-muted" style={{ fontSize: 12, lineHeight: 1.5, margin: "8px 0 0" }}>
        {p.edge}
      </p>

      {p.warnings.length > 0 && (
        <div className="flex flex-col gap-1 mt-2">
          {p.warnings.map((w, i) => (
            <Mono key={i} s={10} c="#9a6a1e">⚠️ {w}</Mono>
          ))}
        </div>
      )}
    </Card>
  );
}

function PicksColumn({ season, week }: { season: number; week: number }) {
  const [picks, setPicks] = useState<CfbPick[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    cfbApi.picks().then(setPicks).catch((e) => setError(e.message));
  }, []);

  // Picks file has no season/week selector server-side — it's always
  // "whatever generate_picks.py last wrote." So we fetch once and compare
  // client-side against the selected (season, week) rather than refetching
  // per-selection — there's only ever one version to fetch anyway.
  const picksWeek = picks?.[0]?.week;
  const picksSeason = picks?.[0]?.season;
  const matchesSelection =
    picks && picks.length > 0 &&
    picksWeek === week &&
    (picksSeason == null || picksSeason === season); // tolerate older files with no season field

  let mismatchReason: "past" | "future" | null = null;
  if (picks && picks.length > 0 && !matchesSelection && picksWeek != null) {
    mismatchReason = week < (picksWeek as number) ? "past" : "future";
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-3">
        <K color="#1d5536">
          {picks && picks.length > 0
            ? `Picks · ${picksSeason ?? season} Week ${picksWeek}`
            : "This Week's Picks"}
          {" "}· model v3 walk-forward
        </K>
      </div>
      {error ? (
        <ErrorState message={error} />
      ) : !picks ? (
        <Loading label="Loading picks…" />
      ) : picks.length === 0 ? (
        <Card>
          <Empty
            message="No qualifying picks yet."
            detail="Either lines haven't posted for this week, or nothing clears the model's publish threshold (model_score ≥ 70, n_edges ≥ 4) — that's the model correctly saying 'no strong signal,' not missing data."
          />
        </Card>
      ) : mismatchReason === "past" ? (
        <Card>
          <Empty
            message={`No archived picks for ${season} Week ${week}.`}
            detail="Picks aren't archived per-week yet — only the current week's picks are kept on disk, and they get overwritten each time the model re-runs. A real history/grading system is planned but not built (see ROADMAP.md)."
          />
        </Card>
      ) : mismatchReason === "future" ? (
        <Card>
          <Empty
            message={`${season} Week ${week} is too far out — no picks yet.`}
            detail={`The model hasn't run for this week. Current picks on file are for ${picksSeason ?? season} Week ${picksWeek}.`}
          />
        </Card>
      ) : (
        <div className="flex flex-col gap-3">
          {picks.map((p, i) => <PickCard key={`${p.matchup}-${i}`} p={p} />)}
        </div>
      )}
    </div>
  );
}

function Slate() {
  const now = new Date();
  // CFB season runs Aug-Jan; if we're in the Jan-July off-season window,
  // default to the upcoming season's year rather than the current
  // calendar year, since "this year's season" hasn't started yet.
  const defaultSeason = now.getMonth() < 7 ? now.getFullYear() : now.getFullYear();
  const [season, setSeason] = useState(defaultSeason);
  const [week, setWeek] = useState(1);

  return (
    <div className="grid gap-[22px]" style={{ gridTemplateColumns: "1fr 1fr" }}>
      <PicksColumn season={season} week={week} />
      <ScheduleColumn
        season={season}
        week={week}
        onWeekChange={setWeek}
        onSeasonChange={setSeason}
      />
    </div>
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

      {tab === "slate" && <Slate />}
      {tab === "lab" && <MatchupLab teams={teams} />}
      {tab === "teams" && <TeamsView teams={teams} />}
    </div>
  );
}
