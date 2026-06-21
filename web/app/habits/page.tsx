"use client";

import { useEffect, useState } from "react";
import { habitsApi, type HabitToday, type HabitStreak } from "@/lib/api";
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

export default function HabitsPage() {
  const [today, setToday]     = useState<HabitToday | null>(null);
  const [streaks, setStreaks] = useState<HabitStreak[] | null>(null);
  const [error, setError]     = useState<string | null>(null);

  useEffect(() => {
    Promise.all([habitsApi.today(), habitsApi.streaks()])
      .then(([t, s]) => {
        setToday(t);
        setStreaks(s);
      })
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!today || !streaks) return <Loading />;

  return (
    <div>
      <PageHeader title="Habits" sub={today.date} />
      <div className="p-6 space-y-6">
        <div className="grid grid-cols-4 gap-3">
          <StatCard label="Done today" value={`${today.done_count}/${today.total_count}`} accent />
          <StatCard
            label="Longest streak"
            value={Math.max(0, ...streaks.map((s) => s.longest_streak))}
            unit="days"
          />
          <StatCard
            label="Active streaks"
            value={streaks.filter((s) => s.current_streak > 0).length}
          />
          <StatCard label="Tracked habits" value={today.total_count} />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Card>
            <SectionLabel>Today</SectionLabel>
            {today.habits.length === 0 ? (
              <Empty message="No habits configured." />
            ) : (
              <div className="space-y-2">
                {today.habits.map((h) => (
                  <div key={h.key} className="flex items-center gap-2.5">
                    <span
                      className={clsx(
                        "w-4 h-4 rounded-sm border flex items-center justify-center text-2xs",
                        h.done
                          ? "bg-green border-green text-white"
                          : "border-border text-transparent"
                      )}
                    >
                      ✓
                    </span>
                    <span className={clsx("text-[13px]", h.done ? "text-ink" : "text-muted")}>
                      {h.label}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card>
            <SectionLabel>Streaks</SectionLabel>
            {streaks.length === 0 ? (
              <Empty message="No streak data yet." />
            ) : (
              <div className="divide-y divide-border">
                {streaks.map((s) => (
                  <div key={s.habit} className="flex items-center justify-between py-2">
                    <span className="text-[13px] text-ink">{s.habit.replace(/_/g, " ")}</span>
                    <div className="text-right">
                      <span className="text-[13px] tabular-nums text-green font-semibold">
                        {s.current_streak}
                      </span>
                      <span className="text-2xs text-faint ml-1">
                        (best {s.longest_streak})
                      </span>
                    </div>
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
