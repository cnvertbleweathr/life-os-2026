"use client";

// Site-wide CFB Live Tracker banner -- lives in app/layout.tsx, above
// {children}, so it's visible on every page.
//
// Updated 2026-06-29: now backed by real data. mart_live_picks (built from
// data/bets/history/*.json via pipelines/live_picks_pipeline.py +
// grade_picks.py) exists, so "Graded Picks / Record / Win Rate / ROI" are
// real numbers, not placeholders -- they'll correctly show 0/0-0/—/— until
// the season starts and games get graded, which is the honest state, not
// a bug.
//
// win_rate_pct/total_pnl/roi_pct are null (not 0) from the API when
// graded_picks is 0 -- rendered as em-dashes, matching the original
// design's distinction between "no data yet" and "0%."

import { useEffect, useState } from "react";
import { cfbApi, type CfbLiveTracker, type CfbPicksSummary } from "@/lib/api";

export function LiveTrackerBanner() {
  const [tracker, setTracker] = useState<CfbLiveTracker | null>(null);
  const [summary, setSummary] = useState<CfbPicksSummary | null>(null);

  useEffect(() => {
    cfbApi.liveTracker().then(setTracker).catch(() => setTracker(null));
    cfbApi.picksSummary().then(setSummary).catch(() => setSummary(null));
  }, []);

  const isPreseason = !tracker || tracker.graded_picks === 0;

  const weekLabel =
    summary && summary.count > 0 && summary.week != null
      ? ` · ${summary.count} qualifying pick${summary.count === 1 ? "" : "s"} this week`
      : "";

  const pendingLabel =
    tracker && tracker.pending_picks > 0
      ? ` · ${tracker.pending_picks} pending`
      : "";

  return (
    <div
      style={{
        borderBottom: "1px solid #e6e3dc",
        background: "#fbfaf5",
        padding: "10px 28px",
      }}
    >
      <div
        className="flex justify-between items-center mx-auto"
        style={{ maxWidth: 1380 }}
      >
        <div className="flex items-baseline gap-[18px] flex-wrap">
          <span
            className="font-mono uppercase"
            style={{ fontSize: 9.5, letterSpacing: "1.7px", color: "#1d5536" }}
          >
            {tracker?.season ?? new Date().getFullYear()} Season · Live Tracker
          </span>
          {isPreseason && (
            <span
              className="font-mono"
              style={{
                fontSize: 9,
                color: "#9a6a1e",
                border: "1px solid rgba(154,106,30,0.33)",
                borderRadius: 999,
                padding: "2px 9px",
              }}
            >
              PRESEASON
            </span>
          )}
          <StatInline label="Graded Picks" value={String(tracker?.graded_picks ?? 0)} />
          <StatInline
            label="Record"
            value={tracker ? `${tracker.wins}–${tracker.losses}${tracker.pushes ? `–${tracker.pushes}` : ""}` : "0–0"}
          />
          <StatInline
            label="Win Rate"
            value={tracker?.win_rate_pct != null ? `${tracker.win_rate_pct}%` : "—"}
          />
          <StatInline
            label="ROI"
            value={tracker?.roi_pct != null ? `${tracker.roi_pct > 0 ? "+" : ""}${tracker.roi_pct}%` : "—"}
          />
        </div>
        <span className="font-mono text-faint" style={{ fontSize: 9 }}>
          MODEL: 107–32 · 77.0% · +47.0% ROI (134 BETS, 5/5 SEASONS){weekLabel}{pendingLabel}
        </span>
      </div>
    </div>
  );
}

function StatInline({ label, value }: { label: string; value: string }) {
  return (
    <span className="flex items-baseline gap-[6px]">
      <span className="font-mono uppercase text-faint" style={{ fontSize: 8.5, letterSpacing: "1px" }}>
        {label}
      </span>
      <span className="font-serif font-semibold" style={{ fontSize: 13, color: "#232a22" }}>
        {value}
      </span>
    </span>
  );
}
