"use client";

import { useEffect, useState } from "react";
import { musicApi, type MusicSummary, type MusicDaily10, type TopArtist, type TopTrack } from "@/lib/api";
import {
  Card, PageHead, Stat, StatBand, K, Empty, Loading, ErrorState,
} from "@/components/ui/primitives";
import { OnsIcon } from "@/components/ui/icons";

export default function MusicPage() {
  const [summary, setSummary] = useState<MusicSummary | null>(null);
  const [daily10, setDaily10] = useState<MusicDaily10 | null>(null);
  const [artists, setArtists] = useState<TopArtist[] | null>(null);
  const [tracks, setTracks] = useState<TopTrack[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      musicApi.summary(),
      musicApi.daily10(),
      musicApi.topArtists(10),
      musicApi.topTracks(10),
    ])
      .then(([s, d, a, t]) => { setSummary(s); setDaily10(d); setArtists(a); setTracks(t); })
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!summary || !daily10 || !artists || !tracks) return <Loading />;

  const hrs = summary.minutes_ytd != null ? Math.round(summary.minutes_ytd / 60) : null;
  const goalHrs = summary.goal_minutes != null ? Math.round(summary.goal_minutes / 60) : null;
  const maxArtistMinutes = Math.max(...artists.map((a) => a.minutes), 1);

  return (
    <div className="ons-page" style={{ padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" }}>
      <PageHead
        title="Music"
        kicker="2026 · via Spotify"
        right={
          <div className="font-mono text-right text-faint" style={{ fontSize: 9.5 }}>
            {summary.unique_artists != null ? `${summary.unique_artists.toLocaleString()} ARTISTS` : "—"}<br />
            {summary.unique_tracks != null ? `${summary.unique_tracks.toLocaleString()} TRACKS` : "—"}
          </div>
        }
      />

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

      <div className="grid gap-[22px] items-start" style={{ gridTemplateColumns: "1.5fr 1fr" }}>
        {/* Top artists + tracks */}
        <div>
          <Card pad={0} style={{ marginBottom: 22 }}>
            <div className="flex justify-between items-center" style={{ padding: "16px 18px 12px" }}>
              <K>Top Artists · YTD</K>
            </div>
            <div style={{ padding: "0 18px 16px" }}>
              {artists.length === 0 ? (
                <Empty message="No listening data for this year yet." />
              ) : (
                artists.map((a, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-[13px] border-t border-border-2"
                    style={{ padding: "11px 0" }}
                  >
                    <span
                      className="font-serif font-bold"
                      style={{ fontSize: 17, color: i === 0 ? "#1d5536" : "#a39d8c", width: 22 }}
                    >
                      {i + 1}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="truncate" style={{ fontSize: 13.5, fontWeight: i === 0 ? 600 : 400 }}>
                        {a.artist}
                      </div>
                      <div className="rounded mt-1.5 overflow-hidden" style={{ height: 4, background: "#efebe1" }}>
                        <div
                          className="rounded"
                          style={{
                            width: `${(a.minutes / maxArtistMinutes) * 100}%`,
                            height: "100%",
                            background: i === 0 ? "#1d5536" : "#2f6b43",
                          }}
                        />
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="font-mono font-semibold" style={{ fontSize: 12 }}>
                        {Math.round(a.minutes / 60)}h
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </Card>

          <Card pad={0}>
            <div style={{ padding: "16px 18px 12px" }}><K>Most-Played Tracks</K></div>
            <div style={{ padding: "0 18px 14px" }}>
              {tracks.length === 0 ? (
                <Empty message="No listening data for this year yet." />
              ) : (
                tracks.map((t, i) => (
                  <div
                    key={i}
                    className="ons-row flex items-center gap-3 border-t border-border-2"
                    style={{ padding: "10px 6px", margin: "0 -6px" }}
                  >
                    <span className="font-mono text-faint" style={{ fontSize: 10, width: 16 }}>{i + 1}</span>
                    <div className="flex-1">
                      <div style={{ fontSize: 13 }}>{t.track}</div>
                      <div className="text-faint" style={{ fontSize: 10.5 }}>{t.artist}</div>
                    </div>
                    <span className="font-mono text-muted" style={{ fontSize: 11 }}>{Math.round(t.minutes)}m</span>
                  </div>
                ))
              )}
            </div>
          </Card>
        </div>

        {/* Daily 10 + News */}
        <div>
          <Card accent pad={0} style={{ overflow: "hidden", marginBottom: 22 }}>
            {daily10.available && daily10.cover_image_path ? (
              <div style={{ position: "relative", borderBottom: "1px solid #ebe5d8" }}>
                <img
                  src={`${process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api"}/music/daily10/cover`}
                  alt="Today's Daily 10 cover art"
                  style={{ width: "100%", aspectRatio: "16/9", objectFit: "cover", display: "block" }}
                  onError={(e) => {
                    // Falls back to the placeholder if the file is
                    // somehow missing despite cover_image_path being
                    // set (e.g. covers/ dir cleared, but the JSON entry
                    // wasn't regenerated) — same honest-gap pattern as
                    // every other "data says X but the file isn't there"
                    // case in this app.
                    (e.target as HTMLImageElement).style.display = "none";
                  }}
                />
                <span
                  className="absolute font-mono text-faint"
                  style={{
                    top: 10, right: 12, fontSize: 8, letterSpacing: "0.5px",
                    border: "1px solid #e6e3dc", borderRadius: 999, padding: "2px 8px",
                    background: "rgba(251,250,245,0.85)",
                  }}
                >
                  gpt-image-1
                </span>
              </div>
            ) : (
              <div
                style={{
                  aspectRatio: "16/9",
                  background: "repeating-linear-gradient(135deg, #efebe1, #efebe1 8px, #fbfaf5 8px, #fbfaf5 16px)",
                  display: "grid",
                  placeItems: "center",
                  borderBottom: "1px solid #ebe5d8",
                  position: "relative",
                }}
              >
                <div className="text-center p-4">
                  <div className="font-mono text-green" style={{ fontSize: 9, letterSpacing: "1.5px" }}>
                    DAILY 10 · COVER
                  </div>
                  <div className="font-serif font-semibold text-ink mt-1.5" style={{ fontSize: 17 }}>
                    {daily10.available ? "Today's Playlist" : "No Playlist Yet"}
                  </div>
                  {daily10.available && (
                    <p className="text-faint mt-2 mb-0" style={{ fontSize: 10 }}>
                      No cover saved locally yet — only playlists generated after this fix shipped will have one.
                    </p>
                  )}
                </div>
              </div>
            )}
            <div style={{ padding: "14px 18px" }}>
              {daily10.available ? (
                <>
                  <p className="m-0" style={{ fontSize: 11.5, lineHeight: 1.5, color: "#232a22" }}>
                    {daily10.description}
                  </p>
                  {daily10.tewnidge_artists && daily10.tewnidge_artists.length > 0 && (
                    <p className="text-faint mt-3 mb-0" style={{ fontSize: 10.5 }}>
                      Featuring: {daily10.tewnidge_artists.slice(0, 4).join(", ")}
                    </p>
                  )}
                </>
              ) : (
                <Empty message="No playlist generated yet today." />
              )}
            </div>
          </Card>

          <Card>
            <K style={{ marginBottom: 10 }}>Music News</K>
            <div className="flex gap-[11px] items-start">
              <span className="text-faint mt-px">
                <OnsIcon name="music" size={16} stroke={1.5} />
              </span>
              <div>
                <div className="text-ink" style={{ fontSize: 13 }}>Not configured</div>
                <p className="text-faint m-0 mt-[3px]" style={{ fontSize: 11.5, lineHeight: 1.5 }}>
                  NEWS_API_KEY isn't set in .env — expected, not a bug. Set it to pull headlines here.
                </p>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
