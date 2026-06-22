"use client";

import { useState } from "react";
import teamIds from "@/lib/cfb_team_ids.json";

/**
 * TeamLogo — renders a team's logo from the locally downloaded set
 * (web/public/logos/{id}.png), served by download_cfb_logos.py.
 *
 * 260/263 teams have a logo locally as of the last download run.
 * 3 known 404s from CFBD's CDN (small/FCS programs without logo art).
 * Falls back to a text badge with the team's initial rather than a
 * broken image icon when no logo exists or the file fails to load.
 */

const TEAM_IDS = teamIds as Record<string, number>;

const SIZE_CLASSES = {
  sm: "w-5 h-5",
  md: "w-7 h-7",
  lg: "w-10 h-10",
} as const;

export function TeamLogo({
  team,
  size = "md",
  px,
  className,
}: {
  team: string;
  size?: keyof typeof SIZE_CLASSES;
  /** Almanac addition: exact pixel size, overrides the size keyword's class
   *  when present (used for the team profile header, matchup crests, etc.) */
  px?: number;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  const id = TEAM_IDS[team];
  const sizeClass = px ? "" : SIZE_CLASSES[size];
  const pxStyle = px ? { width: px, height: px } : undefined;

  if (!id || failed) {
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
      src={`/logos/${id}.png`}
      alt={`${team} logo`}
      title={team}
      onError={() => setFailed(true)}
      className={`${sizeClass} object-contain shrink-0 ${className ?? ""}`}
      style={pxStyle}
    />
  );
}
