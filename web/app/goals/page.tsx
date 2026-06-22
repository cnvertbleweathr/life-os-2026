"use client";

import { useEffect, useState } from "react";
import { goalsApi, type Goal } from "@/lib/api";
import {
  Card, PageHead, Stat, StatBand, K, Pace, Loading, ErrorState,
} from "@/components/ui/primitives";
import { OnsIcon } from "@/components/ui/icons";

interface DomainGroup {
  domain: string;
  goals: Goal[];
}

const DOMAIN_ICON: Record<string, string> = {
  fitness: "fitness",
  professional: "goals",
  personal: "reading",
  finance: "goals",
  family: "checkin",
};

function paceColor(status?: string | null): string {
  if (status === "behind") return "#a8473a";
  if (status === "at_risk") return "#9a6a1e";
  if (status === "unknown" || status === "binary") return "#a39d8c";
  return "#1d5536";
}

export default function GoalsPage() {
  const [groups, setGroups] = useState<DomainGroup[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    goalsApi.byDomain().then(setGroups).catch((e) => setError(e.message));
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!groups) return <Loading />;

  const all = groups.flatMap((g) => g.goals);
  const tracked = all.filter(
    (g) => g.goal_value_type !== "str" && g.progress_percent != null
  );
  const onTrack = tracked.filter(
    (g) =>
      g.pace_status === "on_track" ||
      g.pace_status === "ahead" ||
      g.pace_status === "complete"
  ).length;
  const avg = tracked.length
    ? Math.round(tracked.reduce((s, g) => s + (g.progress_percent ?? 0), 0) / tracked.length)
    : 0;

  return (
    <div className="ons-page" style={{ padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" }}>
      <PageHead
        title="Goals"
        kicker="2026 annual goals · by domain"
        right={
          <div className="font-mono text-right text-faint" style={{ fontSize: 9.5 }}>
            WHAT-IF PROJECTIONS<br />LIVE ON SCENARIOS →
          </div>
        }
      />

      <StatBand>
        <Stat label="Goals Tracked" value={all.length} />
        <Stat label="On / Ahead" value={`${onTrack}/${tracked.length}`} accent={onTrack > 0} />
        <Stat label="Avg Progress" value={avg} unit="%" />
        <Stat label="Domains" value={groups.length} last />
      </StatBand>

      <div className="grid gap-[22px] items-start" style={{ gridTemplateColumns: "1fr 1fr" }}>
        {groups.map((grp) => (
          <Card key={grp.domain} pad={0}>
            <div
              className="flex items-center gap-[9px] border-b border-border-2"
              style={{ padding: "16px 18px 12px" }}
            >
              <span className="text-green flex">
                <OnsIcon
                  name={DOMAIN_ICON[grp.domain.toLowerCase()] ?? "goals"}
                  size={17}
                  stroke={1.6}
                />
              </span>
              <K color="#232a22" style={{ fontSize: 11, letterSpacing: "1.5px" }}>
                {grp.domain}
              </K>
              <span className="ml-auto font-mono text-faint" style={{ fontSize: 9 }}>
                {grp.goals.length} GOALS
              </span>
            </div>
            <div style={{ padding: "4px 18px 14px" }}>
              {grp.goals.map((g) => {
                const col = paceColor(g.pace_status);
                const isStr = g.goal_value_type === "str";
                const pct = g.progress_percent;

                return (
                  <div key={g.goal_key} style={{ padding: "14px 0", borderTop: "1px solid #ebe5d8" }}>
                    <div className="flex justify-between items-baseline gap-3">
                      <span style={{ fontSize: 13.5, fontWeight: 500 }}>{g.label}</span>
                      <Pace status={g.pace_status} />
                    </div>
                    {g.description && (
                      <div className="text-faint mt-0.5" style={{ fontSize: 11 }}>{g.description}</div>
                    )}

                    {isStr ? (
                      <div className="font-mono text-faint italic mt-[9px]" style={{ fontSize: 10.5 }}>
                        Not numerically tracked
                      </div>
                    ) : pct == null ? (
                      <div className="flex items-center gap-[7px] mt-[9px] font-mono text-muted" style={{ fontSize: 10.5 }}>
                        <span className="rounded-full" style={{ width: 6, height: 6, background: "#1d5536" }} />
                        Logged when it happens
                      </div>
                    ) : (
                      <>
                        <div className="flex justify-between items-baseline font-mono mt-[10px] mb-[6px]" style={{ fontSize: 11.5 }}>
                          <span className="text-muted">
                            {g.current_value ?? "—"}
                            <span className="text-faint"> / {g.target_numeric ?? "—"}</span>
                          </span>
                          <span style={{ color: col, fontWeight: 600 }}>
                            {Math.round(pct)}%
                          </span>
                        </div>
                        <div className="rounded overflow-hidden" style={{ height: 4, background: "#efebe1" }}>
                          <div
                            className="rounded"
                            style={{
                              width: `${Math.min(100, pct)}%`,
                              height: "100%",
                              background: col,
                              transition: "width .6s",
                            }}
                          />
                        </div>
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
