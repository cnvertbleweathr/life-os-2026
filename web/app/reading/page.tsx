"use client";

// Reading (Logbook Color). Teal is reading. Real data only:
//   books     /reading/read?year= (hardcover.books_read: title, authors, classification, finish date, tags)
//   goals     /goals/progress (fiction_books_goal, nonfiction_books_goal; the year's goal is their sum)
// Fixes from docs/design/critique.md §10: dates print as "Sep 5" (finished_date arrives as an ISO timestamp,
// which the old page re-suffixed with T00:00:00, so every month parsed as NaN and the pace line went flat);
// the mix counts unclassified books so it adds up; the needed pace is stated; past years are one tap away.

import { useEffect, useMemo, useState } from "react";
import { readingApi, goalsApi, type BookRead, type Goal } from "@/lib/api";
import { PageHead, Loading, ErrorState } from "@/components/ui/primitives";
import { PixelScene } from "@/components/ui/PixelScene";

const TZ = "America/Denver";
const DAY = 86_400_000;
const isoDenver = (d: Date) => new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
const fromIso = (iso: string) => { const [y, m, d] = iso.slice(0, 10).split("-").map(Number); return new Date(Date.UTC(y, m - 1, d, 12)); };
const daysBetween = (a: string, b: string) => Math.round((fromIso(b).getTime() - fromIso(a).getTime()) / DAY);
const fmt = (iso: string, o: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat("en-US", { timeZone: "UTC", ...o }).format(fromIso(iso));
const short = (iso: string) => fmt(iso, { month: "short", day: "numeric" });
const plural = (n: number, one: string, many = one + "s") => `${n} ${n === 1 ? one : many}`;
const WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"];
const word = (n: number) => WORDS[n] ?? String(n);
const join = (xs: string[]) => (xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);

/** Hardcover text can carry HTML entities ("Anita&#039;s"); show the characters. */
function decode(s: string) {
  return s.replace(/&(#\d+|#x[\da-f]+|amp|lt|gt|quot|apos|nbsp);/gi, (_, e: string) => {
    const k = e.toLowerCase();
    if (k[0] === "#") return String.fromCodePoint(k[1] === "x" ? parseInt(k.slice(2), 16) : parseInt(k.slice(1), 10));
    return ({ amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " } as Record<string, string>)[k];
  });
}
/** Genre tags from Hardcover's cached_tags (a Python-repr dict), most-tagged first. */
function genres(tags: string): string[] {
  const i = tags.indexOf("'Genre': [");
  if (i < 0) return [];
  const block = tags.slice(i, tags.indexOf("]", i));
  return Array.from(block.matchAll(/'tag': (?:'([^']*)'|"([^"]*)")/g)).map((m) => m[1] ?? m[2]).filter((g) => g && g !== "General" && !/^[a-z]/.test(g));
}
const KIND: Record<string, [string, string]> = { fiction: ["f", "Fiction"], nonfiction: ["n", "Nonfiction"] };
const kindOf = (b: BookRead) => KIND[b.classification] ?? ["u", "Unclassified"];

type Book = BookRead & { iso: string; t: string; a: string; g: string[]; k: string; kl: string };

export default function ReadingPage() {
  const [today, setToday] = useState<string | null>(null);
  const [byYear, setByYear] = useState<Record<number, Book[]> | null>(null);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [year, setYear] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [narrow, setNarrow] = useState(false);

  useEffect(() => {
    const mq = matchMedia("(max-width: 767px)"), on = () => setNarrow(mq.matches);
    on(); mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);

  useEffect(() => {
    const t = isoDenver(new Date()), y = +t.slice(0, 4);
    setToday(t); setYear(y);
    const years = [y, y - 1, y - 2, y - 3];
    Promise.all(years.map((yy) => readingApi.read(yy, 500).catch(() => [] as BookRead[])))
      .then((rs) => setByYear(Object.fromEntries(years.map((yy, i) => [yy, rs[i].map((b) => {
        const iso = String(b.finished_date).slice(0, 10), [k, kl] = kindOf(b);
        return { ...b, iso, t: decode(b.title), a: decode(b.authors || ""), g: genres(b.cached_tags || ""), k, kl };
      }).sort((a, b) => a.iso.localeCompare(b.iso))]))))
      .catch((e) => setError(e.message));
    goalsApi.progress().then(setGoals).catch(() => {});
  }, []);

  const view = useMemo(() => {
    if (!byYear || !year) return null;
    const books = byYear[year] ?? [];
    const count = (k: string) => books.filter((b) => b.k === k).length;
    const g = new Map<string, number>();
    books.forEach((b) => b.g.slice(0, 3).forEach((x) => g.set(x, (g.get(x) ?? 0) + 1)));
    return { books, f: count("f"), n: count("n"), u: count("u"), genres: Array.from(g.entries()).sort((a, b) => b[1] - a[1]).slice(0, 6) };
  }, [byYear, year]);

  if (error) return <div className="ons-page" style={{ padding: "34px 44px 48px" }}><ErrorState message={error} /></div>;
  if (!byYear || !today || !year || !view) return <Loading label="Loading reading…" />;

  // ── This year against the goal ────────────────────────────────────────────
  const y = +today.slice(0, 4);
  const daysInYear = (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0 ? 366 : 365;
  const dayOfYear = daysBetween(`${y}-01-01`, today) + 1, yearFrac = dayOfYear / daysInYear, daysLeft = daysInYear - dayOfYear;
  const now = byYear[y] ?? [];
  const goalOf = (k: string) => goals.find((g) => g.goal_key === k)?.target_numeric ?? null;
  const fGoal = goalOf("fiction_books_goal") ?? 5, nGoal = goalOf("nonfiction_books_goal") ?? 5, goal = fGoal + nGoal;
  const fNow = now.filter((b) => b.k === "f").length, nNow = now.filter((b) => b.k === "n").length;
  const unclassified = now.filter((b) => b.k === "u");
  const expected = goal * yearFrac, behind = Math.ceil(expected - now.length - 1e-9);
  const fLeft = Math.max(0, fGoal - fNow), nLeft = Math.max(0, nGoal - nNow), left = fLeft + nLeft;
  const last = now[now.length - 1];
  const sinceLast = last ? daysBetween(last.iso, today) : null;
  const every = left ? Math.max(1, Math.floor(daysLeft / left)) : 0;

  const lede = (
    <>
      <b>{now.length} of {goal} books</b>{behind > 0 ? <>, {plural(behind, "book")} behind pace: a {goal}-book year has {expected.toFixed(1)} finished by today.</> : <>, on pace.</>}{" "}
      {left > 0 && <>
        {fLeft > 0 && nLeft > 0 ? <><b>Fiction needs {word(fLeft)} more and nonfiction {word(nLeft)}</b></> : fLeft > 0 ? <><b>Fiction needs {word(fLeft)} more</b></> : <><b>Nonfiction needs {word(nLeft)} more</b></>}
        , one book every {every} days for the {daysLeft} days left.{" "}
      </>}
      {last && sinceLast != null && sinceLast > 21 && <>The last finish was {last.t} on {short(last.iso)}, {sinceLast} days ago. </>}
      {unclassified.length > 0 && <>{unclassified.length === 1 ? <>{unclassified[0].t} isn&apos;t</> : <>{join(unclassified.map((b) => b.t))} aren&apos;t</>} classified in Hardcover, so neither goal counts {unclassified.length === 1 ? "it" : "them"}.</>}
    </>
  );

  const years = Object.keys(byYear).map(Number).filter((yy) => byYear[yy].length || yy === y).sort((a, b) => b - a);
  const isNow = year === y;

  // ── Cumulative chart: a step for every finished book ─────────────────────
  const CW = narrow ? 340 : 640, CH = narrow ? 200 : 220, L = 30, R = 44, T = 10, B = 26;
  const yearDays = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0 ? 366 : 365;
  const xOf = (iso: string) => L + (daysBetween(`${year}-01-01`, iso) / yearDays) * (CW - L - R);
  const top = Math.max(isNow ? goal : 0, view.books.length, 1);
  const step = top > 20 ? 10 : top > 10 ? 5 : 2;
  const yMax = Math.ceil(top / step) * step;
  const yOf = (v: number) => T + (1 - v / yMax) * (CH - T - B);
  const end = isNow ? today : `${year}-12-31`;
  let path = `M${L} ${yOf(0)}`;
  view.books.forEach((b, i) => { path += ` H${xOf(b.iso).toFixed(1)} V${yOf(i + 1).toFixed(1)}`; });
  path += ` H${xOf(end).toFixed(1)}`;

  // A year whose books nearly all share one finish date was bulk-imported into Hardcover: the dates are when
  // they were marked read, not when they were read, so there's no pace to draw and no gaps to count.
  const sameDay = view.books.reduce((m, b) => m.set(b.iso, (m.get(b.iso) ?? 0) + 1), new Map<string, number>());
  const [bulkDay, bulkN] = Array.from(sameDay.entries()).sort((a, b) => b[1] - a[1])[0] ?? ["", 0];
  const bulk = view.books.length >= 5 && bulkN / view.books.length >= 0.8;
  const gaps = view.books.map((b, i) => (i && !bulk ? daysBetween(view.books[i - 1].iso, b.iso) : null));
  const desc = [...view.books].reverse();

  return (
    <div className="ons-page" style={{ padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" }}>
      <PageHead
        title="Reading"
        kicker={`${y} through ${fmt(today, { weekday: "short", month: "short", day: "numeric" })} · ${plural(now.length, "book")} finished · from Hardcover`}
        sub={lede}
        scene={<PixelScene scene="reading" data={{ shelf: now.map((b) => b.k).join(""), goal }}
          label={`a reader in an armchair with the cats; the top shelf holds ${now.length} of ${goal} books for ${y}`} />}
      />

      <div className="ons-tiles" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))" }}>
        <section className="ons-tile t t-read">
          <h2>Books in {y}</h2>
          <div className="big n">{now.length} of {goal}</div>
          <p>{behind > 0 ? `${plural(behind, "book")} behind · ${expected.toFixed(1)} expected by today` : "On pace for the year"}</p>
          <div className="ons-bar" style={{ marginTop: "auto" }}><b style={{ width: `${Math.min(100, (now.length / goal) * 100)}%` }} /><i style={{ left: `${yearFrac * 100}%` }} /></div>
        </section>
        {([["Fiction", fNow, fGoal, fLeft], ["Nonfiction", nNow, nGoal, nLeft]] as const).map(([label, cur, g, l]) => (
          <section key={label} className="ons-tile l-read">
            <h2>{label}</h2>
            <div className="big n">{cur} of {g}</div>
            <p>{!l ? "Done for the year" : l === 1 ? `1 to go in ${plural(daysLeft, "day")}` : `${l} to go · one every ${Math.floor(daysLeft / l)} days`}</p>
            <div className="ons-bar" style={{ marginTop: "auto" }}><b style={{ width: `${Math.min(100, (cur / g) * 100)}%` }} /><i style={{ left: `${yearFrac * 100}%` }} /></div>
          </section>
        ))}
        <section className="ons-tile">
          <h2>Last finished</h2>
          <div className="big">{last ? short(last.iso) : "–"}</div>
          <p>{last ? <>{last.t}{sinceLast != null ? `, ${plural(sinceLast, "day")} ago` : ""}</> : `Nothing finished in ${y} yet.`}</p>
          <p className="tnote">Currently reading isn&apos;t tracked yet: Hardcover&apos;s export only has finished books.</p>
        </section>
      </div>

      <div className="ons-tabs" role="tablist" aria-label="Year">
        {years.map((yy) => <button key={yy} type="button" role="tab" aria-selected={yy === year} onClick={() => setYear(yy)}>{yy}<span className="text-muted" style={{ fontWeight: 400 }}> · {byYear[yy].length}</span></button>)}
      </div>

      <div className="ons-grid">
        <section className="ons-card s8" aria-labelledby="pace-h">
          <div className="ons-ch"><h2 id="pace-h">{isNow ? "Pace against the goal" : `Books through ${year}`}</h2><span className="aside">{bulk ? plural(view.books.length, "book") : isNow ? `Each step is a finished book · dashed line: ${goal} by Dec 31` : `${plural(view.books.length, "book")} · each step is a finished book`}</span></div>
          {bulk ? (
            <p className="m-0" style={{ fontSize: 14, lineHeight: "22px", color: "var(--ink-2)", maxWidth: "62ch" }}>
              {bulkN === view.books.length ? `All ${view.books.length}` : `${bulkN} of ${view.books.length}`} books in {year} are dated {fmt(bulkDay, { month: "long", day: "numeric" })}, the day they were added to Hardcover in bulk, so there&apos;s no pace line for {year}. The count and the mix are still right.
            </p>
          ) : <>
          <svg viewBox={`0 0 ${CW} ${CH}`} width="100%" role="img" style={{ display: "block", overflow: "visible" }}
               aria-label={`${plural(view.books.length, "book")} finished in ${year}${isNow ? `, against ${expected.toFixed(1)} expected by today on a ${goal}-book pace` : ""}.`}>
            {Array.from({ length: yMax / step + 1 }, (_, i) => i * step).map((v) => (
              <g key={v}>
                <line x1={L} x2={CW - R} y1={yOf(v)} y2={yOf(v)} stroke="var(--rule)" />
                <text x={L - 8} y={yOf(v) + 4} textAnchor="end" fontSize="12" fill="var(--muted)" fontFamily="IBM Plex Mono, monospace">{v}</text>
              </g>
            ))}
            {Array.from({ length: 12 }, (_, m) => `${year}-${String(m + 1).padStart(2, "0")}-01`).filter((_, m) => !narrow || m % 3 === 0).map((iso) => (
              <text key={iso} x={xOf(iso) + 2} y={CH - 6} fontSize="12" fill="var(--muted)">{fmt(iso, { month: "short" })}</text>
            ))}
            {isNow && <>
              <line x1={xOf(`${y}-01-01`)} y1={yOf(0)} x2={CW - R} y2={yOf(goal)} stroke="var(--muted)" strokeDasharray="4 4" />
              <line x1={xOf(today)} x2={xOf(today)} y1={T} y2={CH - B} stroke="var(--hue)" />
              <text x={xOf(today) - 6} y={T + 10} textAnchor="end" fontSize="12" fill="var(--hue)">Today</text>
              <text x={CW - R + 6} y={yOf(goal) + 4} fontSize="12" fill="var(--muted)" fontFamily="IBM Plex Mono, monospace">{goal}</text>
            </>}
            <path d={path} fill="none" stroke="var(--read-mark)" strokeWidth="2.5" strokeLinejoin="round" />
            {view.books.map((b, i) => <circle key={i} cx={xOf(b.iso)} cy={yOf(i + 1)} r="3.5" fill="var(--read-mark)" stroke="var(--sheet)" strokeWidth="1.5"><title>{`${b.t}, ${short(b.iso)}`}</title></circle>)}
            <text x={xOf(end) + 6} y={yOf(view.books.length) + 4} fontSize="12" fontWeight="600" fill="var(--read-ink)" fontFamily="IBM Plex Mono, monospace">{view.books.length}</text>
          </svg>
          </>}
          {isNow && left > 0 && <p className="ons-note">To finish: {plural(left, "more book")} in {plural(daysLeft, "day")}, one every {every} days.</p>}
        </section>

        <section className="ons-card s4" aria-labelledby="mix-h">
          <div className="ons-ch"><h2 id="mix-h">Fiction and nonfiction</h2><span className="aside">{year}</span></div>
          {view.books.length ? <>
            <div className="ons-mix" role="img" aria-label={`${view.f} fiction, ${view.n} nonfiction, ${view.u} unclassified`}>
              {view.f > 0 && <i className="f" style={{ flexGrow: view.f }} />}
              {view.n > 0 && <i className="n" style={{ flexGrow: view.n }} />}
              {view.u > 0 && <i className="u" style={{ flexGrow: view.u }} />}
            </div>
            <table className="ons-table" style={{ marginTop: 12 }}>
              <tbody>
                {([["f", "Fiction", view.f], ["n", "Nonfiction", view.n], ["u", "Unclassified", view.u]] as const).map(([k, l, v]) => (
                  <tr key={k}><td><span className={`ons-kind ${k}`}>{l}</span></td><td className="r ons-n">{v}</td></tr>
                ))}
                <tr><td><b>Total</b></td><td className="r ons-n"><b>{view.books.length}</b></td></tr>
              </tbody>
            </table>
            {view.genres.length > 0 && <>
              <h3 style={{ font: "600 14px/20px 'IBM Plex Sans', system-ui, sans-serif", margin: "20px 0 4px" }}>Genres</h3>
              <p className="m-0" style={{ fontSize: 14, lineHeight: "22px", color: "var(--ink-2)" }}>
                {view.genres.map(([g, c], i) => <span key={g}>{i ? " · " : ""}{g} <span className="ons-n text-muted">{c}</span></span>)}
              </p>
              <p className="ons-note">Counted from each book&apos;s top three genre tags on Hardcover.</p>
            </>}
          </> : <p className="ons-note m-0">No books finished in {year}.</p>}
        </section>

        <section className="ons-card s12" aria-labelledby="list-h">
          <div className="ons-ch"><h2 id="list-h">Finished in {year}</h2><span className="aside">Newest first · gap is the days since the book before</span></div>
          {desc.length ? (
            <div style={{ overflowX: "auto" }}>
              <table className="ons-table">
                <thead><tr><th>Finished</th><th>Book</th><th>Kind</th><th className="hide-p">Genres</th><th className="r hide-p">Gap</th></tr></thead>
                <tbody>
                  {desc.map((b, i) => {
                    const gap = gaps[view.books.length - 1 - i];
                    return (
                      <tr key={`${b.t}-${b.iso}`}>
                        <td style={{ whiteSpace: "nowrap" }}>{short(b.iso)}</td>
                        <td><span style={{ fontWeight: 500 }}>{b.t}</span><span className="sub">{b.a || "Unknown author"}</span></td>
                        <td><span className={`ons-kind ${b.k}`}>{b.kl}</span></td>
                        <td className="hide-p text-muted" style={{ fontSize: 13 }}>{b.g.slice(0, 2).join(", ") || "–"}</td>
                        <td className="r hide-p ons-n">{gap != null ? `${gap} d` : "–"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : <p className="ons-note m-0">No books finished in {year}.</p>}
        </section>
      </div>
    </div>
  );
}
