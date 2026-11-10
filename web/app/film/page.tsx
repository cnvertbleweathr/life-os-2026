"use client";

// Film (Logbook Color). Magenta is film. Real data only:
//   watches   /film/watches   mart_film_watches: one row per film per watch date, Letterboxd and/or Plex
//   library   /film/library   rendered pixel GIFs this device may see, plus the catalog's counts
//   scene     /film/scene     the latest watch, for the title scene
//   queue     /film/queue     scene suggestions waiting for approval (owner only: read only when this
//                             device already has the write key, so a visitor never sees a key prompt)
//   clip      /film/clip      the owner picks any watched film's GIF from a YouTube link and start time;
//                             the API renders it at once and the row polls until it's done
// plex_clip and youtube GIFs are personal-use derivatives; the API hides them from anyone without the key.

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import {
  filmApi, hasWriteKey,
  type CatalogRow, type ClipStatus, type FilmLibrary, type FilmScene, type FilmWatch, type RenderMode,
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
const MODE: Record<RenderMode, string> = { sprite: "Public-domain scene", plex_clip: "From your copy", motif: "Motif", youtube: "From YouTube" };
const GIF_LABEL: Record<RenderMode, string> = { youtube: "Clip", plex_clip: "Clip", motif: "Title card", sprite: "Scene" };
const RENDERING = new Set<ClipStatus["state"]>(["queued", "rendering"]);
const POLL_MS = 2000;
const SHOWN = 15;
const rating = (r: number | null) => (r == null ? "–" : r.toFixed(1));
const clock = (s: number | null) => (s == null ? "" : `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`);
const clockLong = (s: number) => (s >= 3600 ? `${Math.floor(s / 3600)}:${clock(s % 3600).padStart(5, "0")}` : clock(s));

/** Seconds from "83", "1:23", "1:02:03", "1m23s"; null when blank, NaN when unreadable. Mirrors film/youtube.py. */
function parseTime(v: string): number | null {
  const s = v.trim().toLowerCase();
  if (!s) return null;
  if (/^\d+(\.\d+)?$/.test(s)) return Number(s);
  if (/^\d+(:\d{1,2}){1,2}(\.\d+)?$/.test(s)) {
    const parts = s.split(":").map(Number);
    if (parts.slice(1).some((p) => p >= 60)) return NaN;
    return parts.reduce((t, p) => t * 60 + p, 0);
  }
  const m = s.match(/^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?$/);
  if (m && (m[1] || m[2] || m[3])) return Number(m[1] ?? 0) * 3600 + Number(m[2] ?? 0) * 60 + Number(m[3] ?? 0);
  return NaN;
}

/** The start time a YouTube link carries (?t=83, ?t=1m23s, ?start=83), if any. */
function linkStart(url: string): number | null {
  try {
    const u = new URL(url.trim());
    const t = u.searchParams.get("t") ?? u.searchParams.get("start");
    const n = t ? parseTime(t) : null;
    return n != null && Number.isFinite(n) ? n : null;
  } catch { return null; }
}

const looksLikeYouTube = (url: string) => {
  try { return /(^|\.)(youtube\.com|youtu\.be)$/.test(new URL(url.trim()).hostname); } catch { return false; }
};

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

/** The GIF column: what the film shows now, or where its new clip stands, and the button that opens the editor. */
function GifCell({ w, open, onToggle }: { w: FilmWatch; open: boolean; onToggle: () => void }) {
  const c = w.clip!;
  const [cls, label] = RENDERING.has(c.state) ? ["busy", "Rendering…"]
    : c.state === "failed" ? ["bad", "Failed"]
    : c.state === "waiting" && !w.gif ? ["wait", "At 9:00"]
    : w.gif_mode ? [w.gif_mode === "youtube" || w.gif_mode === "plex_clip" ? "clip" : "card", GIF_LABEL[w.gif_mode]]
    : ["none", "None"];
  const hasClip = w.gif_mode === "youtube" || w.gif_mode === "plex_clip";
  return (
    <td className="ons-gif-cell">
      <span className={`ons-gif ${cls}`}>{label}</span>
      <button type="button" id={`gifbtn-${w.watch_id}`} className="ons-linkbtn" aria-expanded={open} onClick={onToggle}
        aria-label={`${open ? "Close" : hasClip ? "Replace" : "Set"} the clip for ${w.title}`}>
        {open ? "Close" : hasClip ? "Replace" : "Set clip"}
      </button>
    </td>
  );
}

/** The loop a film shows now (owner's own strip, so youtube and plex clips included). */
function ClipPreview({ w }: { w: FilmWatch }) {
  const urls = useStrips(w.gif ? w.film_key : null, { version: w.gif_version });
  if (!w.gif) return <div className="ons-clip-preview empty" aria-hidden="true">No GIF yet</div>;
  return (
    <div className="ons-clip-preview">
      <PixelScene scene="loop" data={{ "strip-light": urls?.light, "strip-dark": urls?.dark }} label={`${w.title} loop`} />
    </div>
  );
}

/** Under a watch row: paste a YouTube link and a start time; the API renders the 5-second GIF straight away. */
function ClipEditor({ w, cols, onSaved, onClose }: {
  w: FilmWatch; cols: number; onSaved: (key: string, status: ClipStatus) => void; onClose: () => void;
}) {
  const c = w.clip!;
  const [url, setUrl] = useState(c.youtube_url ?? "");
  const [start, setStart] = useState(c.clip_start != null ? clockLong(c.clip_start) : "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const id = `clip-${w.watch_id.replace(/[^a-z0-9]/gi, "-")}`;
  const busy = RENDERING.has(c.state);

  const changeUrl = (v: string) => {
    setUrl(v);
    const t = linkStart(v);
    if (t != null) setStart(clockLong(t));
  };

  const save = (e?: React.FormEvent) => {
    e?.preventDefault();
    const seconds = parseTime(start) ?? 0;
    if (!looksLikeYouTube(url)) { setError("Paste a YouTube link (youtube.com or youtu.be)."); return; }
    if (!Number.isFinite(seconds)) { setError("Use a time like 1:23, 1:02:03 or 83."); return; }
    setSaving(true); setError(null);
    filmApi.setClip(w.film_key, url.trim(), seconds)
      .then((s) => onSaved(w.film_key, s))
      .catch((err: Error) => setError(err.message))
      .finally(() => setSaving(false));
  };

  const status = busy ? "Rendering the 5-second loop. This usually takes under 30 seconds."
    : c.state === "failed" ? null
    : c.state === "waiting" && c.render_mode === "youtube" ? "Saved. It renders at the 9:00 sync."
    : c.state === "done" && c.render_mode === "youtube" ? `Showing ${clockLong(c.clip_start ?? 0)}–${clockLong((c.clip_start ?? 0) + 5)} of the video.`
    : "Pick 5 seconds of any YouTube video: it becomes this film's 64×32 loop, seen only by you.";

  return (
    <tr className="ons-clip-edit">
      <td colSpan={cols}>
        <form className="ons-clip-form" onSubmit={save} onKeyDown={(e) => { if (e.key === "Escape") onClose(); }} aria-labelledby={`${id}-h`}>
          <ClipPreview w={w} />
          <div className="ons-clip-fields">
            <h3 id={`${id}-h`} className="sr-only">Clip for {w.title}</h3>
            <label className="url"><span>YouTube link</span>
              <input className="ons-input" type="url" inputMode="url" autoFocus value={url} onChange={(e) => changeUrl(e.target.value)}
                placeholder="https://youtu.be/…" spellCheck={false} autoComplete="off" maxLength={500} />
            </label>
            <label className="start"><span>Start</span>
              <input className="ons-input ons-n" value={start} onChange={(e) => setStart(e.target.value)} placeholder="1:23" autoComplete="off" />
            </label>
            <div className="acts">
              <button type="submit" className="ons-btn pri" disabled={saving || busy || !url.trim()}>
                {c.state === "failed" ? "Try again" : busy ? "Rendering…" : "Save"}
              </button>
              <button type="button" className="ons-btn" onClick={onClose}>{c.state === "done" ? "Done" : "Cancel"}</button>
            </div>
            {error || c.state === "failed"
              ? <p className="note err" role="alert">{error ?? `Couldn't render: ${c.error ?? "unknown error"}.`}</p>
              : <p className="note" role="status">{status}</p>}
          </div>
        </form>
      </td>
    </tr>
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
  const [editing, setEditing] = useState<string | null>(null);   // watch_id whose clip editor is open

  const loadLibrary = useCallback(() => filmApi.library().then(setLibrary).catch(() => setLibrary({ films: [], counts: { suggested: 0, approved: 0, rejected: 0, rendered: 0 } })), []);

  useEffect(() => {
    const t = isoDenver(new Date());
    setToday(t); setYear(+t.slice(0, 4));
    filmApi.watches().then(setWatches).catch((e) => setError(e.message));
    filmApi.scene().then(setScene).catch(() => {});
    loadLibrary();
    if (hasWriteKey()) filmApi.queue().then(setQueue).catch(() => setQueue(null));
  }, [loadLibrary]);

  // Closing the editor hands focus back to the row's Set clip / Replace button.
  const closeEditor = useCallback((watchId: string) => {
    setEditing(null);
    requestAnimationFrame(() => document.getElementById(`gifbtn-${watchId}`)?.focus());
  }, []);

  // A clip status for one film lands on every watch row of that film.
  const applyClip = useCallback((key: string, clip: ClipStatus) => {
    setWatches((ws) => ws && ws.map((w) => (w.film_key !== key ? w : {
      ...w, clip,
      ...(clip.state === "done" ? { gif: true, gif_mode: clip.render_mode, gif_version: clip.rendered_at } : {}),
    })));
    if (clip.state === "done") loadLibrary();
  }, [loadLibrary]);

  // Poll the films that are rendering until each is done or failed.
  const pending = useMemo(
    () => Array.from(new Set((watches ?? []).filter((w) => w.clip && RENDERING.has(w.clip.state)).map((w) => w.film_key))).sort().join("\n"),
    [watches],
  );
  useEffect(() => {
    if (!pending) return;
    const keys = pending.split("\n");
    const t = window.setTimeout(() => {
      keys.forEach((k) => filmApi.clipStatus(k).then((s) => applyClip(k, s)).catch(() => {}));
    }, POLL_MS);
    return () => window.clearTimeout(t);
  }, [pending, watches, applyClip]);

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
  const owner = watches.some((w) => w.clip);
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
                <thead><tr><th>Date</th><th>Film</th><th className="r">Rating</th><th className="hide-p">Logged on</th>{owner && <th>GIF</th>}</tr></thead>
                <tbody>
                  {(all ? view.rows : view.rows.slice(0, SHOWN)).map((w) => {
                    const [cls, label] = SOURCE[w.source];
                    const notes = [w.is_rewatch && "Rewatch", w.liked && "Liked", w.plex_plays > 1 && `${w.plex_plays} Plex plays`].filter(Boolean).join(" · ");
                    const open = editing === w.watch_id;
                    return (
                      <Fragment key={w.watch_id}>
                      <tr className={open ? "open" : undefined}>
                        <td style={{ whiteSpace: "nowrap" }}>{short(w.watch_date)}</td>
                        <td>
                          {w.letterboxd_url ? <a className="ons-film-link" href={w.letterboxd_url} target="_blank" rel="noreferrer">{w.title}</a> : <span style={{ fontWeight: 500 }}>{w.title}</span>}
                          <span className="sub">{[w.film_year, notes].filter(Boolean).join(" · ")}</span>
                        </td>
                        <td className="r ons-n">{rating(w.rating)}</td>
                        <td className="hide-p"><span className={`ons-src ${cls}`}>{label}</span></td>
                        {owner && w.clip && <GifCell w={w} open={open} onToggle={() => setEditing(open ? null : w.watch_id)} />}
                      </tr>
                      {open && w.clip && <ClipEditor w={w} cols={5} onSaved={applyClip} onClose={() => closeEditor(w.watch_id)} />}
                      </Fragment>
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
