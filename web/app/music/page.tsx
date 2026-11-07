"use client";

// Music (Logbook Color). Play pages have no life-area colour (DESIGN.md: a new area needs an explicit decision),
// so this page stays neutral: ink, rules and status pills. Real data only:
//   listening   /music/summary (spotify_metrics CSV) + /music/by-month (streams_clean.csv; also the export's last play)
//   top lists   /music/top-artists, /music/top-tracks (minutes this year)
//   daily 10    /music/daily10 (playlist id, buckets, Tewnidge artists) — Spotify embed plus a plain link
//   shows       /shows (AEG + Ticketmaster, whole-word match against your Spotify artists)
//   artist      /music/artist-of-the-day
// Fixes from docs/design/critique.md §9: Spotify minutes now agree with Goals (the goal sync read the wrong
// column); the page leads with what's on in Denver; no emoji; the embed has a fallback link.

import { useEffect, useMemo, useState } from "react";
import {
  musicApi, showsApi,
  type MusicSummary, type MusicDaily10, type ArtistOfTheDay, type Show, type TopArtist, type TopTrack, type MusicByMonth,
} from "@/lib/api";
import { PageHead, Loading, ErrorState } from "@/components/ui/primitives";
import { PixelScene } from "@/components/ui/PixelScene";
import { isoDenver, yearClock, daysBetween, fmt, short, plural, join, dayLabel, localTime, decode, addDays } from "@/lib/dates";

const PAGE = 20;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// Google Calendar "create event" link. Times are Denver-local with ctz set, so no UTC math; 3 hours long.
function gcalUrl(x: Show): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  const stamp = (d: Date, t: boolean) => `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}` + (t ? `T${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}00` : "");
  let dates: string;
  if (x.start_local) {
    const [d, t] = x.start_local.split("T"), [y, m, day] = d.split("-").map(Number), [h, mi] = t.split(":").map(Number);
    const start = new Date(Date.UTC(y, m - 1, day, h, mi));
    dates = `${stamp(start, true)}/${stamp(new Date(start.getTime() + 3 * 3600_000), true)}`;
  } else {
    const [y, m, day] = (x.date ?? "").split("-").map(Number), start = new Date(Date.UTC(y, m - 1, day));
    dates = `${stamp(start, false)}/${stamp(new Date(start.getTime() + 86_400_000), false)}`;
  }
  const p = new URLSearchParams({ action: "TEMPLATE", text: decode(x.title), dates, ctz: "America/Denver", location: x.location || x.venue_name || "", details: x.ticket_url ? `Tickets: ${x.ticket_url}` : "" });
  return `https://calendar.google.com/calendar/render?${p.toString()}`;
}

export default function MusicPage() {
  const [today, setToday] = useState<string | null>(null);
  const [summary, setSummary] = useState<MusicSummary | null>(null);
  const [months, setMonths] = useState<MusicByMonth | null>(null);
  const [daily10, setDaily10] = useState<MusicDaily10 | null>(null);
  const [artists, setArtists] = useState<TopArtist[]>([]);
  const [tracks, setTracks] = useState<TopTrack[]>([]);
  const [shows, setShows] = useState<Show[] | null | false>(null);
  const [aotd, setAotd] = useState<ArtistOfTheDay | null>(null);
  const [reroll, setReroll] = useState(0);
  const [mine, setMine] = useState(true);
  const [count, setCount] = useState(PAGE);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setToday(isoDenver(new Date()));
    musicApi.summary().then(setSummary).catch((e) => setError(e.message));
    musicApi.byMonth().then(setMonths).catch(() => setMonths({ months: [], last_played: null }));
    musicApi.daily10().then(setDaily10).catch(() => setDaily10({ available: false }));
    musicApi.topArtists(8).then(setArtists).catch(() => {});
    musicApi.topTracks(5).then(setTracks).catch(() => {});
    showsApi.list(false, 2000).then(setShows).catch(() => setShows(false));
  }, []);

  useEffect(() => {
    setAotd(null);
    musicApi.artistOfTheDay(reroll).then(setAotd).catch((e) => setAotd({ available: false, reason: e.message }));
  }, [reroll]);

  const yours = useMemo(() => (shows ? shows.filter((s) => s.is_my_artist) : []), [shows]);

  if (error) return <div className="ons-page" style={{ padding: "34px 44px 48px" }}><ErrorState message={error} /></div>;
  if (!summary || !months || !today) return <Loading label="Loading music…" />;

  const c = yearClock(today);
  const minutes = summary.minutes_ytd ?? 0, goal = summary.goal_minutes ?? 0, hours = Math.round(minutes / 60);
  const through = months.last_played;
  const covered = through ? daysBetween(`${c.y}-01-01`, through) + 1 : c.dayOfYear;
  const perDay = minutes / Math.max(1, covered);
  const needPerDay = goal ? Math.max(0, goal - minutes) / Math.max(1, c.daysLeft) : 0;
  const state = !goal ? null : minutes >= goal ? ["ok", "Done"] : minutes >= goal * c.frac ? ["ok", "On track"] : needPerDay > perDay * 3 ? ["off", "Out of reach"] : ["risk", "Behind"];
  const stale = through ? daysBetween(through, today) : null;

  const weekEnd = addDays(today, 6);
  const soon = yours.filter((s) => s.date >= today && s.date <= weekEnd);
  const soonBits = soon.slice(0, 3).map((s) => `${decode(s.title)} ${s.date === today ? "tonight" : dayLabel(s.date, today) === "Tomorrow" ? "tomorrow" : `on ${fmt(s.date, { weekday: "long" })}`} at ${decode(s.venue_name)}`);
  const nextYours = yours.find((s) => s.date >= today);

  const lede = (
    <>
      <b>{plural(hours, "hour")} of listening</b> this year, {Math.round((minutes / Math.max(1, goal)) * 100)}% of the {goal.toLocaleString("en-US")}-minute goal.{" "}
      {state && state[0] === "off" ? <>That goal is out of reach: you average {Math.round(perDay)} minutes a day, and the rest would take {(needPerDay / 60).toFixed(1)} hours a day.{" "}</>
        : state && state[0] !== "ok" ? <>The rest needs {Math.round(needPerDay)} minutes a day, against your {Math.round(perDay)}.{" "}</> : null}
      {soon.length > 0 ? <><b>{plural(soon.length, "show")} by your artists in Denver this week</b>, starting with {soonBits[0]}.{" "}</>
        : nextYours ? <>Next of your artists in Denver: {decode(nextYours.title)}, {short(nextYours.date)} at {decode(nextYours.venue_name)}.{" "}</> : null}
      {stale != null && stale > 3 && <>Spotify&apos;s export runs through {short(through!)}, so the last {plural(stale, "day")} aren&apos;t counted yet.</>}
    </>
  );

  // ── Shows list, grouped by day ─────────────────────────────────────────────
  const list = (mine ? yours : shows || []).filter((s) => s.date >= today);
  const visible = list.slice(0, count);

  // ── Monthly chart ────────────────────────────────────────────────────────
  const byM = new Map(months.months.map((m) => [m.month, m.minutes]));
  const perMonthGoal = goal / 12;
  const thruMonth = through ? +through.slice(5, 7) : 0, nowMonth = +today.slice(5, 7);
  const mMax = Math.max(perMonthGoal, ...months.months.map((m) => m.minutes), 1);
  const CW = 520, CH = 180, L = 44, B = 22, T = 8;
  const bw = (CW - L) / 12;
  const yOf = (v: number) => T + (1 - v / mMax) * (CH - T - B);
  const step = mMax > 4000 ? 2000 : 1000;

  return (
    <div className="ons-page" style={{ padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" }}>
      <PageHead
        title="Music"
        kicker={`${c.y} · Spotify history through ${through ? short(through) : "–"} · Denver shows from AEG and Ticketmaster`}
        sub={lede}
        right={daily10?.available && daily10.playlist_id ? <a className="ons-tap ons-btn" href={`https://open.spotify.com/playlist/${daily10.playlist_id}`} target="_blank" rel="noreferrer">Open today&apos;s Daily 10</a> : undefined}
        scene={<PixelScene scene="music" data={{ hours, poster: nextYours ? `${+nextYours.date.slice(5, 7)}-${+nextYours.date.slice(8, 10)}` : "" }}
          label={`a listener in headphones by a turntable; ${hours} hours on the amp${nextYours ? `, a poster for ${decode(nextYours.title)} on ${short(nextYours.date)}` : ""}`} />}
      />

      <div className="ons-tiles" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))" }}>
        <section className="ons-tile">
          <h2>Listening in {c.y}</h2>
          <div className="big n">{hours.toLocaleString("en-US")} h</div>
          <p>{Math.round(minutes).toLocaleString("en-US")} of {goal.toLocaleString("en-US")} minutes · {plural(summary.days_listened ?? 0, "day")} with a play</p>
          {goal > 0 && <div className="ons-bar l-none" style={{ marginTop: "auto" }}><b style={{ width: `${Math.min(100, (minutes / goal) * 100)}%` }} /><i style={{ left: `${c.frac * 100}%` }} /></div>}
        </section>
        <section className="ons-tile">
          <h2>Minutes needed</h2>
          <div className="big n">{goal ? `${Math.round(needPerDay)}/day` : "–"}</div>
          <p>For the {plural(c.daysLeft, "day")} left. You average {Math.round(perDay)} a day.</p>
          {state && <p className="tnote"><span className={`ons-badge ${state[0]}`}>{state[1]}</span></p>}
        </section>
        <section className="ons-tile">
          <h2>Most played</h2>
          <div className="big" style={{ overflowWrap: "anywhere" }}>{summary.top_artist ?? "–"}</div>
          <p>By number of plays. {artists[0] && artists[0].artist !== summary.top_artist ? `By minutes: ${artists[0].artist}, ${Math.round(artists[0].minutes)} min.` : ""}</p>
          <p className="tnote">{(summary.unique_artists ?? 0).toLocaleString("en-US")} artists · {(summary.unique_tracks ?? 0).toLocaleString("en-US")} tracks</p>
        </section>
        <section className="ons-tile">
          <h2>Your artists in Denver</h2>
          <div className="big n">{shows ? yours.length : "–"}</div>
          <p>{shows ? `of ${shows.length} upcoming shows${soon.length ? ` · ${soon.length} in the next 7 days` : ""}` : "Shows didn't load."}</p>
          <p className="tnote">Matched by artist name in the show title.</p>
        </section>
      </div>

      <div className="ons-grid">
        <section className="ons-card s8" aria-labelledby="shows-h">
          <div className="ons-ch"><h2 id="shows-h">Shows in Denver</h2><span className="aside">Soonest first · tickets open in a new tab</span></div>
          <div className="ons-tabs" role="tablist" aria-label="Which shows" style={{ marginBottom: 8 }}>
            <button type="button" role="tab" aria-selected={mine} onClick={() => { setMine(true); setCount(PAGE); }}>Your artists<span className="text-muted" style={{ fontWeight: 400 }}> · {yours.length}</span></button>
            <button type="button" role="tab" aria-selected={!mine} onClick={() => { setMine(false); setCount(PAGE); }}>All<span className="text-muted" style={{ fontWeight: 400 }}> · {shows ? shows.length : 0}</span></button>
          </div>
          {shows === false ? <p className="ons-note m-0">Couldn&apos;t load shows.</p>
            : shows === null ? <p className="ons-note m-0">Loading shows…</p>
            : list.length === 0 ? <p className="ons-note m-0">No upcoming shows{mine ? " by your artists" : ""}.</p>
            : (
              <table className="ons-table">
                <thead><tr><th>Show</th><th className="r">Doors</th><th className="r"><span className="sr-only">Links</span></th></tr></thead>
                <tbody>
                  {visible.map((s, i) => [
                    (i === 0 || visible[i - 1].date !== s.date) && (
                      <tr key={`d-${s.date}`} className="ons-yearrow"><td colSpan={3} style={s.date === today ? { color: "var(--hue)" } : undefined}>{dayLabel(s.date, today)}</td></tr>
                    ),
                    <tr key={`${s.ticket_url}-${i}`}>
                      <td>
                        <span style={{ fontWeight: s.is_my_artist ? 500 : 400 }}>{decode(s.title)}</span>
                        {!mine && s.is_my_artist && <> <span className="ons-badge none">Your artist</span></>}
                        <span className="sub">{decode(s.venue_name)}<span className="hide-p"> · {s.source}</span></span>
                      </td>
                      <td className="r ons-n" style={{ whiteSpace: "nowrap" }}>{localTime(s.start_local) || "–"}</td>
                      <td className="r" style={{ whiteSpace: "nowrap" }}>
                        {s.ticket_url && <a className="ons-link" href={s.ticket_url} target="_blank" rel="noreferrer" aria-label={`Tickets for ${decode(s.title)} (opens in a new tab)`}>Tickets</a>}
                        <a className="ons-link hide-p" style={{ marginLeft: 12 }} href={gcalUrl(s)} target="_blank" rel="noreferrer" aria-label={`Add ${decode(s.title)} to Google Calendar (opens in a new tab)`}>Calendar</a>
                      </td>
                    </tr>,
                  ])}
                </tbody>
              </table>
            )}
          {list.length > count && <button type="button" className="ons-tap ons-btn" style={{ marginTop: 12 }} onClick={() => setCount((n) => n + PAGE)}>Show {Math.min(PAGE, list.length - count)} more of {list.length - count}</button>}
          <p className="ons-note">&ldquo;Your artists&rdquo; are artists from your Spotify playlists whose name appears as a whole word in the show title, so tributes and festivals can match too.</p>
        </section>

        <div className="s4 ons-col no-stretch">
          <section className="ons-card" aria-labelledby="d10-h">
            <div className="ons-ch"><h2 id="d10-h">Daily 10</h2><span className="aside">{daily10?.date ? `Made ${short(daily10.date)}` : ""}</span></div>
            {!daily10 ? <p className="ons-note m-0">Loading…</p>
              : !daily10.available || !daily10.playlist_id ? <p className="ons-note m-0">No playlist yet today. It&apos;s made during the morning sync.</p>
              : <>
                <p className="m-0" style={{ fontSize: 14, lineHeight: "21px", color: "var(--ink-2)" }}>
                  Five tracks from your 500 most played, and five you haven&apos;t heard by artists from Tewnidge{daily10.tewnidge_artists?.length ? <>: {join(daily10.tewnidge_artists.slice(0, 5))}</> : null}.
                </p>
                <iframe className="ons-embed" src={`https://open.spotify.com/embed/playlist/${daily10.playlist_id}?utm_source=generator&theme=0`} height="352" loading="lazy"
                        allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture" title="Today's Daily 10 playlist on Spotify" />
                <a className="ons-link" href={`https://open.spotify.com/playlist/${daily10.playlist_id}`} target="_blank" rel="noreferrer" style={{ fontSize: 14 }}>Open in Spotify</a>
              </>}
          </section>
          <section className="ons-card" aria-labelledby="top-h">
            <div className="ons-ch"><h2 id="top-h">Most listened</h2><span className="aside">Minutes in {c.y}</span></div>
            <table className="ons-table">
              <thead><tr><th>Artist</th><th className="r">Minutes</th></tr></thead>
              <tbody>{artists.map((a) => <tr key={a.artist}><td>{a.artist}</td><td className="r ons-n">{Math.round(a.minutes)}</td></tr>)}</tbody>
            </table>
            {tracks.length > 0 && <table className="ons-table" style={{ marginTop: 16 }}>
              <thead><tr><th>Track</th><th className="r">Minutes</th></tr></thead>
              <tbody>{tracks.map((t) => <tr key={t.track + t.artist}><td>{t.track.replace(/ - (Remaster(ed)?( \d{4})?|.*Version)$/i, "")}<span className="sub">{t.artist}</span></td><td className="r ons-n">{Math.round(t.minutes)}</td></tr>)}</tbody>
            </table>}
          </section>
        </div>

        <section className="ons-card s8" aria-labelledby="month-h">
          <div className="ons-ch"><h2 id="month-h">Listening by month</h2><span className="aside">Minutes · dashed line: {Math.round(perMonthGoal).toLocaleString("en-US")} a month reaches the goal</span></div>
          <svg viewBox={`0 0 ${CW} ${CH}`} width="100%" role="img" style={{ display: "block", overflow: "visible" }}
               aria-label={`Minutes listened per month in ${c.y}: ${months.months.map((m) => `${MONTHS[m.month - 1]} ${Math.round(m.minutes)}`).join(", ")}.`}>
            {Array.from({ length: Math.floor(mMax / step) + 1 }, (_, i) => i * step).map((v) => (
              <g key={v}><line x1={L} x2={CW} y1={yOf(v)} y2={yOf(v)} stroke="var(--rule)" /><text x={L - 8} y={yOf(v) + 4} textAnchor="end" fontSize="12" fill="var(--muted)" fontFamily="IBM Plex Mono, monospace">{v.toLocaleString("en-US")}</text></g>
            ))}
            {MONTHS.map((m, i) => {
              const v = byM.get(i + 1), x = L + i * bw + 4, w = bw - 8, future = i + 1 > nowMonth, missing = !future && i + 1 > thruMonth;
              return (
                <g key={m}>
                  {v != null && <rect x={x} y={yOf(v)} width={w} height={yOf(0) - yOf(v)} rx="2" fill="var(--icon)"><title>{`${m}: ${Math.round(v).toLocaleString("en-US")} minutes`}</title></rect>}
                  {missing && <rect x={x + 0.5} y={yOf(perMonthGoal * 0.25)} width={w - 1} height={yOf(0) - yOf(perMonthGoal * 0.25) - 0.5} rx="2" fill="none" stroke="var(--muted)" strokeDasharray="3 3"><title>{`${m}: not in the export yet`}</title></rect>}
                  <text x={x + w / 2} y={CH - 4} textAnchor="middle" fontSize="12" fill={future ? "var(--control)" : "var(--muted)"}>{m}</text>
                </g>
              );
            })}
            {goal > 0 && <line x1={L} x2={CW} y1={yOf(perMonthGoal)} y2={yOf(perMonthGoal)} stroke="var(--muted)" strokeDasharray="4 4" />}
          </svg>
          <p className="ons-note">The best month was {(() => { const b = [...months.months].sort((a, z) => z.minutes - a.minutes)[0]; return b ? `${MONTHS[b.month - 1]}, ${Math.round(b.minutes).toLocaleString("en-US")} minutes` : "–"; })()}. {thruMonth < nowMonth ? `Dashed months aren't in the Spotify export yet.` : ""}</p>
        </section>

        <section className="ons-card s4" aria-labelledby="aotd-h">
          <div className="ons-ch"><h2 id="aotd-h">Artist of the day</h2><button type="button" className="ons-tap ons-btn" onClick={() => setReroll((r) => r + 1)}>Try another</button></div>
          {aotd === null ? <p className="ons-note m-0">Finding today&apos;s artist…</p>
            : !aotd.available ? <p className="ons-note m-0">No artist today: {(aotd.reason ?? "nothing found").replace(/^./, (m) => m.toLowerCase())}. Try another to look again.</p>
            : <Artist a={aotd} today={today} />}
        </section>
      </div>
    </div>
  );
}

function Artist({ a, today }: { a: ArtistOfTheDay; today: string }) {
  const [more, setMore] = useState(false);
  const paras = (a.bio ?? "").split(/\n\s*\n/).filter((p) => p.trim());
  const meta = [a.description, a.country, a.formed ? `since ${a.formed}` : null, a.label].filter(Boolean).join(" · ");
  const you = a.you ?? {};
  return (
    <div>
      <div className="flex gap-3 items-start">
        {a.image && <img src={a.image} alt="" width={72} height={72} style={{ width: 72, height: 72, objectFit: "cover", borderRadius: 6, flex: "none" }} />}
        <div className="min-w-0">
          <div style={{ font: "600 18px/24px 'IBM Plex Sans', system-ui, sans-serif" }}>{a.artist}</div>
          {meta && <div className="text-muted" style={{ fontSize: 13 }}>{meta}</div>}
        </div>
      </div>
      <p className="m-0" style={{ marginTop: 12, fontSize: 14, lineHeight: "21px", color: "var(--ink-2)" }}>
        {you.minutes ? <>You&apos;ve played them for <b>{you.minutes.toLocaleString("en-US")} minutes</b> ({plural(you.plays ?? 0, "play")}){you.top_track ? `, most of all ${you.top_track}` : ""}.</> : "Not in your listening history yet."}
        {a.shows?.length ? <> In Denver {short(a.shows[0].date) === short(today) ? "tonight" : `on ${short(a.shows[0].date)}`} at {a.shows[0].venue}.</> : null}
      </p>
      {paras.length > 0 && <div style={{ marginTop: 10, fontSize: 14, lineHeight: "21px", color: "var(--ink-2)" }}>{(more ? paras : paras.slice(0, 1)).map((p, i) => <p key={i} className="m-0" style={{ marginTop: i ? 8 : 0 }}>{decode(p)}</p>)}</div>}
      <p className="ons-note" style={{ display: "flex", flexWrap: "wrap", gap: "4px 14px" }}>
        {paras.length > 1 && <button type="button" className="ons-link ons-linkbtn" onClick={() => setMore((m) => !m)}>{more ? "Less" : "Read more"}</button>}
        {Object.entries(a.links ?? {}).map(([src, url]) => <a key={src} className="ons-link" href={url} target="_blank" rel="noreferrer">{src}</a>)}
        {a.similar?.length ? <span>Similar: {a.similar.slice(0, 4).join(", ")}</span> : null}
      </p>
    </div>
  );
}
