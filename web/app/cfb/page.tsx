"use client";

import { useEffect, useState } from "react";
import { cfbApi, type CfbTeam } from "@/lib/api";
import { TeamLogo } from "@/components/ui/TeamLogo";
import {
  Card,
  PageHeader,
  SectionLabel,
  StatCard,
  Empty,
  Loading,
  ErrorState,
} from "@/components/ui/primitives";
import clsx from "clsx";

const TIER_COLOR: Record<string, string> = {
  elite:    "text-green",
  strong:   "text-green-light",
  average:  "text-muted",
  weak:     "text-amber",
  poor:     "text-red",
};

export default function CfbPage() {
  const [teams, setTeams]   = useState<CfbTeam[] | null>(null);
  const [error, setError]   = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<"roi_pct" | "win_rate">("roi_pct");

  useEffect(() => {
    cfbApi
      .teams()
      .then(setTeams)
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!teams) return <Loading />;

  const sorted = [...teams].sort((a, b) => (b[sortBy] ?? 0) - (a[sortBy] ?? 0));
  const profitable = teams.filter((t) => t.seasons_profitable >= 3);

  return (
    <div>
      <PageHeader title="CFB Betting" sub="The Degenerates Corner — walk-forward validated" />
      <div className="p-6 space-y-6">
        {/* Validated model summary — static facts, not from API */}
        <div className="grid grid-cols-4 gap-3">
          <StatCard label="Validated bets" value={318} />
          <StatCard label="Win rate" value="70.4%" accent />
          <StatCard label="ROI" value="+34.5%" accent />
          <StatCard label="Profitable seasons" value="4/4" />
        </div>

        <Card>
          <div className="flex items-center justify-between mb-3">
            <SectionLabel>Team performance ({teams.length} teams)</SectionLabel>
            <div className="flex gap-2">
              {(["roi_pct", "win_rate"] as const).map((key) => (
                <button
                  key={key}
                  onClick={() => setSortBy(key)}
                  className={clsx(
                    "text-2xs px-2.5 py-1 rounded-full border transition-colors",
                    sortBy === key
                      ? "bg-green text-white border-green"
                      : "border-border text-muted hover:text-ink"
                  )}
                >
                  Sort by {key === "roi_pct" ? "ROI" : "win rate"}
                </button>
              ))}
            </div>
          </div>

          {sorted.length === 0 ? (
            <Empty message="No team data available." />
          ) : (
            <div className="divide-y divide-border">
              {sorted.slice(0, 25).map((t) => (
                <div key={t.team} className="flex items-center justify-between py-2">
                  <div className="flex items-center gap-2">
                    <TeamLogo team={t.team} size="sm" />
                    <span className="text-[13px] text-ink">{t.team}</span>
                    <span
                      className={clsx(
                        "text-2xs font-medium uppercase",
                        TIER_COLOR[t.tier] ?? "text-muted"
                      )}
                    >
                      {t.tier}
                    </span>
                  </div>
                  <div className="flex items-center gap-4 text-[12px] tabular-nums">
                    <span className="text-muted">
                      {t.win_rate.toFixed(0)}% win
                    </span>
                    <span
                      className={clsx(
                        "font-semibold",
                        t.roi_pct >= 0 ? "text-green" : "text-red"
                      )}
                    >
                      {t.roi_pct >= 0 ? "+" : ""}
                      {t.roi_pct.toFixed(1)}% ROI
                    </span>
                    <span className="text-faint">{t.seasons_profitable}/4 seasons</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        {profitable.length > 0 && (
          <Card>
            <SectionLabel>Consistently profitable (3+ of 4 seasons)</SectionLabel>
            <div className="flex flex-wrap gap-2">
              {profitable.map((t) => (
                <span
                  key={t.team}
                  className="flex items-center gap-1.5 text-2xs bg-green/10 text-green border border-green/20 rounded-full px-2.5 py-1"
                >
                  <TeamLogo team={t.team} size="sm" />
                  {t.team}
                </span>
              ))}
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
