"use client";

// Paste RECAP (secretary step 8). The voice-chat check-in ends with a RECAP block
// (docs/context/checkin-protocol.md). Pasting it here appends it to data/checkin/recaps.jsonl;
// the 4am sync's ingest_recap step marks Done milestones and proposes new projects / critical
// people (never active on their own). The preview shows what that run will do.

import { useCallback, useEffect, useState } from "react";
import { checkinApi, type RecapPreview, type RecapRow } from "@/lib/api";

const PLACEHOLDER = `RECAP 2026-12-04
Wins: …; …
Top 3 next week: 1) … 2) … 3) …
Decisions: …
Parking lot: …
Commitments: Me — …
Done: <project> — <milestone>
New project: <name> | deadline 2027-03-01 | tier important | notes
New critical person: <name>`;

const fmtWhen = (iso: string) =>
  new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(iso));
const plural = (n: number, one: string, many = one + "s") => `${n} ${n === 1 ? one : many}`;

function summary(r: NonNullable<RecapRow["result"]>): string {
  if (!r.ok) return "Couldn't be applied";
  const bits = [
    r.done?.length ? plural(r.done.length, "milestone") + " done" : "",
    r.proposed_projects?.length ? plural(r.proposed_projects.length, "project") + " proposed" : "",
    r.proposed_people?.length ? plural(r.proposed_people.length, "person", "people") + " proposed" : "",
    r.problems?.length ? plural(r.problems.length, "problem") : "",
  ].filter(Boolean);
  return bits.length ? `Applied: ${bits.join(", ")}` : "Applied: nothing for ONS to do";
}

function Preview({ p }: { p: RecapPreview }) {
  const items = [
    ...p.done.map((d) => `Mark done: ${d.label}${d.already ? " (already done)" : ""}${d.note ? ` (${d.note})` : ""}`),
    ...p.projects.map((x) => `Propose project: ${x.name} (${x.tier.replace(/_/g, " ")}, ${plural(x.milestones.length, "milestone")}), as a draft`),
    ...p.people.map((x) => `Propose critical person: ${x.name}`),
    ...p.skipped.map((s) => `Skip: ${s}`),
  ];
  return (
    <div className="rc-preview" role="status">
      <p className="rc-lead">Saved. At the 4am sync, ONS will:</p>
      {items.length ? <ul>{items.map((t) => <li key={t}>{t}</li>)}</ul> : <p className="ons-note m-0">Nothing to act on (wins, decisions and the rest are kept with the recap).</p>}
      {p.problems.length > 0 && (
        <ul className="rc-problems">{p.problems.map((t) => <li key={t}>{t}</li>)}</ul>
      )}
      {(p.projects.length > 0 || p.people.length > 0) && (
        <p className="ons-note">Proposals land in <code>data/secretary/*.proposed.yaml</code>. Nothing starts until you move it into <code>projects.yaml</code> or <code>secretary.yaml</code>.</p>
      )}
    </div>
  );
}

export function RecapCard() {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<RecapPreview | null>(null);
  const [recent, setRecent] = useState<RecapRow[] | null>(null);

  const loadRecent = useCallback(() => {
    checkinApi.recaps().then(setRecent).catch(() => setRecent(null));   // no key on this device: just no list
  }, []);
  useEffect(() => { loadRecent(); }, [loadRecent]);

  const save = () => {
    setBusy(true); setError(null); setPreview(null);
    checkinApi.recap(text)
      .then((r) => { setPreview(r.preview); setText(""); loadRecent(); })
      .catch((e) => setError(e.message))
      .finally(() => setBusy(false));
  };

  const looksLikeRecap = /^\s*\**\s*RECAP\b/i.test(text);

  return (
    <section className="ons-card rc-card" aria-labelledby="rc-h">
      <div className="ons-ch"><h2 id="rc-h">Paste RECAP</h2><span className="aside">From the voice-chat check-in</span></div>
      <p className="ons-note m-0" style={{ marginBottom: 12 }}>
        Paste the RECAP block the check-in ends with. <code>Done:</code> lines mark project milestones done;{" "}
        <code>New project:</code> and <code>New critical person:</code> become proposals for you to review.
      </p>
      <label htmlFor="rc-text" className="sr-only">RECAP text</label>
      <textarea
        id="rc-text"
        className="ons-input rc-text"
        rows={9}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={PLACEHOLDER}
        spellCheck={false}
      />
      {text.trim() && !looksLikeRecap && <p className="ons-note" style={{ color: "var(--neg)" }}>A RECAP starts with a line like “RECAP 2026-12-04”.</p>}
      {error && <p role="alert" className="ons-note" style={{ color: "var(--neg)" }}>Couldn&apos;t save: {error}</p>}
      <div style={{ marginTop: 12 }}>
        <button type="button" className="ons-btn pri ons-tap" disabled={busy || !looksLikeRecap} onClick={save}>
          {busy ? "Saving…" : "Save RECAP"}
        </button>
      </div>
      {preview && <Preview p={preview} />}
      {recent && recent.length > 0 && (
        <div className="rc-recent">
          <h3>Recent</h3>
          <ul>
            {recent.map((r) => (
              <li key={r.recap_id}>
                <span className="d">RECAP {r.recap_date}</span>
                <span className="t">{r.result ? summary(r.result) : "Waiting for the 4am sync"}</span>
                <span className="w">pasted {fmtWhen(r.submitted_at)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
