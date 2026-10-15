"use client";

import { useEffect, useState } from "react";
import {
  musicApi, showsApi,
  type MusicSummary, type MusicDaily10, type OnThisDay, type Show,
} from "@/lib/api";
import {
  Card, PageHead, Stat, StatBand, K, Pill, Empty, Loading, ErrorState,
} from "@/components/ui/primitives";

const KIND_LABEL: Record<string, string> = { event: "", born: "Born", died: "Died" };

export default function MusicPage() {
  const [summary, setSummary] = useState<MusicSummary | null>(null);
  const [daily10, setDaily10] = useState<MusicDaily10 | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Secondary panels load independently — a failure in one shouldn't blank the page
  const [otd, setOtd] = useState<OnThisDay | null>(null);
  const [allShows, setAllShows] = useState<Show[] | null>(null);
  const [myShows, setMyShows] = useState<Show[]>([]);
  const [showsError, setShowsError] = useState<string | null>(null);
  const [mine, setMine] = useState(false);
  const [coverOk, setCoverOk] = useState(true);

  useEffect(() => {
    Promise.all([musicApi.summary(), musicApi.daily10()])
      .then(([s, d]) => { setSummary(s); setDaily10(d); })
      .catch((e) => setError(e.message));

    musicApi.onThisDay()
      .then(setOtd)
      .catch((e) => setOtd({ date: "", events: [], history: [], error: e.message }));

    Promise.all([showsApi.list(false), showsApi.list(true)])
      .then(([all, my]) => { setAllShows(all); setMyShows(my); })
      .catch((e) => setShowsError(e.message));
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!summary || !daily10) return <Loading />;

  const year = new Date().getFullYear();
  const hrs = summary.minutes_ytd != null ? Math.round(summary.minutes_ytd / 60) : null;
  const goalHrs = summary.goal_minutes != null ? Math.round(summary.goal_minutes / 60) : null;
  const nextMine = myShows[0];
  const showList = (mine ? myShows : allShows) ?? [];
  const hasCover = Boolean(daily10.available && daily10.cover_image_path && coverOk);

  return (
    <div className="ons-page" style={{ padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" }}>
      <PageHead
        title="Music"
        kicker="Spotify · AEG + Ticketmaster"
        right={nextMine ? (
          <div className="font-mono text-right text-faint" style={{ fontSize: 9.5 }}>
            NEXT FOR YOU · {(nextMine.date ?? "").slice(5)}<br />
            {nextMine.title.toUpperCase()} · {(nextMine.venue ?? "").toUpperCase()}
          </div>
        ) : undefined}
      />

      {/* ── This Day in Music ─────────────────────────────────────────── */}
      <ThisDayInMusic data={otd} />

      {/* ── Year listening ────────────────────────────────────────────── */}
      <div className="flex justify-between items-end mb-2">
        <K>{year} Listening</K>
        <div className="font-mono text-faint" style={{ fontSize: 9.5 }}>
          {summary.unique_artists != null ? `${summary.unique_artists.toLocaleString()} ARTISTS` : "—"}
          {" · "}
          {summary.unique_tracks != null ? `${summary.unique_tracks.toLocaleString()} TRACKS` : "—"}
        </div>
      </div>
      <StatBand>
        <Stat
          label="Listening"
          value={hrs != null ? hrs.toLocaleString() : "—"}
          unit={goalHrs != null ? `/ ${goalHrs.toLocaleString()} hrs` : "hrs"}
          accent
        />
        <Stat label="Days Listened" value={summary.days_listened ?? "—"} />
        <Stat label="Top Artist" value={summary.top_artist ?? "—"} />
        <Stat
          label="YTD Progress"
          value={summary.progress_pct != null ? Math.round(summary.progress_pct) : "—"}
          unit={summary.progress_pct != null ? "%" : ""}
          last
        />
      </StatBand>

      {/* ── Playlist (left) + Shows (right) ───────────────────────────── */}
      <div className="grid gap-[22px] items-start" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <Card accent pad={0} style={{ overflow: "hidden" }}>
          <div className="flex justify-between items-center" style={{ padding: "16px 18px 12px" }}>
            <K>Daily 10</K>
            {daily10.available && daily10.date && (
              <span className="font-mono text-faint" style={{ fontSize: 9.5 }}>{daily10.date}</span>
            )}
          </div>

          {/* Cover only when one actually exists — no placeholder block */}
          {hasCover && (
            <img
              src={`${process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api"}/music/daily10/cover`}
              alt="Today's Daily 10 cover art"
              style={{ width: "100%", aspectRatio: "16/9", objectFit: "cover", display: "block" }}
              onError={() => setCoverOk(false)}
            />
          )}

          {daily10.available && daily10.playlist_id ? (
            <iframe
              src={`https://open.spotify.com/embed/playlist/${daily10.playlist_id}?utm_source=generator`}
              width="100%"
              height="660"
              style={{ border: "none", display: "block" }}
              allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"
              loading="lazy"
              title="Today's Daily 10 playlist"
            />
          ) : (
            <div style={{ padding: "0 18px 16px" }}>
              <Empty message="No playlist generated yet today." />
            </div>
          )}

          {daily10.available && (daily10.description || daily10.tewnidge_artists?.length) ? (
            <div style={{ padding: "12px 18px 14px", borderTop: "1px solid #ebe5d8" }}>
              {daily10.description && (
                <p className="m-0" style={{ fontSize: 11.5, lineHeight: 1.5, color: "#232a22" }}>
                  {daily10.description}
                </p>
              )}
              {daily10.tewnidge_artists && daily10.tewnidge_artists.length > 0 && (
                <p className="text-faint mt-2 mb-0" style={{ fontSize: 10.5 }}>
                  Featuring: {daily10.tewnidge_artists.slice(0, 4).join(", ")}
                </p>
              )}
            </div>
          ) : null}
        </Card>

        <Card pad={0}>
          <div
            className="flex justify-between items-center border-b border-border-2"
            style={{ padding: "16px 18px 14px" }}
          >
            <K>Denver Shows</K>
            <div className="flex gap-[7px]">
              <Pill active={!mine} onClick={() => setMine(false)}>All</Pill>
              <Pill active={mine} onClick={() => setMine(true)}>
                My artists ★{myShows.length ? ` ${myShows.length}` : ""}
              </Pill>
            </div>
          </div>
          <div className="ons-scroll" style={{ padding: "0 18px 12px", maxHeight: 720, overflowY: "auto" }}>
            {showsError ? (
              <Empty message="Couldn't load shows." detail={showsError} />
            ) : allShows === null ? (
              <Empty message="Loading…" />
            ) : showList.length === 0 ? (
              <Empty message={mine ? "No matching shows." : "No shows loaded."} />
            ) : (
              showList.map((x, i) => <ShowRow key={i} show={x} first={i === 0} />)
            )}
          </div>
          <p
            className="font-mono text-faint m-0 border-t border-border-2"
            style={{ fontSize: 8.5, padding: "10px 18px" }}
          >
            ARTIST MATCHING IS APPROXIMATE (SUBSTRING SEARCH)
          </p>
        </Card>
      </div>
    </div>
  );
}

function ThisDayInMusic({ data }: { data: OnThisDay | null }) {
  const label = new Date().toLocaleDateString("en-US", { month: "long", day: "numeric" });

  return (
    <div className="mb-7">
      <div className="flex justify-between items-end mb-2">
        <K>This Day in Music · {label}</K>
        <span className="font-mono text-faint" style={{ fontSize: 9 }}>VIA WIKIPEDIA</span>
      </div>

      {data === null ? (
        <Empty message="Loading…" />
      ) : data.events.length === 0 ? (
        <Empty message="Nothing music-related on Wikipedia for today." detail={data.error ?? undefined} />
      ) : (
        <div
          className="grid"
          style={{
            gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
            columnGap: 22,
            borderTop: "1.5px solid #232a22",
          }}
        >
          {data.events.map((e, i) => (
            <a
              key={i}
              href={e.url ?? undefined}
              target="_blank"
              rel="noopener noreferrer"
              className="ons-row no-underline text-inherit"
              style={{ padding: "12px 0", borderBottom: "1px solid #e6e3dc" }}
            >
              <div className="flex items-baseline gap-2">
                <span className="font-serif font-bold text-green" style={{ fontSize: 20 }}>
                  {e.year ?? "—"}
                </span>
                {KIND_LABEL[e.kind] && (
                  <span className="font-mono text-faint uppercase" style={{ fontSize: 8.5, letterSpacing: "1px" }}>
                    {KIND_LABEL[e.kind]}
                  </span>
                )}
                {e.is_my_artist && <span className="text-green" style={{ fontSize: 11 }}>★</span>}
              </div>
              <p className="m-0 mt-1 text-ink" style={{ fontSize: 12, lineHeight: 1.45 }}>{e.text}</p>
            </a>
          ))}
        </div>
      )}

      {data && data.history.length > 0 && (
        <p className="font-mono text-faint mt-3 mb-0" style={{ fontSize: 10 }}>
          YOUR LISTENING ON THIS DATE ·{" "}
          {data.history.map((h) => `${h.year}: ${h.top_artists.join(", ")} (${h.minutes}m)`).join("  ·  ")}
        </p>
      )}
    </div>
  );
}

function ShowRow({ show: x, first }: { show: Show; first: boolean }) {
  const isMine = x.is_my_artist;
  return (
    <a
      href={x.ticket_url || "#"}
      target={x.ticket_url ? "_blank" : undefined}
      rel="noopener noreferrer"
      className="ons-row flex items-center gap-[12px] no-underline text-inherit cursor-pointer"
      style={{
        padding: "11px 8px", margin: "0 -8px", borderRadius: 6,
        borderTop: first ? "none" : "1px solid #ebe5d8",
      }}
    >
      <div
        className="font-mono shrink-0"
        style={{ fontSize: 10.5, color: isMine ? "#1d5536" : "#736e5f", width: 40 }}
      >
        {(x.date ?? "").slice(5)}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-ink truncate" style={{ fontSize: 13.5 }}>
          {x.title}
          {isMine && <span className="text-green ml-[7px]">★</span>}
        </div>
        <div className="font-mono text-faint mt-0.5 truncate" style={{ fontSize: 10.5 }}>
          {x.venue} · {x.source}
        </div>
      </div>
      <span className="font-mono shrink-0 text-faint" style={{ fontSize: 10 }}>↗</span>
    </a>
  );
}
