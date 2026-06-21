"use client";

import { useEffect, useState } from "react";
import { homeApi, type HomeSummary } from "@/lib/api";
import {
  Card,
  PageHeader,
  SectionLabel,
  StatCard,
  Empty,
  Loading,
  ErrorState,
  PaceBadge,
} from "@/components/ui/primitives";

export default function HomePage() {
  const [data, setData]   = useState<HomeSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    homeApi
      .summary()
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!data) return <Loading label="Loading today's summary..." />;

  const { stat_cards, calendar, wod, daily10, goals } = data;

  return (
    <div>
      <PageHeader title="Home" sub={data.date} />

      <div className="p-6 space-y-6">
        {/* Stat row */}
        <div className="grid grid-cols-6 gap-3">
          <StatCard label="Weekly miles" value={stat_cards.weekly_miles} unit="mi" accent />
          <StatCard label="Weekly runs" value={stat_cards.weekly_runs} />
          <StatCard label="YTD miles" value={stat_cards.ytd_miles} unit="mi" accent />
          <StatCard
            label="Habits today"
            value={`${stat_cards.habits_done}/${stat_cards.habits_total}`}
          />
          <StatCard label="Books read" value={stat_cards.books_read} />
          <StatCard label="Date" value={data.date} />
        </div>

        <div className="grid grid-cols-3 gap-4">
          {/* Calendar */}
          <Card>
            <SectionLabel>This week</SectionLabel>
            {calendar.length === 0 ? (
              <Empty message="Nothing on the calendar this week." />
            ) : (
              <div className="space-y-1.5">
                {calendar.map((e, i) => (
                  <div key={i} className="flex items-center justify-between text-[13px]">
                    <span className="text-ink">{e.title}</span>
                    <span className="text-faint text-xs">{e.date}</span>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* WOD */}
          <Card>
            <SectionLabel>Today's WOD</SectionLabel>
            {!wod || !wod.fetched_ok ? (
              <Empty message="No WOD fetched yet today." />
            ) : (
              <div>
                <p className="text-[13px] text-ink whitespace-pre-line">{wod.text}</p>
                {wod.movements.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {wod.movements.map((m, i) => (
                      <span
                        key={i}
                        className="text-2xs bg-canvas border border-border rounded-full px-2 py-0.5 text-muted"
                      >
                        {m}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </Card>

          {/* Daily 10 */}
          <Card>
            <SectionLabel>Daily 10</SectionLabel>
            {!daily10 ? (
              <Empty message="No playlist generated yet today." />
            ) : (
              <div>
                <p className="text-[13px] text-ink">{daily10.description}</p>
                {daily10.tewnidge_artists?.length > 0 && (
                  <p className="text-xs text-faint mt-2">
                    Featuring: {daily10.tewnidge_artists.slice(0, 3).join(", ")}
                  </p>
                )}
              </div>
            )}
          </Card>
        </div>

        {/* Goals */}
        <Card>
          <SectionLabel>Goal pacing</SectionLabel>
          {goals.length === 0 ? (
            <Empty message="No goals tracked yet." />
          ) : (
            <div className="divide-y divide-border">
              {goals.map((g) => (
                <div key={g.goal_key} className="flex items-center justify-between py-2">
                  <div>
                    <p className="text-[13px] text-ink">{g.label}</p>
                    <p className="text-2xs text-faint">{g.domain}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-[13px] tabular-nums text-muted">
                      {g.current_value ?? "—"}
                      {g.target_numeric != null && ` / ${g.target_numeric}`}
                    </span>
                    <PaceBadge status={g.pace_status} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
