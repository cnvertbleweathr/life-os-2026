"use client";

// King Gizzard (Logbook Color). A fan catalogue, neutral like the other Play pages. Real data only:
//   shows        /kglw/shows (kglw.net, 1,233 rows) + /kglw/youtube-matches (full shows on the band's channel)
//   videos       /kglw/music-videos
//   jam chart    /kglw/jamchart (kglw.net's notable versions; there are no setlists, so no play counts)
//   on this day  /kglw/shows/on-this-day
// Fixes from docs/design/critique.md §8: the list is windowed (40 rows at a time, by year) instead of 1,233 rows
// in the DOM; HTML entities are decoded; the player sits above the list on phones and says why it's featured;
// the filters are a select and a search that fit a phone. The Songs tab showed "undefined versions" (the API has
// no play counts); it's now the jam chart.

import { useEffect, useMemo, useRef, useState } from "react";
import { kglwApi, type KglwShow, type KglwMusicVideo, type KglwJamchartEntry } from "@/lib/api";
import { PageHead, Loading, ErrorState } from "@/components/ui/primitives";
import { PixelScene } from "@/components/ui/PixelScene";
import { isoDenver, fmt, short, plural, decode, daysBetween } from "@/lib/dates";

const PAGE = 40;
const long = (iso: string) => fmt(iso, { month: "short", day: "numeric", year: "numeric" });
const US = new Set(["USA", "United States"]);
const place = (s: { city?: string; state?: string | null; country?: string }) =>
  [decode(s.city ?? ""), s.state && US.has(s.country ?? "") ? s.state : null, US.has(s.country ?? "") ? null : s.country].filter(Boolean).join(", ");
const views = (n?: number | null) => (n == null ? "–" : n >= 1e6 ? `${(n / 1e6).toFixed(1).replace(/\.0$/, "")}M` : n >= 1e3 ? `${Math.round(n / 1e3)}K` : String(n));
const length = (iso?: string | null) => { const m = /PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/.exec(iso ?? ""); if (!m) return "–"; const h = +(m[1] ?? 0), mi = +(m[2] ?? 0), s = +(m[3] ?? 0); return h ? `${h}:${String(mi).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${mi}:${String(s).padStart(2, "0")}`; };
const tourOf = (t?: string | null) => (!t || /^not part of a tour$/i.test(t) ? "–" : decode(t));
/** "Primavera Sound Barcelona, Spain": the show's title (or venue) and the place, without saying the city twice. */
const nameAndPlace = (s: KglwShow) => { const n = decode(s.show_title || s.venue_name), c = decode(s.city); return n.includes(c) ? `${n}, ${place(s).split(", ").slice(1).join(", ") || c}` : `${n}, ${place(s)}`; };
const setlist = (permalink: string) => `https://kglw.net/setlists/${permalink}`;

type Sel = { kind: "show"; s: KglwShow } | { kind: "mv"; v: KglwMusicVideo };

export default function KglwPage() {
  const [today, setToday] = useState<string | null>(null);
  const [shows, setShows] = useState<KglwShow[] | null>(null);
  const [mvs, setMvs] = useState<KglwMusicVideo[]>([]);
  const [jam, setJam] = useState<KglwJamchartEntry[]>([]);
  const [otd, setOtd] = useState<KglwShow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"shows" | "videos" | "jam">("shows");
  const [q, setQ] = useState("");
  const [year, setYear] = useState("all");
  const [recorded, setRecorded] = useState(false);
  const [count, setCount] = useState(PAGE);
  const [sel, setSel] = useState<Sel | null>(null);
  const [song, setSong] = useState<number | null>(null);
  const detailRef = useRef<HTMLElement>(null);

  useEffect(() => {
    setToday(isoDenver(new Date()));
    Promise.all([kglwApi.shows({ limit: 5000 }), kglwApi.musicVideos()])
      .then(([sh, mv]) => { setShows(sh); setMvs(mv); })
      .catch((e) => setError(e.message));
    kglwApi.jamchart().then(setJam).catch(() => {});
    kglwApi.onThisDay().then(setOtd).catch(() => {});
  }, []);

  const recordings = useMemo(() => (shows ?? []).filter((s) => s.videoId), [shows]);
  // Featured by default: the newest thing you can watch, a full show or a music video.
  const featured = useMemo<Sel | null>(() => {
    const r = [...recordings].sort((a, b) => b.date!.localeCompare(a.date!))[0];
    const v = [...mvs].sort((a, b) => b.release_date.localeCompare(a.release_date))[0];
    if (!r && !v) return null;
    return !v || (r && r.date! >= v.release_date) ? { kind: "show", s: r! } : { kind: "mv", v };
  }, [recordings, mvs]);
  const current = sel ?? featured;

  const list = useMemo(() => {
    if (!shows) return [];
    const ql = q.trim().toLowerCase();
    return shows
      .filter((s) => year === "all" || (year === "upcoming" ? s.upcoming : String(s.show_year) === year))
      .filter((s) => !recorded || s.videoId)
      .filter((s) => !ql || [s.venue_name, s.city, s.state, s.country, s.tour_name, s.show_title, s.date].map((x) => decode(String(x ?? ""))).join(" ").toLowerCase().includes(ql))
      .sort((a, b) => (a.upcoming !== b.upcoming ? (a.upcoming ? -1 : 1) : a.upcoming ? a.date!.localeCompare(b.date!) : b.date!.localeCompare(a.date!)));
  }, [shows, q, year, recorded]);

  const songs = useMemo(() => {
    const m = new Map<number, { id: number; name: string; n: number; latest: string }>();
    jam.forEach((j) => { const e = m.get(j.song_id) ?? { id: j.song_id, name: decode(j.song_name), n: 0, latest: "" }; e.n++; if (j.show_date > e.latest) e.latest = j.show_date; m.set(j.song_id, e); });
    return Array.from(m.values()).sort((a, b) => b.n - a.n || b.latest.localeCompare(a.latest));
  }, [jam]);

  if (error) return <div className="ons-page" style={{ padding: "34px 44px 48px" }}><ErrorState message={error} /></div>;
  if (!shows || !today) return <Loading label="Loading the catalogue…" />;

  const played = shows.filter((s) => !s.upcoming);
  const upcoming = shows.filter((s) => s.upcoming).sort((a, b) => a.date!.localeCompare(b.date!));
  const next = upcoming[0];
  const nextTour = next ? upcoming.filter((s) => s.tour_name === next.tour_name).length : 0;
  const northAmerica = upcoming.filter((s) => US.has(s.country) || s.country === "Canada" || s.country === "Mexico");
  const colorado = played.filter((s) => s.state === "CO" && US.has(s.country)).sort((a, b) => b.date!.localeCompare(a.date!));
  const thisYear = played.filter((s) => s.show_year === +today.slice(0, 4)).length;
  const first = [...played].sort((a, b) => a.date!.localeCompare(b.date!))[0];
  const years = Array.from(new Set(shows.map((s) => s.show_year))).sort((a, b) => b - a);
  const jamBy = new Map(shows.map((s) => [s.show_id, s]));
  const songSel = song ?? songs[0]?.id ?? null;
  const versions = jam.filter((j) => j.song_id === songSel).sort((a, b) => b.show_date.localeCompare(a.show_date));

  const pick = (x: Sel) => {
    setSel(x);
    if (window.innerWidth < 1101) detailRef.current?.scrollIntoView({ block: "start" });
  };
  const isSel = (x: Sel) => !!current && current.kind === x.kind && (x.kind === "show" ? current.kind === "show" && current.s.show_id === x.s.show_id : current.kind === "mv" && current.v.video_id === x.v.video_id);

  const lede = (
    <>
      {next ? <><b>Next show: {nameAndPlace(next)}, {long(next.date!)}</b>, the first of {nextTour} on the {next.tour_name} run{northAmerica.length ? `, with ${plural(northAmerica.length, "date")} in North America` : "; nothing announced in North America yet"}.{" "}</> : <>No shows announced right now.{" "}</>}
      {colorado.length > 0 && <>They&apos;ve played Colorado {colorado.length} times, most recently {decode(colorado[0].venue_name)} in {decode(colorado[0].city)} on {long(colorado[0].date!)}.{" "}</>}
      {recordings.length > 0 && <>{plural(recordings.length, "full show")} and {plural(mvs.length, "music video")} are on the band&apos;s channel; pick one to watch.</>}
    </>
  );

  return (
    <div className="ons-page" style={{ padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" }}>
      <PageHead
        title="King Gizzard"
        titleSub="& the Lizard Wizard"
        kicker={`${plural(played.length, "show")} since ${first ? first.show_year : "–"} · ${upcoming.length} announced · from kglw.net and the band's YouTube channel`}
        sub={lede}
        scene={<PixelScene scene="kglw" data={{ shows: played.length }} label={`a lizard in a wizard hat plays a flute on stage; the marquee reads ${played.length} shows`} />}
      />

      <div className="ons-tiles" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))" }}>
        <section className="ons-tile">
          <h2>Shows played</h2>
          <div className="big n">{played.length.toLocaleString("en-US")}</div>
          <p>{thisYear} in {today.slice(0, 4)} · {plural(new Set(played.map((s) => s.venue_id)).size, "venue")}</p>
        </section>
        <section className="ons-tile">
          <h2>Next show</h2>
          <div className="big">{next ? short(next.date!) : "–"}</div>
          <p>{next ? <>{decode(next.show_title || next.venue_name)} · {place(next)}{next.date!.slice(0, 4) !== today.slice(0, 4) ? `, ${next.date!.slice(0, 4)}` : ""}</> : "Nothing announced."}</p>
          {next && <p className="tnote">In {plural(daysBetween(today, next.date!), "day")}</p>}
        </section>
        <section className="ons-tile">
          <h2>In Colorado</h2>
          <div className="big n">{colorado.length}</div>
          <p>{colorado[0] ? <>Last: {decode(colorado[0].venue_name)}, {long(colorado[0].date!)}</> : "Never played here."}</p>
          <p className="tnote">{Array.from(new Set(colorado.map((s) => decode(s.venue_name)))).slice(0, 3).join(" · ")}</p>
        </section>
        <section className="ons-tile">
          <h2>On this day</h2>
          <div className="big n">{otd.length}</div>
          <p>{otd.length ? otd.slice(0, 3).map((s) => `${s.show_year}: ${decode(s.venue_name)}, ${decode(s.city)}`).join(" · ") : `No shows on ${short(today)} in any year.`}</p>
        </section>
      </div>

      <div className="ons-tabs" role="tablist" aria-label="Catalogue">
        {([["shows", "Shows", played.length + upcoming.length], ["videos", "Music videos", mvs.length], ["jam", "Jam chart", jam.length]] as const).map(([k, l, n]) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{l}<span className="text-muted" style={{ fontWeight: 400 }}> · {n.toLocaleString("en-US")}</span></button>
        ))}
      </div>

      {tab !== "jam" ? (
        <div className="ons-grid ons-split">
          <section className="ons-card side" ref={detailRef} aria-label="Player">
            {current ? <Detail x={current} today={today} featured={!sel} /> : <p className="ons-note m-0">Nothing to watch yet.</p>}
          </section>

          {tab === "shows" ? (
            <section className="ons-card main" aria-labelledby="list-h">
              <div className="ons-ch"><h2 id="list-h">Shows</h2><span className="aside">{plural(list.length, "show")}{list.length > count ? `, showing ${count}` : ""}</span></div>
              <div className="ons-filters">
                <input className="ons-input" type="search" value={q} onChange={(e) => { setQ(e.target.value); setCount(PAGE); }} placeholder="Search venue, city, tour or date" aria-label="Search shows" />
                <select className="ons-select" value={year} onChange={(e) => { setYear(e.target.value); setCount(PAGE); }} aria-label="Year">
                  <option value="all">All years</option>
                  {upcoming.length > 0 && <option value="upcoming">Announced ({upcoming.length})</option>}
                  {years.map((y) => <option key={y} value={y}>{y}</option>)}
                </select>
                <label className="ons-check"><input type="checkbox" checked={recorded} onChange={(e) => { setRecorded(e.target.checked); setCount(PAGE); }} /> With a recording</label>
              </div>
              {list.length === 0 ? <p className="ons-note">Nothing matches. Try a city, a venue or a year.</p> : (
                <table className="ons-table">
                  <thead><tr><th>Date</th><th>Venue</th><th className="hide-p">Tour</th><th className="r"><span className="sr-only">Status</span></th></tr></thead>
                  <tbody>
                    {list.slice(0, count).map((s, i, arr) => {
                      const x: Sel = { kind: "show", s }, on = isSel(x);
                      const head = i === 0 || arr[i - 1].show_year !== s.show_year || arr[i - 1].upcoming !== s.upcoming;
                      return [
                        head && <tr key={`h-${s.show_year}-${s.upcoming}`} className="ons-yearrow"><td colSpan={4}>{s.upcoming ? "Announced" : s.show_year}</td></tr>,
                        <tr key={s.show_id} className={on ? "is-sel" : undefined}>
                          <td style={{ whiteSpace: "nowrap" }}>{short(s.date!)}</td>
                          <td><button type="button" className="ons-rowbtn" aria-pressed={on} onClick={() => pick(x)}>{decode(s.venue_name)}<span className="sub">{place(s)}{s.show_title ? ` · ${decode(s.show_title)}` : ""}</span></button></td>
                          <td className="hide-p text-muted" style={{ fontSize: 13 }}>{tourOf(s.tour_name)}</td>
                          <td className="r">{s.videoId ? <span className="ons-badge none">Recording</span> : null}</td>
                        </tr>,
                      ];
                    })}
                  </tbody>
                </table>
              )}
              {list.length > count && <button type="button" className="ons-tap ons-btn" style={{ marginTop: 12 }} onClick={() => setCount((n) => n + PAGE)}>Show {Math.min(PAGE, list.length - count)} more of {list.length - count}</button>}
              <p className="ons-note">Shows from kglw.net. A show has a recording when the band&apos;s YouTube channel has uploaded it.</p>
            </section>
          ) : (
            <section className="ons-card main" aria-labelledby="mv-h">
              <div className="ons-ch"><h2 id="mv-h">Music videos</h2><span className="aside">Newest first · official channel</span></div>
              <table className="ons-table">
                <thead><tr><th>Song</th><th>Released</th><th className="r hide-p">Length</th><th className="r">Views</th></tr></thead>
                <tbody>
                  {[...mvs].sort((a, b) => b.release_date.localeCompare(a.release_date)).map((v) => {
                    const x: Sel = { kind: "mv", v }, on = isSel(x);
                    return (
                      <tr key={v.video_id} className={on ? "is-sel" : undefined}>
                        <td><button type="button" className="ons-rowbtn" aria-pressed={on} onClick={() => pick(x)}>{decode(v.song_title)}</button></td>
                        <td style={{ whiteSpace: "nowrap" }}>{long(v.release_date)}</td>
                        <td className="r ons-n hide-p">{length(v.duration)}</td>
                        <td className="r ons-n">{views(v.view_count)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </section>
          )}
        </div>
      ) : (
        <div className="ons-grid">
          <section className="ons-card s4" aria-labelledby="songs-h">
            <div className="ons-ch"><h2 id="songs-h">Songs</h2><span className="aside">{plural(songs.length, "song")} · by notable versions</span></div>
            <div className="ons-scroll" style={{ maxHeight: 560, overflowY: "auto" }}>
              <table className="ons-table">
                <tbody>
                  {songs.map((s) => (
                    <tr key={s.id} className={s.id === songSel ? "is-sel" : undefined}>
                      <td><button type="button" className="ons-rowbtn" aria-pressed={s.id === songSel} onClick={() => setSong(s.id)}>{s.name}</button></td>
                      <td className="r ons-n">{s.n}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="ons-card s8" aria-labelledby="ver-h">
            <div className="ons-ch"><h2 id="ver-h">{songs.find((s) => s.id === songSel)?.name ?? "Versions"}</h2><span className="aside">{plural(versions.length, "notable version")}</span></div>
            <table className="ons-table">
              <thead><tr><th>Date</th><th>Where, and why it&apos;s on the chart</th><th className="r"><span className="sr-only">Links</span></th></tr></thead>
              <tbody>
                {versions.map((j) => {
                  const show = jamBy.get(j.show_id), note = decode(j.jamchart_note || j.footnote || "").trim();
                  return (
                    <tr key={j.uniqueid}>
                      <td style={{ whiteSpace: "nowrap", verticalAlign: "top" }}>{long(j.show_date)}</td>
                      <td>{decode(j.venue_name)}, {place(j)}{j.is_recommended && <> <span className="ons-badge ok">Recommended</span></>}{note && <span className="sub" style={{ marginTop: 4, maxWidth: "70ch" }}>{note}</span>}</td>
                      <td className="r" style={{ whiteSpace: "nowrap", verticalAlign: "top" }}>
                        {show?.videoId && <button type="button" className="ons-link ons-linkbtn" style={{ marginRight: 12 }} onClick={() => { setTab("shows"); pick({ kind: "show", s: show }); }}>Watch</button>}
                        <a className="ons-link" href={setlist(j.permalink)} target="_blank" rel="noreferrer">Setlist</a>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="ons-note">kglw.net&apos;s jam chart lists notable versions, not every performance. ONS doesn&apos;t load full setlists, so there are no play counts.</p>
          </section>
        </div>
      )}
    </div>
  );
}

function Detail({ x, today, featured }: { x: Sel; today: string; featured: boolean }) {
  if (x.kind === "mv") {
    const v = x.v;
    return (
      <>
        <div className="ons-ch"><h2>{decode(v.song_title)}</h2><span className="aside">{featured ? "Newest on the channel" : "Music video"}</span></div>
        <div className="ons-video"><iframe key={v.video_id} src={`https://www.youtube-nocookie.com/embed/${v.video_id}?rel=0`} title={decode(v.song_title)} allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowFullScreen /></div>
        <p className="ons-note">Released {long(v.release_date)} · {length(v.duration)} · {views(v.view_count)} views · <a className="ons-link" href={`https://www.youtube.com/watch?v=${v.video_id}`} target="_blank" rel="noreferrer">YouTube</a></p>
      </>
    );
  }
  const s = x.s;
  return (
    <>
      <div className="ons-ch"><h2>{decode(s.venue_name)}</h2><span className="aside">{featured ? "Newest recording" : s.upcoming ? "Announced" : s.videoId ? "Recording" : "Show"}</span></div>
      {s.videoId ? (
        <div className="ons-video"><iframe key={s.videoId} src={`https://www.youtube-nocookie.com/embed/${s.videoId}?rel=0`} title={`${decode(s.venue_name)}, ${long(s.date!)}`} allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowFullScreen /></div>
      ) : (
        <div className="ons-novideo">{s.upcoming ? `Not played yet: in ${plural(daysBetween(today, s.date!), "day")}.` : "No recording of this show on the band's channel."}</div>
      )}
      <p className="ons-note">{long(s.date!)} · {place(s)}{s.show_title ? ` · ${decode(s.show_title)}` : ""} · {tourOf(s.tour_name) === "–" ? "" : `${tourOf(s.tour_name)} · `}<a className="ons-link" href={setlist(s.permalink)} target="_blank" rel="noreferrer">{s.upcoming ? "kglw.net" : "Setlist"}</a></p>
    </>
  );
}
