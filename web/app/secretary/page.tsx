"use client";

// Secretary (Logbook Color, the Plans area: rose). Heads-ups for birthdays, holidays and deadlines, by importance
// tier, with Done / Dismiss, and the next 30 days. Tiers use the week strip's marks: critical solid, important tint,
// nice to know outlined. Private: /api/secretary is owner-only, reads included (birthdays, family names).
// Reads: secretary.headsups + int_events_tiered. A click appends to data/secretary/headsup_actions.jsonl; the page
// shows it at once and the 4am sync writes it to the warehouse (api/routers/secretary.py).

import { useCallback, useEffect, useState } from "react";
import { secretaryApi, LockedError, type Headsup, type HeadsupStatus, type SecretaryOverview, type SecretaryTier } from "@/lib/api";
import { PageHead, Loading, ErrorState } from "@/components/ui/primitives";
import { PixelScene } from "@/components/ui/PixelScene";

const TIER_LABEL: Record<SecretaryTier, string> = { critical: "Critical", important: "Important", nice_to_know: "Nice to know", trivia: "Trivia" };
const fromIso = (iso: string) => { const [y, m, d] = iso.slice(0, 10).split("-").map(Number); return new Date(Date.UTC(y, m - 1, d, 12)); };
const fmt = (iso: string, o: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat("en-US", { timeZone: "UTC", ...o }).format(fromIso(iso));
const md = (iso: string) => fmt(iso, { month: "short", day: "numeric" });
const wmd = (iso: string) => `${fmt(iso, { weekday: "short" })} ${md(iso)}`;   // "Wed Nov 25", like the paper
const rel = (n: number) => (n === 0 ? "today" : n === 1 ? "tomorrow" : `${n} days`);
const inRel = (n: number) => (n === 0 ? "today" : n === 1 ? "tomorrow" : `in ${n} days`);
const plural = (n: number, one: string, many = one + "s") => `${n} ${n === 1 ? one : many}`;
const addDays = (iso: string, n: number) => { const d = fromIso(iso); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };

function Tier({ tier }: { tier: SecretaryTier }) {
  return <span className={`sc-tier ${tier}`}>{TIER_LABEL[tier]}</span>;
}

/** Where the heads-up stands today, in the page's own words. */
/** The nag limit and its one exception: critical heads-ups show daily from `daily` days out through the day. */
type Nag = { limit: number; daily: number };

function standing(h: Headsup, nag: Nag): { text: string; on?: boolean } | null {
  if (h.queued) return { text: h.status === "open" ? "Reopened · syncs at 4am" : "Saved · syncs at 4am" };
  if (h.status !== "open") return null;
  if (h.shown_today) {
    const paper = h.surfaces.includes("paper") || h.surfaces.includes("paper_lead");
    return { text: paper ? "On today's paper" : "In today's check-in", on: true };
  }
  const daily = h.tier === "critical" && h.days_to_go <= nag.daily;
  if (!daily && h.shown_count >= nag.limit) {
    return { text: h.tier === "critical"
      ? `Shown ${plural(h.shown_count, "day")} · back daily from ${plural(nag.daily, "day")} out`
      : `Shown ${plural(h.shown_count, "day")} · off the paper now` };
  }
  return null;
}

function Row({ h, nag, busy, onAct }: { h: Headsup; nag: Nag; busy: boolean; onAct: (h: Headsup, a: "done" | "dismiss" | "reopen") => void }) {
  const closed = h.status !== "open";
  const s = standing(h, nag);
  return (
    <div className={`sc-row${closed ? " closed" : ""}`}>
      <div className="sc-when">{md(h.event_date)}<span>{rel(h.days_to_go)}</span></div>
      <div style={{ minWidth: 0 }}>
        <p className="sc-text">{h.text}</p>
        <div className="sc-meta">
          <Tier tier={h.tier} />
          {closed && <span>{h.status === "done" ? "Done" : "Dismissed"}</span>}
          {s && <span className={s.on ? "on" : undefined}>{s.text}</span>}
        </div>
      </div>
      <div className="sc-acts">
        {closed ? (
          <button type="button" className="ons-btn ons-tap" disabled={busy} onClick={() => onAct(h, "reopen")} aria-label={`Undo: ${h.title}`}>Undo</button>
        ) : (
          <>
            <button type="button" className="ons-btn ons-tap" disabled={busy} onClick={() => onAct(h, "done")} aria-label={`Done: ${h.title}`}>Done</button>
            <button type="button" className="ons-btn ons-tap" disabled={busy} onClick={() => onAct(h, "dismiss")} aria-label={`Dismiss: ${h.title}`}>Dismiss</button>
          </>
        )}
      </div>
    </div>
  );
}

export default function SecretaryPage() {
  const [phase, setPhase] = useState<"loading" | "locked" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [ov, setOv] = useState<SecretaryOverview | null>(null);
  // Clicks this session, shown at once (the server overlays them too, so they survive a reload).
  const [local, setLocal] = useState<Record<string, HeadsupStatus>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);
  const [showClosed, setShowClosed] = useState(false);

  const load = useCallback((prompt: boolean) => {
    secretaryApi.overview(prompt)
      .then((o) => { setOv(o); setPhase("ready"); })
      .catch((e) => {
        if (e instanceof LockedError || /write key|401/i.test(e.message)) { setPhase("locked"); return; }
        setError(e.message); setPhase("error");
      });
  }, []);
  useEffect(() => { load(false); }, [load]);

  const act = (h: Headsup, a: "done" | "dismiss" | "reopen") => {
    const next: HeadsupStatus = a === "done" ? "done" : a === "dismiss" ? "dismissed" : "open";
    setBusy(h.headsup_id); setRowError(null);
    secretaryApi.act(h.headsup_id, a)
      .then(() => setLocal((s) => ({ ...s, [h.headsup_id]: next })))
      .catch((e) => setRowError(`Couldn't save "${h.title}": ${e.message}`))
      .finally(() => setBusy(null));
  };

  const pad = { padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" } as const;
  if (phase === "loading") return <Loading label="Loading Secretary…" />;
  if (phase === "error") return <div className="ons-page" style={pad}><ErrorState message={error ?? undefined} /></div>;
  if (phase === "locked") {
    return (
      <div className="ons-page" style={pad}>
        <PageHead title="Secretary" kicker="Private" sub="Birthdays and family dates stay private. Over the internet this page needs this device's write key, the same one check-ins use. On the Mac mini and over Tailscale it opens without one." />
        <button className="ons-btn pri ons-tap" onClick={() => { setPhase("loading"); load(true); }}>Enter write key</button>
      </div>
    );
  }
  if (!ov) return <Loading label="Loading Secretary…" />;

  const all = ov.headsups.map((h) => (local[h.headsup_id] && local[h.headsup_id] !== h.status
    ? { ...h, status: local[h.headsup_id], queued: true } : h));
  const open = all.filter((h) => h.status === "open");
  const closed = all.filter((h) => h.status !== "open");
  const onPaper = open.filter((h) => h.shown_today && (h.surfaces.includes("paper") || h.surfaces.includes("paper_lead")));
  const sentence = (t: string) => (/[.?!]$/.test(t.trim()) ? t.trim() : `${t.trim()}.`);
  const nextCritical = ov.upcoming.find((e) => e.tier === "critical");
  const nag: Nag = { limit: ov.nag_limit, daily: ov.critical_daily_days ?? 3 };
  const proposed = [
    ...(ov.proposals?.projects ?? []).map((n) => `Proposed project: ${n}`),
    ...(ov.proposals?.people ?? []).map((n) => `Proposed critical person: ${n}`),
  ];
  const end = addDays(ov.today, 30);

  // ── Lede: what needs you, then the next critical date ───────────────────────
  const first = open[0];
  const firstIsNext = !!(first && nextCritical && first.event_key === nextCritical.event_key);
  const lede = (
    <>
      {first
        ? <><b>{plural(open.length, "heads-up")} {open.length === 1 ? "needs" : "need"} you</b>{onPaper.length ? `, ${onPaper.length} on today's paper` : ""}. Top of the list: {sentence(first.text)} </>
        : <><b>Nothing needs you today.</b> </>}
      {nextCritical && !firstIsNext && <>Next critical date: <b>{nextCritical.title}, {wmd(nextCritical.event_date)}</b> ({inRel(nextCritical.days_to_go)}). </>}
      {!nextCritical && <>No critical dates in the next 30 days. </>}
      Mark each one done when it&apos;s handled.
    </>
  );
  const sceneLabel = nextCritical
    ? `a desk calendar flipping its pages toward ${nextCritical.title}, ${inRel(nextCritical.days_to_go)}; ${plural(open.length, "letter")} in the tray`
    : `a desk calendar with a clear month; ${plural(open.length, "letter")} in the tray`;

  return (
    <div className="ons-page t-plan" style={pad}>
      <PageHead
        title="Secretary"
        kicker={`Today and the next 30 days · ${wmd(ov.today)} – ${wmd(end)}`}
        sub={lede}
        scene={<PixelScene scene="secretary" data={{ days: nextCritical?.days_to_go ?? -1, open: open.length }} label={sceneLabel} />}
      />

      {!ov.calendar.ok && (
        <div className="sc-alert" role="status">
          <b>Calendar unavailable today.</b> {(ov.calendar.message ?? "the calendar sync didn't run").replace(/^\w/, (c) => c.toUpperCase()).replace(/\.?$/, ".")} Birthdays and holidays from templates still show; calendar events don&apos;t.
          {" "}Fix: on the Mac mini, run <code>uv run python scripts/calendar_export.py --auth</code>.
        </div>
      )}

      <div className="ons-grid">
        <div className="s8 ons-col no-stretch">
        <section className="ons-card" aria-labelledby="sc-h">
          <div className="ons-ch"><h2 id="sc-h">Heads-ups</h2><span className="aside">{open.length} open{closed.length ? ` · ${closed.length} handled` : ""}</span></div>
          {rowError && <p role="alert" style={{ color: "var(--neg)", fontSize: 13, margin: "0 0 12px" }}>{rowError}</p>}
          {open.length === 0 && <p className="ons-note m-0">No open heads-ups. New ones arrive with the 4am sync as dates come into range.</p>}
          {open.map((h) => <Row key={h.headsup_id} h={h} nag={nag} busy={busy === h.headsup_id} onAct={act} />)}
          {closed.length > 0 && <>
            <button type="button" className="ons-btn ons-tap" style={{ marginTop: 16 }} onClick={() => setShowClosed((s) => !s)} aria-expanded={showClosed}>
              {showClosed ? "Hide handled" : `Show handled (${closed.length})`}
            </button>
            {showClosed && <div style={{ marginTop: 12 }}>{closed.map((h) => <Row key={h.headsup_id} h={h} nag={nag} busy={busy === h.headsup_id} onAct={act} />)}</div>}
          </>}
        </section>

        {(ov.projects?.length ?? 0) > 0 && (
          <section className="ons-card" aria-labelledby="sc-pr">
            <div className="ons-ch"><h2 id="sc-pr">Life projects</h2><span className="aside">Mark milestones done in the check-in RECAP</span></div>
            {ov.projects!.map((p) => (
              <div key={p.key} className="sc-proj">
                <div className="sc-proj-h">
                  <b>{p.name}</b> <Tier tier={p.tier} />
                  <span className="n">{p.done_count} of {p.open_count + p.done_count} done</span>
                </div>
                <ul className="sc-cal">
                  {p.overdue.map((m) => <li key={m.key} className="over"><i className="sc-dot critical" aria-hidden="true" /><span className="d">{m.label}</span><span className="t">{m.title}{m.deadline ? " (deadline)" : ""} <small>· overdue, {m.rel}</small></span></li>)}
                  {p.due.map((m) => <li key={m.key}><i className={`sc-dot ${p.tier}`} aria-hidden="true" /><span className="d">{m.label}</span><span className="t">{m.title}{m.deadline ? " (deadline)" : ""} <small>· {m.rel}</small></span></li>)}
                  {p.next && <li key={p.next.key}><i className="sc-dot nice_to_know" aria-hidden="true" /><span className="d">{p.next.label}</span><span className="t">Next: {p.next.title}{p.next.deadline ? " (deadline)" : ""} <small>· {p.next.rel}</small></span></li>}
                  {p.done.map((m) => <li key={m.key} className="done"><i className="sc-dot done" aria-hidden="true" /><span className="d">{m.label}</span><span className="t">{m.title} <small>· done</small></span></li>)}
                </ul>
              </div>
            ))}
          </section>
        )}
        </div>

        <div className="s4 ons-col no-stretch">
          <section className="ons-card" aria-labelledby="sc-up">
            <div className="ons-ch"><h2 id="sc-up">Next 30 days</h2><span className="aside">{ov.upcoming.length} dates</span></div>
            {ov.upcoming.length === 0
              ? <p className="ons-note m-0">Nothing on the calendar or in the templates for the next 30 days.</p>
              : <ul className="sc-cal">
                  {ov.upcoming.map((e) => (
                    <li key={e.event_key} className={e.tier}>
                      <i className={`sc-dot ${e.tier}`} aria-hidden="true" />
                      <span className="d">{wmd(e.event_date)}</span>
                      <span className="t">{e.title}{e.time && <small> · {e.time}</small>}<span className="sr-only"> ({TIER_LABEL[e.tier]})</span></span>
                    </li>
                  ))}
                </ul>}
            <div className="sc-legend" aria-hidden="true">
              <span><i className="sc-dot critical" />Critical</span>
              <span><i className="sc-dot important" />Important</span>
              <span><i className="sc-dot nice_to_know" />Nice to know</span>
            </div>
          </section>

          {(ov.placeholders.length > 0 || ov.problems.length > 0 || !ov.configured || proposed.length > 0) && (
            <section className="ons-card" aria-labelledby="sc-todo">
              <div className="ons-ch"><h2 id="sc-todo">To review</h2><span className="aside">{ov.placeholders.length + ov.problems.length + proposed.length}</span></div>
              {!ov.configured && <p className="ons-note m-0" style={{ marginBottom: 10 }}>No settings yet: copy <code>secretary/config/secretary.example.yaml</code> to <code>data/secretary/secretary.yaml</code>.</p>}
              <ul className="sc-todo">
                {proposed.map((p) => <li key={p}>{p}</li>)}
                {ov.placeholders.map((p) => <li key={p}>Fill in: {p}</li>)}
                {ov.problems.map((p) => <li key={p} style={{ color: "var(--neg)" }}>{p}</li>)}
              </ul>
              {proposed.length > 0 && <p className="ons-note">Proposals came from check-in RECAPs and sit in <code>projects.proposed.yaml</code> / <code>secretary.proposed.yaml</code>. Move one into <code>projects.yaml</code> or <code>secretary.yaml</code> to start it.</p>}
              <p className="ons-note">Edit the files in <code>data/secretary/</code> (private, never committed). Changes show after the next sync.</p>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
