"use client";

// Site-wide top ticker -- lives in app/layout.tsx above {children}, so it's on
// every page. Replaces the static CFB LiveTrackerBanner (2026-10-28).
//
//   [ ● LIVE / THE WIRE ][ pinned live games ][ ← scrolling: scores · next · team news · headlines ← ][ CFB chip ]
//
// Data: one call to GET /api/sports/ticker (ESPN scores + team news, NewsAPI
// top headlines) and the existing CFB live-tracker endpoint. Polls every 60s
// while one of my teams is live, every 5 min otherwise, and not at all while
// the tab is hidden.
//
// The marquee is two copies of the same strip translated -50% on a loop, so
// it wraps seamlessly. Hover or keyboard focus pauses it; with
// prefers-reduced-motion it becomes a plain horizontally scrollable strip.

import Link from "next/link";
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import {
  cfbApi,
  sportsApi,
  type CfbLiveTracker,
  type GameSide,
  type SportsTicker,
  type TeamNewsArticle,
  type TickerGame,
  type TickerHeadline,
} from "@/lib/api";
import { TeamMark, kickoffLabel } from "@/components/sports/GameRow";

const SPEED_PX_PER_SEC = 42;
const POLL_LIVE_MS = 60_000;
const POLL_IDLE_MS = 5 * 60_000;

export function TopTicker() {
  const [data, setData] = useState<SportsTicker | null>(null);
  const [failed, setFailed] = useState(false);
  const [tracker, setTracker] = useState<CfbLiveTracker | null>(null);

  // ── Polling ──────────────────────────────────────────────────────────────
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let live = false;
    let cancelled = false;

    const load = async () => {
      try {
        const d = await sportsApi.ticker();
        if (cancelled) return;
        live = d.any_live;
        setData(d);
        setFailed(false);
      } catch {
        if (!cancelled) setFailed(true);
      }
      schedule();
    };
    const schedule = () => {
      clearTimeout(timer);
      if (cancelled || document.hidden) return;
      timer = setTimeout(load, live ? POLL_LIVE_MS : POLL_IDLE_MS);
    };
    const onVisible = () => {
      if (!document.hidden) load();
      else clearTimeout(timer);
    };

    load();
    cfbApi.liveTracker().then(setTracker).catch(() => setTracker(null));
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  // Live games of mine are pinned beside the label instead of scrolling away.
  const pinned = (data?.games ?? []).filter((g) => g.ticker_group === "live").slice(0, 2);
  const segments = data ? buildSegments(data, new Set(pinned.map((g) => g.id))) : [];
  const live = !!data?.any_live;

  return (
    <div className="ons-banner ons-ticker-bar" role="region" aria-label="Scores and headlines">
      <div className="ons-ticker-label">
        <span className={`ons-ticker-dot${live ? " is-live" : ""}`} aria-hidden />
        <span>{live ? "Live" : "The Wire"}</span>
      </div>

      {pinned.length > 0 && (
        <div className="ons-ticker-pinned">
          {pinned.map((g, i) => (
            <span key={g.id} className={i > 0 ? "ons-banner-extra" : undefined}>
              <GameItem g={g} />
            </span>
          ))}
        </div>
      )}

      {segments.length > 0 ? (
        <Marquee>{segments}</Marquee>
      ) : (
        <div className="ons-ticker-empty font-mono text-faint">
          {failed ? "Wire offline — couldn't reach /api/sports/ticker" : data ? "Quiet day — no games or headlines" : "Tuning in…"}
        </div>
      )}

      <CfbChip tracker={tracker} />
    </div>
  );
}

// ── Marquee ──────────────────────────────────────────────────────────────────

function Marquee({ children }: { children: ReactNode }) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [duration, setDuration] = useState<number | null>(null);

  // Speed stays constant however long the strip is. Only re-time on a real
  // length change -- every new duration makes the animation jump.
  useLayoutEffect(() => {
    const el = trackRef.current;
    if (!el) return;
    const measure = () => {
      const half = el.scrollWidth / 2;
      const next = Math.max(20, half / SPEED_PX_PER_SEC);
      setDuration((prev) => (prev && Math.abs(prev - next) / prev < 0.12 ? prev : next));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  });

  return (
    <div className="ons-ticker-viewport">
      <div
        ref={trackRef}
        className="ons-ticker-track"
        style={{ animationDuration: duration ? `${duration}s` : undefined }}
      >
        <div className="ons-ticker-copy">{children}</div>
        {/* Visual duplicate for the seamless loop: hidden from screen readers and tab order. */}
        <div className="ons-ticker-copy" aria-hidden ref={(el) => el?.setAttribute("inert", "")}>
          {children}
        </div>
      </div>
    </div>
  );
}

// ── Segments ─────────────────────────────────────────────────────────────────

function buildSegments(d: SportsTicker, pinned: Set<string>): ReactNode[] {
  const out: ReactNode[] = [];
  const scores = d.games.filter((g) => g.ticker_group !== "next" && !pinned.has(g.id));
  const next = d.games.filter((g) => g.ticker_group === "next");

  if (scores.length) {
    out.push(<Tag key="t-scores">Scores</Tag>);
    scores.forEach((g) => out.push(<GameItem key={`g-${g.id}`} g={g} />));
  }
  if (next.length) {
    out.push(<Tag key="t-next">Up next</Tag>);
    next.forEach((g) => out.push(<GameItem key={`n-${g.id}`} g={g} />));
  }
  if (d.team_news.length) {
    out.push(<Tag key="t-team">My teams</Tag>);
    d.team_news.forEach((a) => out.push(<TeamNewsItem key={`tn-${a.url}`} a={a} />));
  }
  if (d.headlines.length) {
    out.push(<Tag key="t-head">Headlines</Tag>);
    d.headlines.forEach((h) => out.push(<HeadlineItem key={`h-${h.url}`} h={h} />));
  }
  return out;
}

function Tag({ children }: { children: ReactNode }) {
  return <span className="ons-ticker-tag">{children}</span>;
}

function Item({ href, children, title }: { href: string | null; children: ReactNode; title?: string }) {
  const cls = "ons-ticker-item";
  return href ? (
    <a className={cls} href={href} target="_blank" rel="noreferrer" title={title}>
      {children}
    </a>
  ) : (
    <span className={cls} title={title}>
      {children}
    </span>
  );
}

/** Which side of a game is one of my teams (null if both or neither). */
function mySide(g: TickerGame): "home" | "away" | null {
  const mine = (g.my_team ?? "").toLowerCase().split(" / ");
  const h = mine.includes(g.home.name.toLowerCase());
  const a = mine.includes(g.away.name.toLowerCase());
  return h && !a ? "home" : a && !h ? "away" : null;
}

function GameItem({ g }: { g: TickerGame }) {
  const showScore = g.state !== "pre";
  const side = mySide(g);
  const away = Number(g.away.score);
  const home = Number(g.home.score);
  const leader = showScore && away !== home ? (away > home ? "away" : "home") : null;

  let status: ReactNode;
  if (g.state === "in") {
    status = <span className="ons-ticker-status is-live">{g.status_detail || "Live"}</span>;
  } else if (g.state === "post") {
    const result = side && leader ? (leader === side ? "W" : "L") : null;
    status = (
      <>
        {result && <span className={`ons-ticker-result is-${result === "W" ? "win" : "loss"}`}>{result}</span>}
        <span className="ons-ticker-status">{g.status_detail || "Final"}</span>
      </>
    );
  } else {
    const label = g.ticker_group === "today" ? `Tonight ${kickoffLabel(g.start_utc)}` : kickoffLabel(g.start_utc, true);
    status = (
      <span className="ons-ticker-status">
        {label}
        {g.broadcasts[0] ? ` · ${g.broadcasts[0]}` : ""}
      </span>
    );
  }

  return (
    <Item href={g.link} title={`${g.name}${g.venue ? ` — ${g.venue}` : ""}`}>
      <span className="ons-ticker-league">{g.league_label}</span>
      <Team side={g.away} score={showScore ? g.away.score : null} bold={leader === "away" || side === "away"} />
      <span className="text-faint">{showScore ? "" : "@"}</span>
      <Team side={g.home} score={showScore ? g.home.score : null} bold={leader === "home" || side === "home"} />
      {status}
    </Item>
  );
}

function Team({ side, score, bold }: { side: GameSide; score: string | null; bold: boolean }) {
  return (
    <span className="inline-flex items-center gap-[5px]">
      <TeamMark side={side} px={15} />
      <span style={{ fontWeight: bold ? 600 : 400 }}>{side.abbr || side.short}</span>
      {score != null && (
        <span className="font-serif" style={{ fontWeight: bold ? 700 : 500, fontSize: 13.5 }}>
          {score}
        </span>
      )}
    </span>
  );
}

function TeamNewsItem({ a }: { a: TeamNewsArticle }) {
  return (
    <Item href={a.url} title={a.description ?? a.title}>
      <TeamMark side={{ logo: a.team_logo, abbr: a.team_abbr ?? "", name: a.team }} px={15} />
      <span className="ons-ticker-source is-team">{a.team_abbr ?? a.team}</span>
      <span className="ons-ticker-headline">{a.title}</span>
      <Ago iso={a.published} />
    </Item>
  );
}

function HeadlineItem({ h }: { h: TickerHeadline }) {
  return (
    <Item href={h.url} title={h.title}>
      <span className="ons-ticker-source">{h.source}</span>
      <span className="ons-ticker-headline">{h.title}</span>
      <Ago iso={h.published} />
    </Item>
  );
}

function Ago({ iso }: { iso: string | null }) {
  if (!iso) return null;
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (!Number.isFinite(mins) || mins < 0) return null;
  const label = mins < 60 ? `${Math.max(1, mins)}m` : mins < 48 * 60 ? `${Math.round(mins / 60)}h` : `${Math.round(mins / 1440)}d`;
  return <span className="ons-ticker-ago">{label}</span>;
}

// ── CFB record chip (what the whole banner used to be) ──────────────────────

function CfbChip({ tracker }: { tracker: CfbLiveTracker | null }) {
  const graded = tracker?.graded_picks ?? 0;
  const record = tracker ? `${tracker.wins}–${tracker.losses}${tracker.pushes ? `–${tracker.pushes}` : ""}` : "—";
  const roi = tracker?.roi_pct != null ? `${tracker.roi_pct > 0 ? "+" : ""}${tracker.roi_pct}%` : "—";
  const title =
    `${tracker?.season ?? ""} picks: ${graded} graded` +
    (tracker?.win_rate_pct != null ? ` · ${tracker.win_rate_pct}% win rate` : "") +
    (tracker?.pending_picks ? ` · ${tracker.pending_picks} pending` : "") +
    "\nModel backtest: 107–32 · 77.0% · +47.0% ROI (134 bets, 5/5 seasons)";

  return (
    <Link href="/cfb" className="ons-ticker-cfb ons-banner-extra" title={title}>
      <span className="ons-ticker-cfb-label">CFB {tracker ? `’${String(tracker.season).slice(2)}` : ""}</span>
      {graded === 0 ? (
        <span className="ons-ticker-cfb-pre">Preseason</span>
      ) : (
        <>
          <span className="font-serif font-semibold">{record}</span>
          <span
            className="font-serif font-semibold"
            style={{ color: (tracker?.roi_pct ?? 0) >= 0 ? "#1d5536" : "#a8473a" }}
          >
            {roi}
          </span>
        </>
      )}
      {tracker && tracker.pending_picks > 0 && <span className="ons-ticker-cfb-pending">{tracker.pending_picks} pending</span>}
    </Link>
  );
}
