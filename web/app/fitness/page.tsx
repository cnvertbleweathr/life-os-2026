"use client";

import { useEffect, useState } from "react";
import { fitnessApi, type FitnessSummary } from "@/lib/api";
import {
  Card,
  PageHeader,
  SectionLabel,
  StatCard,
  Empty,
  Loading,
  ErrorState,
} from "@/components/ui/primitives";

function formatRunDate(iso: string): string {
  // run_date is a full ISO timestamp — slice to date portion for display
  return iso.slice(0, 10);
}

export default function FitnessPage() {
  const [data, setData]   = useState<FitnessSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fitnessApi
      .summary()
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!data) return <Loading />;

  const { running_summary: rs, recent_runs, weekly_miles } = data;
  const maxWeek = Math.max(1, ...weekly_miles.map((w) => w.miles));

  return (
    <div>
      <PageHeader title="Fitness" sub="Running, via Strava" />
      <div className="p-6 space-y-6">
        <div className="grid grid-cols-4 gap-3">
          <StatCard label="YTD miles" value={rs.ytd_miles} unit="mi" accent />
          <StatCard label="Total runs" value={rs.total_runs} />
          <StatCard label="Avg pace" value={rs.avg_pace_min_mile} unit="min/mi" />
          <StatCard label="Total miles" value={rs.total_miles} unit="mi" />
        </div>

        <div className="grid grid-cols-3 gap-4">
          <Card className="col-span-2">
            <SectionLabel>Weekly miles</SectionLabel>
            {weekly_miles.length === 0 ? (
              <Empty message="No weekly data yet." />
            ) : (
              <div className="flex items-end gap-1.5 h-32 mt-3">
                {weekly_miles.map((w) => (
                  <div key={w.week} className="flex-1 h-full flex flex-col justify-end items-center gap-1">
                    <div
                      className="w-full bg-green/70 rounded-t-sm"
                      style={{ height: `${Math.max(4, (w.miles / maxWeek) * 100)}%` }}
                      title={`${w.week}: ${w.miles}mi`}
                    />
                    <span className="text-2xs text-faint rotate-0">{w.miles}</span>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card>
            <SectionLabel>Recent runs</SectionLabel>
            {recent_runs.length === 0 ? (
              <Empty message="No recent runs." />
            ) : (
              <div className="divide-y divide-border">
                {recent_runs.map((r, i) => (
                  <div key={i} className="py-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[13px] text-ink">{formatRunDate(r.run_date)}</span>
                      <span className="text-[13px] tabular-nums text-green font-semibold">
                        {r.miles.toFixed(2)} mi
                      </span>
                    </div>
                    <p className="text-2xs text-faint">
                      {r.minutes.toFixed(0)} min · {r.pace.toFixed(1)} min/mi
                    </p>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
