"use client";

import { useState } from "react";
import mlbLogos from "@/lib/mlb_team_logos.json";
import nbaLogos from "@/lib/nba_team_logos.json";
import nflLogos from "@/lib/nfl_team_logos.json";
import nhlLogos from "@/lib/nhl_team_logos.json";

/**
 * ProTeamLogo — renders an MLB/NBA/NFL team's logo from the locally
 * downloaded set (web/public/logos/{league}/{filename}), served by
 * scripts/download_pro_logos.py.
 *
 * Source repo (klunn91/team-logos) is from 2019 — MLB Guardians resolves
 * to indians.png, NFL Commanders resolves to redskins.png. The maps below
 * already point current team names at the old filenames, so callers never
 * need to know about this.
 *
 * MLB/NBA/NFL come from that download; NHL from web/public/logos/nhl (keyed by
 * full team name in lib/nhl_team_logos.json). MLS has no logo source and always
 * renders the initial-letter fallback.
 */

const MAPS: Record<string, Record<string, string>> = {
  mlb: mlbLogos,
  nba: nbaLogos,
  nfl: nflLogos,
  nhl: nhlLogos,
};

const SIZE_CLASSES = {
  sm: "w-5 h-5",
  md: "w-7 h-7",
  lg: "w-10 h-10",
} as const;

export function ProTeamLogo({
  league,
  team,
  size = "md",
  px,
  className,
}: {
  /** Lowercase league key: "mlb" | "nba" | "nfl" | "nhl". MLS falls back to
   *  the initial-letter badge — no logo source exists yet. */
  league: string;
  team: string;
  size?: keyof typeof SIZE_CLASSES;
  px?: number;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  const map = MAPS[league.toLowerCase()];
  const filename = map?.[team];
  const sizeClass = px ? "" : SIZE_CLASSES[size];
  const pxStyle = px ? { width: px, height: px } : undefined;

  if (!filename || failed) {
    return (
      <span
        className={`${sizeClass} rounded-full bg-canvas border border-border flex items-center justify-center text-2xs font-semibold text-faint shrink-0 ${className ?? ""}`}
        style={pxStyle}
        title={team}
      >
        {team.charAt(0)}
      </span>
    );
  }

  return (
    <img
      src={`/logos/${league.toLowerCase()}/${filename}`}
      alt={`${team} logo`}
      title={team}
      onError={() => setFailed(true)}
      className={`${sizeClass} object-contain shrink-0 ${className ?? ""}`}
      style={pxStyle}
    />
  );
}
