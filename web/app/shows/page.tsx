"use client";

import { useEffect, useState } from "react";
import { showsApi, type Show, type ShowsSummary } from "@/lib/api";
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

export default function ShowsPage() {
  const [summary, setSummary]   = useState<ShowsSummary | null>(null);
  const [shows, setShows]       = useState<Show[] | null>(null);
  const [filterMine, setFilterMine] = useState(false);
  const [error, setError]       = useState<string | null>(null);

  useEffect(() => {
    showsApi.summary().then(setSummary).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    showsApi
      .list(filterMine)
      .then(setShows)
      .catch((e) => setError(e.message));
  }, [filterMine]);

  if (error) return <ErrorState message={error} />;
  if (!summary || !shows) return <Loading />;

  return (
    <div>
      <PageHeader title="Shows" sub="Denver concerts — AEG + Ticketmaster" />
      <div className="p-6 space-y-6">
        <div className="grid grid-cols-4 gap-3">
          <StatCard label="Total shows" value={summary.total} />
          <StatCard
            label="Matching my artists"
            value={summary.my_artist_count}
            accent
          />
          <StatCard label="Venues" value={summary.venues} />
          <StatCard label="Next show" value={summary.next_show?.title ?? "—"} />
        </div>

        {/* my_artist_count uses substring matching and can false-positive on
            short/common-word artist names — caveat visibly rather than
            presenting it as a precise number. */}
        <p className="text-2xs text-faint -mt-3">
          Artist matching is approximate (substring search) — treat the count as a rough signal, not exact.
        </p>

        <Card>
          <div className="flex items-center justify-between mb-3">
            <SectionLabel>Upcoming shows</SectionLabel>
            <div className="flex bg-canvas border border-border rounded-full p-0.5">
              {[
                { v: false, label: "All" },
                { v: true, label: "My artists" },
              ].map((opt) => (
                <button
                  key={String(opt.v)}
                  onClick={() => setFilterMine(opt.v)}
                  className={clsx(
                    "px-3 py-1 text-2xs font-medium rounded-full transition-colors",
                    filterMine === opt.v
                      ? "bg-green text-white"
                      : "text-muted hover:text-ink"
                  )}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {shows.length === 0 ? (
            <Empty message="No shows found." />
          ) : (
            <div className="divide-y divide-border">
              {shows.map((s, i) => (
                <a
                  key={i}
                  href={s.ticket_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-between py-2.5 hover:bg-canvas -mx-2 px-2 rounded-sm transition-colors"
                >
                  <div>
                    <p className="text-[13px] text-ink">
                      {s.title}
                      {s.is_my_artist && (
                        <span className="text-2xs text-green ml-1.5">★</span>
                      )}
                    </p>
                    <p className="text-2xs text-faint">{s.venue_name} · {s.source}</p>
                  </div>
                  <span className="text-2xs text-muted">{s.date}</span>
                </a>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
