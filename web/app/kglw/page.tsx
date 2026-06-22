"use client";

import { useEffect, useState, useMemo } from "react";
import { kglwApi, type KglwShow, type KglwSong } from "@/lib/api";
import {
  Card, PageHead, K, Pill, Empty, Loading, ErrorState,
} from "@/components/ui/primitives";
import { OnsIcon } from "@/components/ui/icons";

function loc(s: KglwShow) {
  return `${s.city || ""}${s.state ? ", " + s.state : ""}${s.country ? " · " + s.country : ""}`;
}

// ── Show Explorer ──
function ShowExplorer({ shows: allShows }: { shows: KglwShow[] }) {
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<"all" | "upcoming" | "video">("all");
  const [sel, setSel] = useState<KglwShow | null>(allShows[0] || null);

  const shows = useMemo(() => {
    const ql = q.trim().toLowerCase();
    return allShows
      .filter((s) => {
        if (filter === "upcoming" && !s.upcoming) return false;
        if (filter === "video" && !s.videoId) return false;
        return true;
      })
      .filter((s) => {
        if (!ql) return true;
        return [s.venue, s.city, s.state, s.country, s.tour, s.date]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .includes(ql);
      })
      .sort((a, b) => {
        if (a.upcoming !== b.upcoming) return a.upcoming ? -1 : 1;
        return (b.date ?? "").localeCompare(a.date ?? "");
      });
  }, [allShows, q, filter]);

  return (
    <div className="grid gap-[22px]" style={{ gridTemplateColumns: "1.05fr 1.25fr" }}>
      <div>
        <Card pad={0}>
          <div className="border-b border-border-2" style={{ padding: "16px 18px 14px" }}>
            <K style={{ marginBottom: 10 }}>Explore shows · by location & date</K>
            <div className="flex items-center gap-2 mb-[11px]">
              <OnsIcon name="search" size={15} stroke={1.7} style={{ color: "#a39d8c" }} />
              <input
                className="ons-input flex-1"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder='Try "Morrison", "Red Rocks", "France", "2017"…'
              />
            </div>
            <div className="flex gap-[7px]">
              <Pill active={filter === "all"} onClick={() => setFilter("all")}>All</Pill>
              <Pill active={filter === "upcoming"} onClick={() => setFilter("upcoming")}>Upcoming</Pill>
              <Pill active={filter === "video"} onClick={() => setFilter("video")}>Watchable</Pill>
              <span className="ml-auto self-center font-mono text-faint" style={{ fontSize: 9.5 }}>
                {shows.length} SHOWS
              </span>
            </div>
          </div>
          <div className="ons-scroll" style={{ maxHeight: 430, overflowY: "auto" }}>
            {shows.length === 0 ? (
              <div className="text-center text-muted p-10" style={{ fontSize: 13 }}>No shows match that search.</div>
            ) : shows.map((s) => {
              const active = sel?.id === s.id;
              return (
                <button
                  key={s.id}
                  className="ons-tap w-full text-left flex items-center gap-3 border-none cursor-pointer border-b border-border-2"
                  onClick={() => setSel(s)}
                  style={{
                    padding: "11px 18px",
                    background: active ? "#e9efe7" : "transparent",
                    borderLeft: active ? "2px solid #1d5536" : "2px solid transparent",
                    borderBottom: "1px solid #ebe5d8",
                  }}
                >
                  <div className="font-mono shrink-0" style={{ fontSize: 10, color: active ? "#1d5536" : "#736e5f", width: 70 }}>
                    {s.date}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-ink truncate" style={{ fontSize: 13.5, fontWeight: active ? 600 : 400 }}>
                      {s.venue}
                    </div>
                    <div className="font-mono text-faint mt-px" style={{ fontSize: 11 }}>{loc(s)}</div>
                  </div>
                  {s.upcoming && (
                    <span className="font-mono" style={{ fontSize: 8, letterSpacing: "0.5px", color: "#9a6a1e", border: "1px solid rgba(154,106,30,0.33)", borderRadius: 999, padding: "2px 7px" }}>
                      SOON
                    </span>
                  )}
                  {s.videoId && <OnsIcon name="play" size={17} stroke={1.6} style={{ color: active ? "#1d5536" : "#a39d8c" }} />}
                </button>
              );
            })}
          </div>
        </Card>
        <p className="font-mono text-faint mt-[10px]" style={{ fontSize: 9, lineHeight: 1.5 }}>
          NO LAT/LNG IN KGLW'S API — THIS IS A LIST/SEARCH EXPLORER, NOT A LITERAL GLOBE. GEOCODING PASS PENDING.
        </p>
      </div>

      {/* Detail / player */}
      <div>
        <Card pad={0} accent style={{ overflow: "hidden" }}>
          {sel?.videoId ? (
            <div>
              <div style={{ position: "relative", aspectRatio: "16/9", background: "#000" }}>
                <iframe
                  title={sel.venue ?? ""}
                  src={`https://www.youtube-nocookie.com/embed/${sel.videoId}?rel=0&modestbranding=1`}
                  style={{ position: "absolute", inset: 0, width: "100%", height: "100%", border: "none" }}
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                  allowFullScreen
                />
              </div>
              <div style={{ padding: "16px 18px" }}>
                <div className="flex justify-between items-start gap-3">
                  <div>
                    <div className="font-serif font-bold text-ink" style={{ fontSize: 20 }}>{sel.venue}</div>
                    <div className="text-muted mt-0.5" style={{ fontSize: 12 }}>{loc(sel)} · {sel.date}</div>
                  </div>
                  <span className="font-mono text-green shrink-0" style={{ fontSize: 9, border: "1px solid rgba(29,85,54,0.27)", borderRadius: 999, padding: "3px 9px", whiteSpace: "nowrap" }}>
                    ● RECORDING
                  </span>
                </div>
                <div className="flex gap-[18px] mt-[14px] pt-[14px] border-t border-border-2 font-mono text-muted" style={{ fontSize: 10 }}>
                  <span>TOUR · {sel.tour}</span>
                  <span>SHOW #{sel.id}</span>
                  <a href="https://kglw.net" target="_blank" rel="noopener noreferrer" className="ml-auto text-green no-underline">OPEN ON KGLW.NET ↗</a>
                </div>
              </div>
            </div>
          ) : sel ? (
            <div>
              <div style={{ aspectRatio: "16/9", background: "repeating-linear-gradient(135deg, #efebe1, #efebe1 9px, #fbfaf5 9px, #fbfaf5 18px)" }} className="grid place-items-center">
                <div className="text-center">
                  <div className="text-faint mb-[10px]"><OnsIcon name="kglw" size={34} stroke={1.3} /></div>
                  <div className="font-mono text-faint" style={{ fontSize: 10, letterSpacing: "1px" }}>NO RECORDING INGESTED</div>
                </div>
              </div>
              <div style={{ padding: "16px 18px" }}>
                <div className="font-serif font-bold" style={{ fontSize: 20 }}>{sel.venue}</div>
                <div className="text-muted mt-0.5" style={{ fontSize: 12 }}>{loc(sel)} · {sel.date}</div>
                <p className="text-muted mt-3" style={{ fontSize: 12, lineHeight: 1.5 }}>
                  No YouTube recording linked yet. Only flagged shows carry a watchable version.
                </p>
              </div>
            </div>
          ) : (
            <Empty message="Select a show to view." />
          )}
        </Card>
      </div>
    </div>
  );
}

// ── Song Explorer ──
function SongExplorer({ songs: catalog }: { songs: KglwSong[] }) {
  const [q, setQ] = useState("");
  const [songName, setSongName] = useState(catalog[0]?.name ?? "");
  const song = catalog.find((s) => s.name === songName) || catalog[0];

  const songs = useMemo(() => {
    const ql = q.trim().toLowerCase();
    return catalog
      .filter((s) => !ql || s.name.toLowerCase().includes(ql))
      .sort((a, b) => (b.versions ?? 0) - (a.versions ?? 0));
  }, [catalog, q]);

  const maxV = Math.max(...catalog.map((s) => s.versions ?? 0), 1);

  return (
    <div className="grid gap-[22px]" style={{ gridTemplateColumns: "1.05fr 1.25fr" }}>
      <div>
        <Card pad={0}>
          <div className="border-b border-border-2" style={{ padding: "16px 18px 14px" }}>
            <K style={{ marginBottom: 10 }}>Scan the catalog · {catalog.length} songs</K>
            <div className="flex items-center gap-2">
              <OnsIcon name="search" size={15} stroke={1.7} style={{ color: "#a39d8c" }} />
              <input className="ons-input flex-1" value={q} onChange={(e) => setQ(e.target.value)} placeholder='Search "Rattlesnake", "River"…' />
              <span className="font-mono text-faint whitespace-nowrap" style={{ fontSize: 9.5 }}>{songs.length}</span>
            </div>
          </div>
          <div className="ons-scroll" style={{ maxHeight: 470, overflowY: "auto" }}>
            {songs.map((s) => {
              const active = s.name === songName;
              return (
                <button
                  key={s.name}
                  className="ons-tap w-full text-left flex items-center gap-3 border-none cursor-pointer"
                  onClick={() => setSongName(s.name)}
                  style={{
                    padding: "12px 18px",
                    background: active ? "#e9efe7" : "transparent",
                    borderLeft: active ? "2px solid #1d5536" : "2px solid transparent",
                    borderBottom: "1px solid #ebe5d8",
                  }}
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-ink" style={{ fontSize: 14, fontWeight: active ? 600 : 400 }}>{s.name}</div>
                    <div className="font-mono text-faint mt-0.5" style={{ fontSize: 10.5 }}>
                      {s.versions} versions
                    </div>
                  </div>
                  <div className="shrink-0 rounded overflow-hidden" style={{ width: 54, height: 4, background: "#efebe1" }}>
                    <div className="rounded" style={{ width: `${((s.versions ?? 0) / maxV) * 100}%`, height: "100%", background: active ? "#1d5536" : "#e6e3dc" }} />
                  </div>
                </button>
              );
            })}
          </div>
        </Card>
      </div>

      <div>
        <Card pad={0} accent style={{ overflow: "hidden" }}>
          {song ? (
            <div>
              <div
                style={{ aspectRatio: "16/9", background: "repeating-linear-gradient(135deg, #efebe1, #efebe1 9px, #fbfaf5 9px, #fbfaf5 18px)" }}
                className="grid place-items-center"
              >
                <div className="text-center">
                  <div className="text-faint mb-[10px]"><OnsIcon name="music" size={34} stroke={1.3} /></div>
                  <div className="font-mono text-faint" style={{ fontSize: 10, letterSpacing: "1px" }}>SONG EXPLORER</div>
                </div>
              </div>
              <div style={{ padding: "16px 18px" }}>
                <div className="font-serif font-bold" style={{ fontSize: 24 }}>{song.name}</div>
                <div className="text-muted mt-0.5" style={{ fontSize: 12 }}>
                  {song.versions} live versions
                </div>
                <p className="text-muted mt-3" style={{ fontSize: 12, lineHeight: 1.5 }}>
                  Timestamped performances and embedded video playback are pending a manual overlay of KGLW's setlist data with YouTube recordings.
                </p>
              </div>
            </div>
          ) : (
            <Empty message="Select a song to view." />
          )}
        </Card>
      </div>
    </div>
  );
}

export default function KglwPage() {
  const [shows, setShows] = useState<KglwShow[] | null>(null);
  const [songs, setSongs] = useState<KglwSong[] | null>(null);
  const [mode, setMode] = useState<"shows" | "songs">("shows");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([kglwApi.shows({ limit: 1200 }), kglwApi.songs()])
      .then(([sh, so]) => { setShows(sh); setSongs(so); })
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!shows || !songs) return <Loading />;

  const TABS: Array<[string, string, string]> = [
    ["shows", "Shows", "shows"],
    ["songs", "Songs", "music"],
  ];

  return (
    <div className="ons-page" style={{ padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" }}>
      <PageHead
        title="King Gizzard"
        kicker="Live catalog · via kglw.net"
        right={
          <div className="flex gap-1 rounded-full" style={{ background: "#fbfaf5", border: "1px solid #e6e3dc", padding: 4 }}>
            {TABS.map(([k, l, icon]) => (
              <button
                key={k}
                className="ons-tap flex items-center gap-[7px] border-none cursor-pointer rounded-full"
                onClick={() => setMode(k as "shows" | "songs")}
                style={{
                  fontSize: 12, fontWeight: 500, padding: "7px 15px",
                  background: mode === k ? "#1d5536" : "transparent",
                  color: mode === k ? "#fff" : "#736e5f",
                }}
              >
                <OnsIcon name={icon} size={14} stroke={1.7} />
                {l}
              </button>
            ))}
          </div>
        }
      />

      {mode === "shows" ? <ShowExplorer shows={shows} /> : <SongExplorer songs={songs} />}
    </div>
  );
}
