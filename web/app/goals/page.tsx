"use client";

import { useEffect, useState } from "react";
import { goalsApi, type GoalDomainGroup } from "@/lib/api";
import {
  Card,
  PageHeader,
  SectionLabel,
  Empty,
  Loading,
  ErrorState,
  PaceBadge,
} from "@/components/ui/primitives";

export default function GoalsPage() {
  const [groups, setGroups] = useState<GoalDomainGroup[] | null>(null);
  const [error, setError]   = useState<string | null>(null);

  useEffect(() => {
    goalsApi
      .byDomain()
      .then(setGroups)
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!groups) return <Loading />;

  return (
    <div>
      <PageHeader title="Goals" sub="2026 annual goals" />
      <div className="p-6">
        {groups.length === 0 ? (
          <Empty message="No goals configured." />
        ) : (
          <div className="grid grid-cols-2 gap-4">
            {groups.map(({ domain, goals }) => (
              <Card key={domain}>
                <SectionLabel>{domain}</SectionLabel>
                {goals.length === 0 ? (
                  <Empty message="No goals in this domain." />
                ) : (
                  <div className="divide-y divide-border">
                    {goals.map((g) => (
                      <div key={g.goal_key} className="py-3">
                        <div className="flex items-center justify-between">
                          <span className="text-[13px] text-ink font-medium">
                            {g.label}
                          </span>
                          <PaceBadge status={g.pace_status} />
                        </div>
                        {g.description && (
                          <p className="text-2xs text-faint mt-0.5">
                            {g.description}
                          </p>
                        )}

                        {g.goal_value_type === "str" ? (
                          <p className="text-2xs text-faint mt-1.5">
                            Not numerically tracked
                          </p>
                        ) : (
                          <>
                            <div className="flex items-center justify-between mt-1.5">
                              <span className="text-[12px] tabular-nums text-muted">
                                {g.current_value ?? "—"}
                                {g.target_numeric != null &&
                                  ` / ${g.target_numeric}`}
                              </span>
                              {g.progress_percent != null && (
                                <span className="text-[12px] tabular-nums text-green font-semibold">
                                  {g.progress_percent.toFixed(0)}%
                                </span>
                              )}
                            </div>
                            {g.progress_percent != null && (
                              <div className="h-1 bg-canvas rounded-full mt-1.5 overflow-hidden">
                                <div
                                  className="h-full bg-green"
                                  style={{
                                    width: `${Math.min(
                                      100,
                                      g.progress_percent
                                    )}%`,
                                  }}
                                />
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
