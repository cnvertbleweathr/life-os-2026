"use client";

import { useEffect, useState } from "react";
import { showsApi, type ShowsSummary, type Show } from "@/lib/api";
import {
  Card, PageHead, Stat, StatBand, K, Pill, Empty, Loading, ErrorState,
} from "@/components/ui/primitives";

export default function ShowsPage() {
  const [summary, setSummary] = useState<Awaited<ReturnType<typeof showsApi.summary>> | null>(null);
  const [allShows, setAllShows] = useState<Show[]>([]);
  const [myShows, setMyShows] = useState<Show[]>([]);
  const [mine, setMine] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      showsApi.summary(),
      showsApi.list(false),
      showsApi.list(true),
    ])
      .then(([s, all, my]) => { setSummary(s); setAllShows(all); setMyShows(my); })
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!summary) return <Loading />;

  const list = mine ? myShows : allShows;
  const myCount = summary.my_artist_count ?? myShows.length;
  const totalCount = summary.total_shows ?? allShows.length;
  const venues = summary.venue_count ?? 0;
  const nextMine = myShows[0];

  return (
    <div className="ons-page" style={{ padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" }}>
      <PageHead
        title="Shows"
        kicker="Denver concerts · AEG + Ticketmaster"
        right={nextMine ? (
          <div className="font-mono text-right text-faint" style={{ fontSize: 9.5 }}>
            NEXT FOR YOU · {(nextMine.date ?? "").slice(5)}<br />
            {(nextMine.venue ?? "").toUpperCase()}
          </div>
        ) : undefined}
      />

      <StatBand>
        <Stat label="Total Shows" value={totalCount.toLocaleString()} />
        <Stat label="Matching My Artists" value={myCount} accent />
        <Stat label="Venues" value={venues} />
        <Stat
          label="Next For You"
          value={nextMine ? nextMine.title?.split(" ").slice(0, 2).join(" ") ?? "—" : "—"}
          last
        />
      </StatBand>

      <p className="font-mono text-faint mb-[26px]" style={{ fontSize: 9.5, margin: "0 0 26px" }}>
        ARTIST MATCHING IS APPROXIMATE (SUBSTRING SEARCH) — TREAT THE COUNT AS A ROUGH SIGNAL, NOT EXACT.
      </p>

      <Card pad={0}>
        <div
          className="flex justify-between items-center border-b border-border-2"
          style={{ padding: "16px 18px 14px" }}
        >
          <K>Upcoming Shows</K>
          <div className="flex gap-[7px]">
            <Pill active={!mine} onClick={() => setMine(false)}>All</Pill>
            <Pill active={mine} onClick={() => setMine(true)}>My artists ★</Pill>
          </div>
        </div>
        <div style={{ padding: "0 18px 12px" }}>
          {list.length === 0 ? (
            <Empty message={mine ? "No matching shows." : "No shows loaded."} />
          ) : (
            list.map((x, i) => {
              const isMine = x.is_my_artist;
              return (
                <a
                  key={i}
                  href={x.ticket_url || "#"}
                  target={x.ticket_url ? "_blank" : undefined}
                  rel="noopener noreferrer"
                  className="ons-row flex items-center gap-[14px] no-underline text-inherit cursor-pointer"
                  style={{
                    padding: "13px 8px", margin: "0 -8px", borderRadius: 6,
                    borderTop: i ? "1px solid #ebe5d8" : "none",
                  }}
                >
                  <div
                    className="font-mono shrink-0"
                    style={{ fontSize: 10.5, color: isMine ? "#1d5536" : "#736e5f", width: 58 }}
                  >
                    {(x.date ?? "").slice(5)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-ink truncate" style={{ fontSize: 14 }}>
                      {x.title}
                      {isMine && <span className="text-green ml-[7px]">★</span>}
                    </div>
                    <div className="font-mono text-faint mt-0.5" style={{ fontSize: 11 }}>
                      {x.venue} · {x.source}
                    </div>
                  </div>
                  <span
                    className="ons-tap font-mono shrink-0"
                    style={{
                      fontSize: 9, color: "#736e5f",
                      border: "1px solid #e6e3dc", borderRadius: 999, padding: "4px 11px",
                    }}
                  >
                    TICKETS ↗
                  </span>
                </a>
              );
            })
          )}
        </div>
      </Card>
    </div>
  );
}
