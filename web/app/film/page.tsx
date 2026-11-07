"use client";

// Film (Logbook Color). Magenta is film. Real data only:
//   watches   /film/watches   mart_film_watches: one row per film per watch date, Letterboxd and/or Plex
//   library   /film/library   rendered pixel GIFs this device may see, plus the catalog's counts
//   scene     /film/scene     the latest watch, for the title scene
//   queue     /film/queue     scene suggestions waiting for approval (owner only: read only when this
//                             device already has the write key, so a visitor never sees a key prompt)
// plex_clip GIFs come from the owner's own copies; the API hides them from anyone without the key.

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  filmApi, hasWriteKey,
  type CatalogRow, type FilmLibrary, type FilmScene, type FilmWatch, type RenderMode,
} from "@/lib/api";
import { PageHead, Loading, ErrorState } from "@/components/ui/primitives";
import { PixelScene } from "@/components/ui/PixelScene";
import { loadStrip } from "@/lib/pixelScenes";

const TZ = "America/Denver";
const isoDenver = (d: Date) => new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
const fromIso = (iso: string) => { const [y, m, d] = iso.slice(0, 10).split("-").map(Number); return new Date(Date.UTC(y, m - 1, d, 12)); };
const fmt = (iso: string, o: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat("en-US", { timeZone: "UTC", ...o }).format(fromIso(iso));
const short = (iso: string) => fmt(iso, { month: "short", day: "numeric" });
const plural = (n: number, one: string, many = one + "s") => `${n} ${n === 1 ? one : many}`;
const MONTHS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];
const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const SOURCE: Record<FilmWatch["source"], [string, string]> = {
  both: ["both", "Both"], letterboxd: ["lb", "Letterboxd"], plex: ["px", "Plex only"],
};
const MODE: Record<RenderMode, string> = { sprite: "Public-domain scene", plex_clip: "From your copy", motif: "Motif" };
const SHOWN = 15;
const rating = (r: number | null) => (r == null ? "–" : r.toFixed(1));
const clock = (s: number | null) => (s == null ? "" : `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`);

/** Object URLs for a film's light and dark strips, preloaded so the scene engine never draws a half-loaded image. */
function useStrips(key: string | null, opts: { motif?: boolean; version?: string | null } = {}) {
  const [urls, setUrls] = useState<{ light: string; dark: string } | null>(null);
  const { motif, version } = opts;
  useEffect(() => {
    if (!key) return;
    let live = true;
    Promise.all([filmApi.strip(key, "light", { motif, version }), filmApi.strip(key, "dark", { motif, version })])
      .then(async ([light, dark]) => { await Promise.all([loadStrip(light), loadStrip(dark)]); if (live) setUrls({ light, dark }); })
      .catch(() => {});
    return () => { live = false; };
  }, [key, motif, version]);
  return urls;
}

function TitleScene({ scene }: { scene: FilmScene | null }) {
  const urls = useStrips(scene?.film_key ?? null, { motif: scene?.strip === "motif", version: scene?.version });
  const what = scene ? `${scene.title}${scene.scene_label ? `: ${scene.scene_label}` : ""}` : "no film yet";
  return (
    <PixelScene scene="film" data={{ "strip-light": urls?.light, "strip-dark": urls?.dark }}
      label={`a small cinema with velvet curtains; the screen loops the latest film, ${what}`} />
  );
}

function ReelTile({ film }: { film: FilmLibrary["films"][number] }) {
  const urls = useStrips(film.film_key, { version: film.rendered_at });
  return (
    <li className="ons-reel-item">
      <PixelScene scene="loop" data={{ "strip-light": urls?.light, "strip-dark": urls?.dark }}
        label={`${film.title} loop${film.scene_label ? `: ${film.scene_label}` : ""}`} />
      <div className="cap">
        <b>{film.title}</b> <span className="ons-n text-muted">{film.year ?? ""}</span>
        {film.scene_label && <span className="sub">{film.scene_label}</span>}
        <span className="sub">{MODE[film.render_mode]}</span>
      </div>
    </li>
  );
}

type Draft = { scene_label: string; scene_note: string; render_mode: RenderMode; clip_start: string; clip_end: string };
const draftOf = (r: CatalogRow): Draft => ({
  scene_label: r.scene_label ?? "", scene_note: r.scene_note ?? "", render_mode: r.render_mode,
  clip_start: r.clip_start == null ? "" : String(r.clip_start), clip_end: r.clip_end == null ? "" : String(r.clip_end),
});

function QueueRow({ row, onDone }: { row: CatalogRow; onDone: (key: string) => void }) {
  const [d, setD] = useState<Draft>(() => draftOf(row));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof Draft) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setD({ ...d, [k]: e.target.value });
  const num = (v: string) => (v.trim() === "" ? null : Number(v));
  const id = row.film_key.replace(/[^a-z0-9]/gi, "-");

  const act = (kind: "approve" | "reject") => {
    setBusy(true); setError(null);
    const edits = {
      scene_label: d.scene_label, scene_note: d.scene_note, render_mode: d.render_mode,
      ...(d.render_mode === "plex_clip" ? { clip_start: num(d.clip_start), clip_end: num(d.clip_end) } : {}),
    };
    (kind === "approve" ? filmApi.approve(row.film_key, edits) : filmApi.reject(row.film_key))
      .then(() => onDone(row.film_key))
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
  };

  return (
    <li className="ons-queue-row" aria-labelledby={`${id}-t`}>
      <div className="head">
        <h3 id={`${id}-t`}>{row.title} <span className="ons-n text-muted">{row.year ?? ""}</span></h3>
        {row.suggestion_confidence && <span className="ons-n text-muted">Suggested · {row.suggestion_confidence} confidence</span>}
      </div>
      <div className="fields">
        <label className="wide"><span>Scene</span><input className="ons-input" value={d.scene_label} onChange={set("scene_label")} maxLength={120} placeholder="Name the moment" /></label>
        <label className="wide"><span>What moves in the loop</span><input className="ons-input" value={d.scene_note} onChange={set("scene_note")} maxLength={500} /></label>
        <label><span>Render</span>
          <select className="ons-input" value={d.render_mode} onChange={set("render_mode")}>
            <option value="plex_clip" disabled={!row.plex_file}>From your copy{row.plex_file ? "" : " (no Plex file)"}</option>
            <option value="motif">Motif</option>
            <option value="sprite">Public-domain scene</option>
          </select>
        </label>
        {d.render_mode === "plex_clip" && <>
          <label><span>Clip start (s){d.clip_start ? ` · ${clock(Number(d.clip_start))}` : ""}</span><input className="ons-input ons-n" inputMode="decimal" value={d.clip_start} onChange={set("clip_start")} placeholder={row.suggested_timestamp_s != null ? String(row.suggested_timestamp_s) : "seconds"} /></label>
          <label><span>Clip end (s)</span><input className="ons-input ons-n" inputMode="decimal" value={d.clip_end} onChange={set("clip_end")} placeholder="start + 5" /></label>
        </>}
      </div>
      <div className="acts">
        <button type="button" className="ons-btn pri" disabled={busy} onClick={() => act("approve")}>Approve</button>
        <button type="button" className="ons-btn" disabled={busy} onClick={() => act("reject")}>Reject</button>
        {error && <p role="alert" className="err">{error}</p>}
      </div>
    </li>
  );
}

export default function FilmPage() {
  const [today, setToday] = useState<string | null>(null);
  const [watches, setWatches] = useState<FilmWatch[] | null>(null);
  const [library, setLibrary] = useState<FilmLibrary | null>(null);
  const [scene, setScene] = useState<FilmScene | null>(null);
  const [queue, setQueue] = useState<CatalogRow[] | null>(null);
  const [year, setYear] = useState<number | null>(null);
  const [all, setAll] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadLibrary = useCallback(() => filmApi.library().then(setLibrary).catch(() => setLibrary({ films: [], counts: { suggested: 0, approved: 0, rejected: 0, rendered: 0 } })), []);

  useEffect(() => {
    const t = isoDenver(new Date());
    setToday(t); setYear(+t.slice(0, 4));
    filmApi.watches().then(setWatches).catch((e) => setError(e.message));
    filmApi.scene().then(setScene).catch(() => {});
    loadLibrary();
    if (hasWriteKey()) filmApi.queue().then(setQueue).catch(() => setQueue(null));
  }, [loadLibrary]);

  const y = today ? +today.slice(0, 4) : 0;
  const view = useMemo(() => {
    if (!watches || !year) return null;
    const rows = watches.filter((w) => w.watch_year === year);
    const months = Array.from({ length: 12 }, (_, m) => rows.filter((w) => +w.watch_date.slice(5, 7) === m + 1).length);
    const dec = new Map<number, number>();
    rows.forEach((w) => { if (w.film_year) dec.set(Math.floor(w.film_year / 10) * 10, (dec.get(Math.floor(w.film_year / 10) * 10) ?? 0) + 1); });
    return {
      rows,
      months,
      decades: Array.from(dec.entries()).sort((a, b) => a[0] - b[0]),
    };
  }, [watches, year]);

  if (error) return <div className="ons-page" style={{ padding: "34px 44px 48px" }}><ErrorState message={error} /></div>;
  if (!watches || !today || !year || !view) return <Loading label="Loading film…" />;

  const years = Array.from(new Set([y, ...watches.map((w) => w.watch_year)])).sort((a, b) => b - a);
  const counts = library?.counts;
  const now = watches.filter((w) => w.watch_year === y);
  const nowFilms = new Set(now.map((w) => w.film_key)).size;
  const plexOnlyNow = now.filter((w) => w.source === "plex").length;
  const last = watches[0];
  const waiting = queue?.length ?? 0;
  const isNow = year === y;
  const maxMonth = Math.max(1, ...view.months);
  const maxDec = Math.max(1, ...view.decades.map(([, c]) => c));

  const lede = now.length ? (
    <>
      <b>{plural(now.length, "watch", "watches")} in {y}</b>
      {nowFilms !== now.length ? <> across {plural(nowFilms, "film")}</> : null}
      {last ? <>; the latest was {last.title} on {short(last.watch_date)}.</> : "."}{" "}
      {plexOnlyNow > 0 && <><b>{plural(plexOnlyNow, "Plex watch", "Plex watches")} {plexOnlyNow === 1 ? "has" : "have"} no Letterboxd entry</b>, so {plexOnlyNow === 1 ? "it has" : "they have"} no rating yet: log {plexOnlyNow === 1 ? "it" : "them"} while you remember. </>}
      {waiting > 0 && <>{plural(waiting, "scene suggestion")} {waiting === 1 ? "waits" : "wait"} for you below; approved scenes render at the 9:00 sync.</>}
    </>
  ) : (
    <>Nothing watched yet in {y}. Letterboxd diary entries and Plex plays land here after the 9:00 sync.</>
  );

  return (
    <div className="ons-page" style={{ padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" }}>
      <PageHead
        title="Film"
        kicker={`${y} through ${fmt(today, { weekday: "short", month: "short", day: "numeric" })} · ${plural(now.length, "watch", "watches")} · from Letterboxd and Plex`}
        sub={lede}
        scene={<TitleScene scene={scene} />}
      />

      <div className="ons-tiles" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))" }}>
        <section className="ons-tile t t-film">
          <h2>Watched in {y}</h2>
          <div className="big n">{now.length}</div>
          <p>{plural(nowFilms, "film")}{now.filter((w) => w.is_rewatch).length ? ` · ${plural(now.filter((w) => w.is_rewatch).length, "rewatch", "rewatches")}` : ""}</p>
        </section>
        <section className="ons-tile">
          <h2>Average rating</h2>
          <div className="big n">{(() => { const r = now.filter((w) => w.rating != null); return r.length ? (r.reduce((s, w) => s + (w.rating ?? 0), 0) / r.length).toFixed(2) : "–"; })()}<span className="text-muted" style={{ fontSize: 15 }}> / 5</span></div>
          <p>From {plural(now.filter((w) => w.rating != null).length, "rated Letterboxd entry", "rated Letterboxd entries")}</p>
          {plexOnlyNow > 0 && <p className="tnote">{plural(plexOnlyNow, "Plex-only watch", "Plex-only watches")} unrated</p>}
        </section>
        <section className="ons-tile">
          <h2>Last watched</h2>
          <div className="big">{last ? short(last.watch_date) : "–"}</div>
          <p>{last ? <>{last.title}{last.film_year ? ` (${last.film_year})` : ""}</> : "Nothing logged yet."}</p>
          {last && <p className="tnote">{last.rating != null ? `Rated ${rating(last.rating)}` : last.source === "plex" ? "Not on Letterboxd yet" : "Not rated"}</p>}
        </section>
        <section className="ons-tile">
          <h2>Screening Room</h2>
          <div className="big n">{counts ? counts.rendered : "–"}</div>
          <p>{counts ? <>{plural(counts.rendered, "loop")} rendered{counts.approved ? ` · ${counts.approved} approved, rendering at 9:00` : ""}</> : "Loading the library…"}</p>
          {counts && counts.suggested > 0 && <p className="tnote">{plural(counts.suggested, "suggestion")} waiting for review</p>}
        </section>
      </div>

      {queue && queue.length > 0 && (
        <section className="ons-card ons-queue" aria-labelledby="queue-h" style={{ marginBottom: 24 }}>
          <div className="ons-ch"><h2 id="queue-h">Scenes to review</h2><span className="aside">{plural(queue.length, "suggestion")} · nothing renders until you approve it</span></div>
          <ul>
            {queue.map((r) => <QueueRow key={r.film_key} row={r} onDone={(k) => { setQueue((q) => (q ?? []).filter((x) => x.film_key !== k)); loadLibrary(); }} />)}
          </ul>
        </section>
      )}

      <div className="ons-tabs" role="tablist" aria-label="Year">
        {years.map((yy) => <button key={yy} type="button" role="tab" aria-selected={yy === year} onClick={() => { setYear(yy); setAll(false); }}>{yy}<span className="text-muted" style={{ fontWeight: 400 }}> · {watches.filter((w) => w.watch_year === yy).length}</span></button>)}
      </div>

      <div className="ons-grid">
        <section className="ons-card s8" aria-labelledby="watches-h">
          <div className="ons-ch"><h2 id="watches-h">{isNow ? "Recent watches" : `Watched in ${year}`}</h2><span className="aside">Newest first · rating from Letterboxd</span></div>
          {view.rows.length ? (
            <div style={{ overflowX: "auto" }}>
              <table className="ons-table">
                <thead><tr><th>Date</th><th>Film</th><th className="r">Rating</th><th>Logged on</th></tr></thead>
                <tbody>
                  {(all ? view.rows : view.rows.slice(0, SHOWN)).map((w) => {
                    const [cls, label] = SOURCE[w.source];
                    const notes = [w.is_rewatch && "Rewatch", w.liked && "Liked", w.plex_plays > 1 && `${w.plex_plays} Plex plays`].filter(Boolean).join(" · ");
                    return (
                      <tr key={w.watch_id}>
                        <td style={{ whiteSpace: "nowrap" }}>{short(w.watch_date)}</td>
                        <td>
                          {w.letterboxd_url ? <a className="ons-film-link" href={w.letterboxd_url} target="_blank" rel="noreferrer">{w.title}</a> : <span style={{ fontWeight: 500 }}>{w.title}</span>}
                          <span className="sub">{[w.film_year, notes].filter(Boolean).join(" · ")}</span>
                        </td>
                        <td className="r ons-n">{rating(w.rating)}</td>
                        <td><span className={`ons-src ${cls}`}>{label}</span></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {view.rows.length > SHOWN && (
                <button type="button" className="ons-btn" style={{ marginTop: 12 }} aria-expanded={all} onClick={() => setAll(!all)}>
                  {all ? `Show the latest ${SHOWN}` : `Show all ${plural(view.rows.length, "watch", "watches")}`}
                </button>
              )}
            </div>
          ) : <p className="ons-note m-0">Nothing watched in {year}.</p>}
        </section>

        <div className="s4 ons-col no-stretch" style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          <section className="ons-card l-film" aria-labelledby="month-h">
            <div className="ons-ch"><h2 id="month-h">By month</h2><span className="aside">{year}</span></div>
            <ol className="ons-months" aria-label={`Watches by month in ${year}`}>
              {view.months.map((c, m) => (
                <li key={m} title={`${MONTH_NAMES[m]}: ${plural(c, "watch", "watches")}`}>
                  <span className="bar"><b style={{ height: `${(c / maxMonth) * 100}%` }} /></span>
                  <span className="n ons-n">{c || ""}</span>
                  <span className="lab" aria-hidden="true">{MONTHS[m]}</span>
                  <span className="sr-only">{MONTH_NAMES[m]}: {c}</span>
                </li>
              ))}
            </ol>
          </section>
          <section className="ons-card l-film" aria-labelledby="decade-h">
            <div className="ons-ch"><h2 id="decade-h">By decade</h2><span className="aside">Release year of {year}&apos;s watches</span></div>
            {view.decades.length ? (
              <table className="ons-table">
                <tbody>
                  {view.decades.map(([d, c]) => (
                    <tr key={d}>
                      <td className="ons-n" style={{ width: 56 }}>{d}s</td>
                      <td><div className="ons-bar"><b style={{ width: `${(c / maxDec) * 100}%` }} /></div></td>
                      <td className="r ons-n" style={{ width: 32 }}>{c}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <p className="ons-note m-0">No watches in {year}.</p>}
          </section>
        </div>

        <section className="ons-card s12" aria-labelledby="reel-h">
          <div className="ons-ch"><h2 id="reel-h">Screening Room</h2><span className="aside">Every rendered loop · 5 seconds, 64×32 · click any loop to pause them all</span></div>
          {library === null ? <p className="ons-note m-0">Loading the library…</p>
            : library.films.length ? (
              <ul className="ons-reel">{library.films.map((f) => <ReelTile key={f.film_key} film={f} />)}</ul>
            ) : (
              <p className="ons-note m-0">
                No loops rendered yet.{" "}
                {queue ? "Approve a scene above and the 9:00 sync renders it." : "Each film gets one after its scene is approved."}
              </p>
            )}
        </section>
      </div>
    </div>
  );
}
