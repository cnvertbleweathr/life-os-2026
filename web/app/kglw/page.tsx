"use client";

/**
 * /kglw — King Gizzard show catalog.
 *
 * Built against the CONFIRMED real API (2026-06-20). Two known
 * limitations from the live data, both surfaced honestly in the UI
 * rather than hidden:
 *
 *   1. No lat/lng anywhere in KGLW's API — there is no real globe
 *      visualization yet, just a venue list/picker. A future pass
 *      would need to geocode city/state/country separately.
 *   2. The jam chart only covers 247 NOTABLE versions, not full
 *      setlist history for all 1104 shows — so "everywhere this song
 *      has been played" via Song mode is really "everywhere this song
 *      has a jam-chart-flagged version," a meaningfully smaller set.
 */

import { useEffect, useState } from "react";
import {
  kglwApi,
  type KglwShow,
  type KglwSong,
  type KglwJamchartEntry,
  type KglwSummary,
} from "@/lib/api";
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

function ShowRow({ show }: { show: KglwShow }) {
  return (
    <a
      href={`https://kglw.net/${show.permalink}`}
      target="_blank"
      rel="noopener noreferrer"
      className="flex items-center justify-between py-2.5 hover:bg-canvas -mx-2 px-2 rounded-sm transition-colors"
    >
      <div>
        <p className="text-[13px] text-ink">
          {show.show_title || show.artist}
          {show.tour_name && show.tour_name !== "Not Part of a Tour" && (
            <span className="text-2xs text-faint ml-1.5">· {show.tour_name}</span>
          )}
        </p>
        <p className="text-2xs text-faint">
          {show.venue_name} · {show.city}{show.state ? `, ${show.state}` : ""}, {show.country}
        </p>
      </div>
      <span className="text-2xs text-muted shrink-0 ml-3">{show.show_date}</span>
    </a>
  );
}

export default function KglwPage() {
  const [mode, setMode]               = useState<"shows" | "songs">("shows");
  const [summary, setSummary]         = useState<KglwSummary | null>(null);
  const [shows, setShows]             = useState<KglwShow[] | null>(null);
  const [onThisDay, setOnThisDay]     = useState<KglwShow[] | null>(null);
  const [songs, setSongs]             = useState<KglwSong[] | null>(null);
  const [songSearch, setSongSearch]   = useState("");
  const [selectedSong, setSelectedSong]   = useState<KglwSong | null>(null);
  const [songVersions, setSongVersions]   = useState<KglwJamchartEntry[] | null>(null);
  const [error, setError]             = useState<string | null>(null);

  useEffect(() => {
    kglwApi.summary()
      .then(setSummary)
      .catch(() => setSummary(null));
    kglwApi.shows({ upcoming: true, limit: 50 })
      .then(setShows)
      .catch((e) => setError(e.message));
    kglwApi.onThisDay()
      .then(setOnThisDay)
      .catch(() => setOnThisDay([]));
    kglwApi.songs()
      .then(setSongs)
      .catch(() => setSongs([]));
  }, []);

  useEffect(() => {
    if (!selectedSong) { setSongVersions(null); return; }
    kglwApi.songShows(selectedSong.song_id)
      .then(setSongVersions)
      .catch(() => setSongVersions([]));
  }, [selectedSong]);

  if (error) return <ErrorState message={error} />;

  const filteredSongs = (songs ?? []).filter((s) =>
    s.name.toLowerCase().includes(songSearch.toLowerCase())
  ).slice(0, 40);

  return (
    <div>
      <PageHeader
        title="🎸 King Gizzard"
        sub="Live show catalog — via kglw.net"
        right={
          <div className="flex items-center bg-canvas border border-border rounded-full p-1">
            {(["shows", "songs"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={clsx(
                  "px-4 py-1.5 text-xs font-medium rounded-full transition-colors",
                  mode === m ? "bg-green text-white" : "text-muted hover:text-ink"
                )}
              >
                {m === "shows" ? "Upcoming shows" : "Song explorer"}
              </button>
            ))}
          </div>
        }
      />

      <div className="p-6 space-y-6">
        {summary === null ? (
          <Loading label="Loading catalog stats..." />
        ) : (
          <div className="grid grid-cols-4 gap-3">
            <StatCard label="Total shows" value={summary.total_shows} />
            <StatCard label="Songs" value={summary.total_songs} />
            <StatCard label="Venues" value={summary.total_venues} />
            <StatCard
              label="Next show"
              value={summary.next_show?.show_date ?? "—"}
              accent
            />
          </div>
        )}

        {mode === "shows" && (
          <div className="grid grid-cols-3 gap-4">
            <Card className="col-span-2">
              <SectionLabel>Upcoming shows</SectionLabel>
              {shows === null ? (
                <Loading />
              ) : shows.length === 0 ? (
                <Empty message="No upcoming shows found." />
              ) : (
                <div className="divide-y divide-border">
                  {shows.map((s) => <ShowRow key={s.show_id} show={s} />)}
                </div>
              )}
              <p className="text-2xs text-faint mt-3">
                Includes related-artist shows tracked by kglw.net, not only King Gizzard proper.
              </p>
            </Card>

            <Card>
              <SectionLabel>On this day</SectionLabel>
              {onThisDay === null ? (
                <Loading />
              ) : onThisDay.length === 0 ? (
                <Empty message="No KGLW shows on this calendar date in any year." />
              ) : (
                <div className="space-y-3">
                  {onThisDay.map((s) => (
                    <div key={s.show_id}>
                      <p className="text-[13px] text-ink">{s.venue_name}</p>
                      <p className="text-2xs text-faint">
                        {s.city}, {s.country} · {s.show_date}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        )}

        {mode === "songs" && (
          <div className="grid grid-cols-3 gap-4">
            <Card>
              <SectionLabel>Pick a song</SectionLabel>
              <input
                type="text"
                placeholder="Search songs..."
                value={songSearch}
                onChange={(e) => setSongSearch(e.target.value)}
                className="w-full text-sm border border-border rounded-sm px-3 py-2
                           bg-canvas text-ink placeholder-faint mb-2
                           focus:outline-none focus:ring-1 focus:ring-green/40"
              />
              {songs === null ? (
                <Loading />
              ) : (
                <div className="max-h-80 overflow-y-auto divide-y divide-border">
                  {filteredSongs.map((song) => (
                    <button
                      key={song.song_id}
                      onClick={() => setSelectedSong(song)}
                      className={clsx(
                        "w-full text-left py-2 px-1 text-[12px] hover:bg-canvas transition-colors",
                        selectedSong?.song_id === song.song_id
                          ? "text-green font-medium"
                          : "text-ink"
                      )}
                    >
                      {song.name}
                      {!song.is_original && (
                        <span className="text-2xs text-faint ml-1">(cover)</span>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </Card>

            <Card className="col-span-2">
              <SectionLabel>
                {selectedSong ? `Jam chart versions — ${selectedSong.name}` : "Notable versions"}
              </SectionLabel>
              {!selectedSong ? (
                <Empty
                  message="Pick a song to see its jam chart entries."
                  detail="Note: this shows jam-chart-flagged versions only (247 total), not full setlist history across all shows."
                />
              ) : songVersions === null ? (
                <Loading />
              ) : songVersions.length === 0 ? (
                <Empty
                  message="No jam chart entries for this song."
                  detail="It may have been played live without being flagged as a notable version."
                />
              ) : (
                <div className="divide-y divide-border">
                  {songVersions.map((v) => (
                    <a
                      key={v.uniqueid}
                      href={`https://kglw.net/${v.permalink}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block py-3 hover:bg-canvas -mx-2 px-2 rounded-sm transition-colors"
                    >
                      <div className="flex items-center justify-between">
                        <p className="text-[13px] text-ink">
                          {v.venue_name}
                          {v.is_recommended && (
                            <span className="text-2xs text-green font-semibold ml-1.5">★ RECOMMENDED</span>
                          )}
                        </p>
                        <span className="text-2xs text-faint">{v.show_date}</span>
                      </div>
                      <p className="text-2xs text-faint">{v.city}, {v.country}</p>
                      {v.jamchart_note && (
                        <p className="text-2xs text-muted mt-1 italic">{v.jamchart_note}</p>
                      )}
                    </a>
                  ))}
                </div>
              )}
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}
