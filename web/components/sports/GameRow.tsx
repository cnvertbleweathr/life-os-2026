"use client";

import { useState } from "react";
import type { Game, GameSide } from "@/lib/api";

/** ESPN CDN logo with initials fallback (covers every league, incl. NHL/MLS/CFB). */
export function TeamMark({ side, px = 22 }: { side: Pick<GameSide, "logo" | "abbr" | "name">; px?: number }) {
  const [failed, setFailed] = useState(false);
  if (!side.logo || failed) {
    return (
      <span
        className="rounded-full bg-canvas border border-border flex items-center justify-center font-semibold text-faint shrink-0"
        style={{ width: px, height: px, fontSize: Math.max(8, px * 0.36) }}
        title={side.name}
      >
        {(side.abbr || side.name).slice(0, 3)}
      </span>
    );
  }
  return (
    <img
      src={side.logo}
      alt={`${side.name} logo`}
      title={side.name}
      onError={() => setFailed(true)}
      className="object-contain shrink-0"
      style={{ width: px, height: px }}
    />
  );
}

/** "7:30 PM" today, "Thu 6:00 PM" this week, "Nov 4 · 6:00 PM" further out — in the viewer's timezone. */
export function kickoffLabel(startUtc: string | null, withDay = false): string {
  if (!startUtc) return "TBD";
  const d = new Date(startUtc);
  const time = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  if (!withDay) return time;
  const now = new Date();
  const days = Math.round((new Date(d.toDateString()).getTime() - new Date(now.toDateString()).getTime()) / 864e5);
  if (days === 0) return `Today ${time}`;
  if (days === 1) return `Tmrw ${time}`;
  if (days > 1 && days < 7) return `${d.toLocaleDateString("en-US", { weekday: "short" })} ${time}`;
  return `${d.toLocaleDateString("en-US", { month: "short", day: "numeric" })} · ${time}`;
}

export function statusLabel(g: Game, withDay = false): string {
  if (g.state === "pre") return kickoffLabel(g.start_utc, withDay);
  return g.status_detail || (g.state === "in" ? "LIVE" : "Final");
}

function Side({ side, showScore, dim }: { side: GameSide; showScore: boolean; dim: boolean }) {
  return (
    <div className="flex items-center gap-2 min-w-0" style={{ opacity: dim ? 0.55 : 1 }}>
      <TeamMark side={side} px={18} />
      <span className="truncate" style={{ fontSize: 12.5 }}>
        {side.rank ? <span className="font-mono text-faint" style={{ fontSize: 9.5 }}>{side.rank} </span> : null}
        {side.short || side.name}
      </span>
      {side.record && <span className="font-mono text-faint shrink-0" style={{ fontSize: 9 }}>{side.record}</span>}
      {showScore && (
        <span className="font-mono ml-auto shrink-0" style={{ fontSize: 13, fontWeight: side.winner ? 700 : 500 }}>
          {side.score ?? "–"}
        </span>
      )}
    </div>
  );
}

/** Two-line scoreboard row: away over home, scores right, status + TV far right. */
export function GameRow({ g, withDay = false, rank }: { g: Game; withDay?: boolean; rank?: number }) {
  const started = g.state !== "pre";
  const final = g.state === "post";
  const Wrapper = g.link ? "a" : "div";
  return (
    <Wrapper
      {...(g.link ? { href: g.link, target: "_blank", rel: "noopener noreferrer" } : {})}
      className="ons-row flex items-center gap-3 no-underline text-inherit border-t border-border-2"
      style={{ padding: "10px 6px", margin: "0 -6px", cursor: g.link ? "pointer" : "default" }}
    >
      {rank !== undefined && (
        <span className="font-serif font-bold text-faint shrink-0" style={{ fontSize: 14, width: 14 }}>{rank}</span>
      )}
      <div className="flex-1 min-w-0 flex flex-col gap-1">
        <Side side={g.away} showScore={started} dim={final && g.home.winner === true} />
        <Side side={g.home} showScore={started} dim={final && g.away.winner === true} />
      </div>
      <div className="text-right shrink-0" style={{ width: 112 }}>
        <div className="font-mono" style={{ fontSize: 10.5, color: g.is_live ? "#a8473a" : "#736e5f" }}>
          {g.is_live && "● "}
          {statusLabel(g, withDay)}
        </div>
        <div className="font-mono text-faint truncate" style={{ fontSize: 8.5, marginTop: 3 }}>
          {g.league_label}
          {g.broadcasts.length > 0 && ` · ${g.broadcasts.slice(0, 2).join(", ")}`}
        </div>
        {g.note && (
          <div className="text-faint truncate" style={{ fontSize: 9.5, marginTop: 2 }} title={g.note}>{g.note}</div>
        )}
      </div>
    </Wrapper>
  );
}

/** Single-line compact row for Home. */
export function GameLine({ g, withDay = false, label }: { g: Game; withDay?: boolean; label?: string }) {
  const started = g.state !== "pre";
  return (
    <div className="flex items-center gap-3 border-t border-border-2" style={{ padding: "9px 6px", margin: "0 -6px" }}>
      <div className="flex items-center -space-x-1.5 shrink-0">
        <TeamMark side={g.away} px={20} />
        <TeamMark side={g.home} px={20} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="truncate" style={{ fontSize: 13, fontWeight: label ? 600 : 400 }}>
          {label ?? g.short_name}
        </div>
        <div className="text-faint truncate" style={{ fontSize: 10.5 }}>
          {started
            ? `${g.away.abbr} ${g.away.score ?? "–"} · ${g.home.abbr} ${g.home.score ?? "–"}`
            : `${g.short_name}${g.broadcasts.length ? ` · ${g.broadcasts[0]}` : ""}`}
        </div>
      </div>
      <span className="font-mono shrink-0" style={{ fontSize: 9.5, color: g.is_live ? "#a8473a" : "#736e5f" }}>
        {g.is_live && "● "}
        {statusLabel(g, withDay)}
      </span>
    </div>
  );
}
