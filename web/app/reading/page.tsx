"use client";

import { useEffect, useState } from "react";
import { readingApi, type ReadingSummary, type BookRead } from "@/lib/api";
import {
  Card, PageHead, Stat, StatBand, K, Empty, Loading, ErrorState,
} from "@/components/ui/primitives";
import { Donut } from "@/components/ui/viz";

// Deterministic spine color from title — keeps it visually varied without
// needing real cover art (Hardcover's API doesn't give us cover images here)
const SPINE_COLORS = ["#1d5536", "#3a5f7a", "#9a6a1e", "#a8473a", "#2f6b43", "#736e5f"];
function spineColor(title: string) {
  let h = 0;
  for (let i = 0; i < title.length; i++) h = (h * 31 + title.charCodeAt(i)) % SPINE_COLORS.length;
  return SPINE_COLORS[h];
}

export default function ReadingPage() {
  const [data, setData] = useState<ReadingSummary | null>(null);
  const [books, setBooks] = useState<BookRead[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([readingApi.summary(), readingApi.read(undefined, 50)])
      .then(([s, b]) => { setData(s); setBooks(b); })
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!data || !books) return <Loading />;

  const goal = 10;
  const booksRead = data.books_read ?? 0;
  const fiction = data.fiction_books ?? 0;
  const nonfiction = data.nonfiction_books ?? 0;

  // pace
  const now = new Date();
  const dayOfYear = Math.floor(
    (now.getTime() - new Date(now.getFullYear(), 0, 0).getTime()) / 86400000
  );
  const ytdTarget = Math.round((goal / 365) * dayOfYear);
  const behindBy = Math.max(0, ytdTarget - booksRead);

  // Real pace chart — cumulative books finished by month, from actual finish dates
  const byMonth = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
  for (const b of books) {
    const m = new Date(b.finished_date + "T00:00:00").getMonth();
    byMonth[m]++;
  }
  const currentMonth = now.getMonth();
  const cumulative: number[] = [];
  let running = 0;
  for (let i = 0; i <= currentMonth; i++) {
    running += byMonth[i];
    cumulative.push(running);
  }
  const monthLabels = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"].slice(0, currentMonth + 1);
  const targetLine = monthLabels.map((_, i) => +((goal / 12) * (i + 1)).toFixed(1));

  const sortedBooks = [...books].sort((a, b) => b.finished_date.localeCompare(a.finished_date));

  return (
    <div className="ons-page" style={{ padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" }}>
      <PageHead
        title="Reading"
        kicker="2026 · via Hardcover"
        right={
          <div className="font-mono text-right text-faint" style={{ fontSize: 9.5 }}>
            {booksRead} OF {goal} BOOKS<br />
            {behindBy > 0 ? `~${behindBy} BEHIND PACE` : "ON PACE"}
          </div>
        }
      />

      <StatBand>
        <Stat label="Books Read" value={booksRead} unit={`/ ${goal}`} accent />
        <Stat label="Fiction" value={fiction} />
        <Stat label="Nonfiction" value={nonfiction} />
        <Stat label="On-Pace Target" value={ytdTarget} unit="by now" last />
      </StatBand>

      <div className="grid gap-[22px] items-start" style={{ gridTemplateColumns: "1.4fr 1fr" }}>
        {/* Shelf — real books */}
        <Card pad={0}>
          <div className="flex justify-between items-center" style={{ padding: "16px 18px 12px" }}>
            <K>2026 Shelf · finished</K>
            <span className="font-mono text-faint" style={{ fontSize: 9.5 }}>
              {sortedBooks.length} BOOKS
            </span>
          </div>
          <div style={{ padding: "0 18px 16px" }}>
            {sortedBooks.length === 0 ? (
              <Empty message="No finished books synced from Hardcover yet." />
            ) : (
              sortedBooks.map((b, i) => (
                <div
                  key={i}
                  className="flex items-center gap-[14px] border-t border-border-2"
                  style={{ padding: "13px 6px", margin: "0 -6px" }}
                >
                  {/* spine */}
                  <div
                    className="shrink-0 relative"
                    style={{
                      width: 34, height: 48, borderRadius: "2px 3px 3px 2px",
                      background: spineColor(b.title),
                      boxShadow: "inset -3px 0 0 rgba(0,0,0,0.18), inset 3px 0 0 rgba(255,255,255,0.12)",
                    }}
                  >
                    <div
                      className="absolute"
                      style={{ left: 6, top: 5, bottom: 5, width: 1, background: "rgba(255,255,255,0.25)" }}
                    />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-serif font-semibold text-ink leading-tight" style={{ fontSize: 16 }}>
                      {b.title}
                    </div>
                    <div className="text-muted mt-[3px]" style={{ fontSize: 12 }}>{b.authors || "Unknown author"}</div>
                    <div className="flex items-center gap-[10px] mt-1.5">
                      <span
                        className="font-mono uppercase rounded-full"
                        style={{
                          fontSize: 9, letterSpacing: "0.5px",
                          color: b.classification === "fiction" ? "#1d5536" : b.classification === "nonfiction" ? "#3a5f7a" : "#a39d8c",
                          border: `1px solid ${b.classification === "fiction" ? "#1d553633" : b.classification === "nonfiction" ? "#3a5f7a33" : "#e6e3dc"}`,
                          padding: "2px 8px",
                        }}
                      >
                        {b.classification === "unknown" ? "unclassified" : b.classification}
                      </span>
                    </div>
                  </div>
                  <span className="font-mono text-faint shrink-0" style={{ fontSize: 10 }}>
                    {b.finished_date.slice(5)}
                  </span>
                </div>
              ))
            )}
          </div>
        </Card>

        {/* Pace + split */}
        <div>
          <Card style={{ marginBottom: 22 }}>
            <div className="flex justify-between items-center mb-4">
              <K>Pace vs Goal · 2026</K>
              <span className="font-mono" style={{ fontSize: 9, color: behindBy > 0 ? "#a8473a" : "#1d5536" }}>
                {behindBy > 0 ? "BEHIND" : "ON TRACK"}
              </span>
            </div>
            {cumulative.length < 2 ? (
              <Empty message="Need more finished books across more months for a trend line." />
            ) : (
              <>
                <svg width="100%" viewBox="0 0 300 110" style={{ display: "block", overflow: "visible" }}>
                  {(() => {
                    const max = Math.max(goal, ...cumulative) || 1;
                    const xs = (i: number) => (i / (cumulative.length - 1)) * 300;
                    const ys = (v: number) => 100 - (v / max) * 96;
                    const tgt = targetLine.map((v, i) => `${i ? "L" : "M"}${xs(i).toFixed(1)} ${ys(v).toFixed(1)}`).join(" ");
                    const act = cumulative.map((v, i) => `${i ? "L" : "M"}${xs(i).toFixed(1)} ${ys(v).toFixed(1)}`).join(" ");
                    return (
                      <>
                        <path d={tgt} fill="none" stroke="#a39d8c" strokeWidth={1.4} strokeDasharray="3 3" />
                        <path d={`${act} L ${xs(cumulative.length - 1)} 100 L 0 100 Z`} fill="#1d5536" opacity="0.12" />
                        <path d={act} fill="none" stroke="#1d5536" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" />
                        <circle cx={xs(cumulative.length - 1)} cy={ys(cumulative[cumulative.length - 1])} r={3.5} fill="#1d5536" />
                      </>
                    );
                  })()}
                </svg>
                <div className="flex justify-between mt-1.5 font-mono text-faint" style={{ fontSize: 8.5 }}>
                  {monthLabels.map((m, i) => <span key={i}>{m}</span>)}
                </div>
              </>
            )}
            <div
              className="flex gap-4 font-mono border-t border-border-2 pt-3 mt-4"
              style={{ fontSize: 9.5 }}
            >
              <span className="text-green">● ACTUAL {booksRead}</span>
              <span className="text-faint">– – TARGET {ytdTarget}</span>
            </div>
          </Card>

          <Card>
            <K style={{ marginBottom: 16 }}>Fiction / Nonfiction</K>
            <div className="flex items-center gap-5">
              <Donut
                value={booksRead > 0 ? fiction / booksRead : 0}
                size={84}
                sw={11}
                color="#1d5536"
                track="#3a5f7a"
              >
                <div className="text-center">
                  <div className="font-serif text-[20px] font-bold">{booksRead}</div>
                  <div className="font-mono text-faint" style={{ fontSize: 7.5 }}>BOOKS</div>
                </div>
              </Donut>
              <div className="flex-1 flex flex-col gap-[10px]">
                <div className="flex items-center gap-[9px]">
                  <span className="rounded" style={{ width: 11, height: 11, background: "#1d5536" }} />
                  <span className="flex-1" style={{ fontSize: 13 }}>Fiction</span>
                  <span className="font-mono font-semibold" style={{ fontSize: 12 }}>{fiction}</span>
                </div>
                <div className="flex items-center gap-[9px]">
                  <span className="rounded" style={{ width: 11, height: 11, background: "#3a5f7a" }} />
                  <span className="flex-1" style={{ fontSize: 13 }}>Nonfiction</span>
                  <span className="font-mono font-semibold" style={{ fontSize: 12 }}>{nonfiction}</span>
                </div>
              </div>
            </div>
            <p className="text-faint italic mt-4 mb-0" style={{ fontSize: 11, lineHeight: 1.5 }}>
              In-progress books aren't tracked — Hardcover's data has no status field at all here, only finish dates. Would need a pipeline change to capture "currently reading."
            </p>
          </Card>
        </div>
      </div>
    </div>
  );
}
