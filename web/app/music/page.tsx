"use client";

import { useEffect, useState } from "react";
import {
  musicApi, showsApi,
  type MusicSummary, type MusicDaily10, type ArtistOfTheDay, type Show,
} from "@/lib/api";
import {
  Card, PageHead, Stat, StatBand, K, Pill, Empty, Loading, ErrorState,
} from "@/components/ui/primitives";


export default function MusicPage() {
  const [summary, setSummary] = useState<MusicSummary | null>(null);
  const [daily10, setDaily10] = useState<MusicDaily10 | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Secondary panels load independently — a failure in one shouldn't blank the page
  const [aotd, setAotd] = useState<ArtistOfTheDay | null>(null);
  const [reroll, setReroll] = useState(0);
  const [allShows, setAllShows] = useState<Show[] | null>(null);
  const [myShows, setMyShows] = useState<Show[]>([]);
  const [showsError, setShowsError] = useState<string | null>(null);
  const [mine, setMine] = useState(false);
  const [coverOk, setCoverOk] = useState(true);

  useEffect(() => {
    Promise.all([musicApi.summary(), musicApi.daily10()])
      .then(([s, d]) => { setSummary(s); setDaily10(d); })
      .catch((e) => setError(e.message));

    Promise.all([showsApi.list(false), showsApi.list(true)])
      .then(([all, my]) => { setAllShows(all); setMyShows(my); })
      .catch((e) => setShowsError(e.message));
  }, []);

  useEffect(() => {
    setAotd(null);
    musicApi.artistOfTheDay(reroll)
      .then(setAotd)
      .catch((e) => setAotd({ available: false, reason: e.message }));
  }, [reroll]);

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

      {/* ── Artist of the Day ─────────────────────────────────────────── */}
      <ArtistOfTheDayCard data={aotd} onShuffle={() => setReroll((r) => r + 1)} />

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
      <div className="ons-stack grid gap-[22px] items-start" style={{ gridTemplateColumns: "1fr 1fr" }}>
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

function ArtistOfTheDayCard({ data, onShuffle }: { data: ArtistOfTheDay | null; onShuffle: () => void }) {
  const [expanded, setExpanded] = useState(false);
  useEffect(() => setExpanded(false), [data?.artist]);

  const header = (
    <div className="flex justify-between items-end mb-2">
      <K>Artist of the Day · from Tewnidge</K>
      <button
        onClick={onShuffle}
        className="font-mono text-faint bg-transparent border-0 cursor-pointer p-0"
        style={{ fontSize: 9, letterSpacing: "1px" }}
        title="Pick a different artist"
      >
        SHUFFLE ↻
      </button>
    </div>
  );

  if (data === null) return <div className="mb-7">{header}<Empty message="Loading…" /></div>;
  if (!data.available) {
    return <div className="mb-7">{header}<Empty message="No artist today." detail={data.reason} /></div>;
  }

  const meta = [
    data.description,
    data.country,
    data.formed ? `since ${data.formed}` : null,
    data.members ? `${data.members} members` : null,
    data.label,
  ].filter(Boolean);
  const paragraphs = (data.bio ?? "").split(/\n\s*\n/).filter((p) => p.trim());
  const shown = expanded ? paragraphs : paragraphs.slice(0, 1);
  const you = data.you ?? {};

  return (
    <div className="mb-7">
      {header}
      <div
        className="ons-stack grid gap-[26px]"
        style={{
          gridTemplateColumns: data.image ? "200px 1fr 240px" : "1fr 240px",
          borderTop: "1.5px solid #232a22",
          borderBottom: "1px solid #e6e3dc",
          padding: "18px 0",
        }}
      >
        {data.image && (
          <img
            src={data.image}
            alt={data.artist}
            style={{ width: 200, height: 200, objectFit: "cover", borderRadius: 4, display: "block" }}
          />
        )}

        <div className="min-w-0">
          <div className="font-serif font-bold text-ink" style={{ fontSize: 30, lineHeight: 1.1 }}>
            {data.artist}
          </div>
          {meta.length > 0 && (
            <div className="font-mono text-faint mt-1.5" style={{ fontSize: 10 }}>{meta.join(" · ").toUpperCase()}</div>
          )}
          {data.tags && data.tags.length > 0 && (
            <div className="flex flex-wrap gap-[6px] mt-2.5">
              {data.tags.map((t) => (
                <span
                  key={t}
                  className="font-mono text-green"
                  style={{ fontSize: 9, border: "1px solid #c9d6cc", borderRadius: 999, padding: "2px 8px" }}
                >
                  {t.toLowerCase()}
                </span>
              ))}
            </div>
          )}
          <div className="mt-3" style={{ fontSize: 13, lineHeight: 1.6, color: "#232a22" }}>
            {shown.map((p, i) => <p key={i} className="m-0 mb-2">{p}</p>)}
          </div>
          <div className="flex gap-4 font-mono text-faint" style={{ fontSize: 9.5 }}>
            {paragraphs.length > 1 && (
              <button
                onClick={() => setExpanded((e) => !e)}
                className="font-mono text-green bg-transparent border-0 cursor-pointer p-0"
                style={{ fontSize: 9.5 }}
              >
                {expanded ? "LESS ↑" : "READ MORE ↓"}
              </button>
            )}
            {Object.entries(data.links ?? {}).map(([src, url]) => (
              <a key={src} href={url} target="_blank" rel="noopener noreferrer" className="text-faint">
                {src.toUpperCase()} ↗
              </a>
            ))}
            {data.website && (
              <a href={data.website} target="_blank" rel="noopener noreferrer" className="text-faint">WEBSITE ↗</a>
            )}
          </div>
        </div>

        <div className="flex flex-col gap-4" style={{ borderLeft: "1px solid #e6e3dc", paddingLeft: 20 }}>
          <Fact label="You">
            {you.minutes ? (
              <>
                <span className="font-serif font-bold text-green" style={{ fontSize: 20 }}>
                  {you.minutes.toLocaleString()}
                </span>{" "}
                <span className="text-faint" style={{ fontSize: 11 }}>min · {you.plays} plays</span>
                {you.top_track && <div style={{ fontSize: 11.5 }}>Most played: {you.top_track}</div>}
                {you.first_played && (
                  <div className="text-faint" style={{ fontSize: 10.5 }}>First played {you.first_played}</div>
                )}
              </>
            ) : (
              <span className="text-faint" style={{ fontSize: 11.5 }}>Not in your history yet</span>
            )}
          </Fact>
          {data.listeners != null && (
            <Fact label="Last.fm listeners">
              <span style={{ fontSize: 13 }}>{data.listeners.toLocaleString()}</span>
            </Fact>
          )}
          {data.shows && data.shows.length > 0 && (
            <Fact label="In Denver">
              {data.shows.map((sh, i) => (
                <a key={i} href={sh.ticket_url} target="_blank" rel="noopener noreferrer"
                   className="block text-green no-underline" style={{ fontSize: 11.5 }}>
                  {sh.date.slice(5)} · {sh.venue} ↗
                </a>
              ))}
            </Fact>
          )}
          {data.similar && data.similar.length > 0 && (
            <Fact label="Similar">
              <span style={{ fontSize: 11.5 }}>{data.similar.join(", ")}</span>
            </Fact>
          )}
        </div>
      </div>
    </div>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="font-mono text-faint uppercase mb-1" style={{ fontSize: 8.5, letterSpacing: "1.2px" }}>
        {label}
      </div>
      {children}
    </div>
  );
}

// Google Calendar "create event" link. Times are Denver-local with ctz set,
// so no UTC math; default length 3h. Date-only shows become all-day events.
function gcalUrl(x: Show): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  const stamp = (d: Date, withTime: boolean) =>
    `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}` +
    (withTime ? `T${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}00` : "");

  let dates: string;
  if (x.start_local) {
    const [d, t] = x.start_local.split("T");
    const [y, m, day] = d.split("-").map(Number);
    const [h, mi] = t.split(":").map(Number);
    const start = new Date(Date.UTC(y, m - 1, day, h, mi));
    const end = new Date(start.getTime() + 3 * 3600 * 1000);
    dates = `${stamp(start, true)}/${stamp(end, true)}`;
  } else {
    const [y, m, day] = (x.date ?? "").split("-").map(Number);
    const start = new Date(Date.UTC(y, m - 1, day));
    dates = `${stamp(start, false)}/${stamp(new Date(start.getTime() + 86400000), false)}`;
  }

  const params = new URLSearchParams({
    action: "TEMPLATE",
    text: x.title,
    dates,
    ctz: "America/Denver",
    location: x.location || x.venue || "",
    details: x.ticket_url ? `Tickets: ${x.ticket_url}` : "",
  });
  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}

function ShowRow({ show: x, first }: { show: Show; first: boolean }) {
  const isMine = x.is_my_artist;
  return (
    <div
      className="flex items-center gap-[6px]"
      style={{ borderTop: first ? "none" : "1px solid #ebe5d8" }}
    >
      <a
        href={x.ticket_url || "#"}
        target={x.ticket_url ? "_blank" : undefined}
        rel="noopener noreferrer"
        className="ons-row flex flex-1 min-w-0 items-center gap-[12px] no-underline text-inherit cursor-pointer"
        style={{ padding: "11px 8px", margin: "0 0 0 -8px", borderRadius: 6 }}
        title="Buy tickets"
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
            {x.venue}
            {x.start_local && ` · ${fmtTime(x.start_local)}`} · {x.source}
          </div>
        </div>
        <span className="font-mono shrink-0 text-faint" style={{ fontSize: 10 }}>↗</span>
      </a>
      <a
        href={gcalUrl(x)}
        target="_blank"
        rel="noopener noreferrer"
        className="ons-row shrink-0 no-underline"
        style={{ fontSize: 16, padding: "8px 6px", borderRadius: 6, lineHeight: 1 }}
        title="Add to Google Calendar"
        aria-label={`Add ${x.title} to Google Calendar`}
      >
        📅
      </a>
    </div>
  );
}

function fmtTime(startLocal: string): string {
  const [h, m] = startLocal.split("T")[1].split(":").map(Number);
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")}${h < 12 ? "am" : "pm"}`;
}
