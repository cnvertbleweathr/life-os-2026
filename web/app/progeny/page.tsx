"use client";

// Progeny (Logbook Color). The kids: countdowns, this week's learning focus, a timeline of quotes and firsts,
// learning paths, CDC milestones, read-alouds toward 1,000 Books Before Kindergarten, and baby prep.
// Neutral page: the kids aren't one of the nine life areas, so there's no area hue (DESIGN.md → One Lane, One
// Colour). Private: every /api/progeny call is owner-only, reads included, so over the public tunnel the page
// asks for the write key before it shows anything (api/routers/progeny.py).
// Reads come from the dbt marts; logging appends to data/progeny/*.jsonl and shows up after the 9am sync.

import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import {
  progenyApi, LockedError,
  type ProgenyOverview, type ProgenyOptions, type ProgenyEvent, type ProgenyPath, type ProgenyMilestone,
  type ProgenyReading, type ProgenyTitle, type ProgenyTask, type ProgenyBurnDay, type ProgenyKind, type ProgenyEventType,
} from "@/lib/api";
import { PageHead, Loading, ErrorState, Pill } from "@/components/ui/primitives";
import { PixelScene } from "@/components/ui/PixelScene";

const DAY = 86_400_000;
const fromIso = (iso: string) => { const [y, m, d] = iso.slice(0, 10).split("-").map(Number); return new Date(Date.UTC(y, m - 1, d, 12)); };
const fmt = (iso: string | null | undefined, o: Intl.DateTimeFormatOptions = { month: "short", day: "numeric", year: "numeric" }) =>
  iso ? new Intl.DateTimeFormat("en-US", { timeZone: "UTC", ...o }).format(fromIso(iso)) : "";
const short = (iso: string | null | undefined) => fmt(iso, { month: "short", day: "numeric" });
const plural = (n: number, one: string, many = one + "s") => `${n.toLocaleString()} ${n === 1 ? one : many}`;
const SYNC = "It shows up here after the 9am sync.";

const TABS = ["Timeline", "Learning paths", "Milestones", "Reading", "Baby prep"] as const;
type Tab = (typeof TABS)[number];
const DOMAIN_ORDER = ["social_emotional", "language", "cognitive", "movement"]; // the CDC checklists' order
const EVENT_LABEL: Record<ProgenyEventType, string> = { quote: "Quote", first: "First", milestone: "Milestone", path: "Learning" };

type Data = {
  timeline: ProgenyEvent[];
  paths: ProgenyPath[];
  milestones: ProgenyMilestone[];
  reading: { kids: ProgenyReading[]; titles: ProgenyTitle[] };
  prep: { tasks: ProgenyTask[]; burndown: ProgenyBurnDay[] };
  options: ProgenyOptions;
};

function Check({ ok }: { ok: boolean }) {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true">
      <circle cx="8" cy="8" r="6.5" />
      {ok && <path d="M5 8.2 7 10l4-4" />}
    </svg>
  );
}

function Section({ id, title, aside, children, className = "s12" }: { id: string; title: ReactNode; aside?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`ons-card ${className}`} aria-labelledby={id}>
      <div className="ons-ch"><h2 id={id}>{title}</h2>{aside && <span className="aside">{aside}</span>}</div>
      {children}
    </section>
  );
}

export default function ProgenyPage() {
  const [phase, setPhase] = useState<"loading" | "locked" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [ov, setOv] = useState<ProgenyOverview | null>(null);
  const [data, setData] = useState<Data | null>(null);
  const [tab, setTab] = useState<Tab>("Timeline");
  // Clicks this session that the warehouse hasn't caught up with yet (it loads at the 9am sync).
  const [seen, setSeen] = useState<Record<string, string>>({});
  const [done, setDone] = useState<Record<string, string>>({});
  const [rowError, setRowError] = useState<string | null>(null);

  const loadRest = useCallback(() => {
    Promise.all([progenyApi.timeline(), progenyApi.paths(), progenyApi.milestones(), progenyApi.reading(), progenyApi.prep(), progenyApi.options()])
      .then(([timeline, paths, milestones, reading, prep, options]) => { setData({ timeline, paths, milestones, reading, prep, options }); setPhase("ready"); })
      .catch((e) => { setError(e.message); setPhase("error"); });
  }, []);

  const load = useCallback((prompt: boolean) => {
    progenyApi.overview(prompt)
      .then((o) => { setOv(o); loadRest(); })
      .catch((e) => {
        if (e instanceof LockedError || /write key|401/i.test(e.message)) { setPhase("locked"); return; }
        setError(e.message); setPhase("error");
      });
  }, [loadRest]);

  useEffect(() => { load(false); }, [load]);

  const pad = { padding: "34px 44px 48px", maxWidth: 1380, margin: "0 auto" } as const;

  if (phase === "loading") return <Loading label="Loading Progeny…" />;
  if (phase === "error") return <div className="ons-page" style={pad}><ErrorState message={error ?? undefined} /></div>;
  if (phase === "locked") {
    return (
      <div className="ons-page" style={pad}>
        <PageHead title="Progeny" kicker="Private" sub="The kids' page is private. Over the internet it needs this device's write key, the same one check-ins use. On the Mac mini and over Tailscale it opens without one." />
        <button className="ons-btn pri ons-tap" onClick={() => { setPhase("loading"); load(true); }}>Enter write key</button>
      </div>
    );
  }
  if (!ov || !data) return <Loading label="Loading Progeny…" />;

  // ── Not set up yet ──────────────────────────────────────────────────────────
  if (!ov.configured) {
    return (
      <div className="ons-page" style={pad}>
        <PageHead title="Progeny" kicker="Not set up yet" sub={ov.config_error
          ? <>Couldn&apos;t read <code>data/progeny/kids.yaml</code>: {ov.config_error}</>
          : <>Add the kids to <code>data/progeny/kids.yaml</code>. It&apos;s gitignored, so names and dates never get committed. Start from the template: <code>cp progeny/config/kids.example.yaml data/progeny/kids.yaml</code>, then edit and reload.</>} />
      </div>
    );
  }

  const today = ov.today;
  const born = ov.kids.filter((k) => k.is_born);
  const expected = ov.kids.filter((k) => !k.is_born);
  const tasks = data.prep.tasks.map((t) => (done[t.task_id] ? { ...t, status: "done" as const, done_date: done[t.task_id] } : t));
  const openTasks = tasks.filter((t) => t.status !== "done");
  const overdue = tasks.filter((t) => t.status === "overdue").length;
  const reading0 = data.reading.kids.find((r) => born.some((k) => k.kid_id === r.kid_id));
  const focus0 = ov.focus[0];

  // ── Lede ────────────────────────────────────────────────────────────────────
  const lede = (
    <>
      {born.map((k) => (
        <span key={k.kid_id}>
          <b>{k.display_name} is {k.age_label}</b>{k.days_to_birthday === 0 ? <> and turns {k.turning_age} today. </> : <> and turns {k.turning_age} in {plural(k.days_to_birthday ?? 0, "day")}, on {fmt(k.next_birthday, { month: "long", day: "numeric" })}. </>}
        </span>
      ))}
      {expected.map((k) => (
        <span key={k.kid_id}>
          <b>{k.display_name} is due {fmt(k.due_date, { month: "long", day: "numeric" })}</b>
          {(k.days_to_due ?? 0) >= 0 ? <>, {plural(k.days_to_due ?? 0, "day")} away</> : <>, {plural(-(k.days_to_due ?? 0), "day")} ago: add the birthdate to kids.yaml</>}
          {tasks.length > 0 && <>, with {plural(openTasks.length, "prep task")} open{overdue ? ` (${overdue} overdue)` : ""}</>}. </span>
      ))}
      {focus0 && <>This week&apos;s focus for {focus0.display_name} is <b>{focus0.path_name.toLowerCase()}: {focus0.focus_level_name.toLowerCase()}</b>.</>}
    </>
  );
  const kicker = [...born.map((k) => `${k.display_name} ${k.age_label}`), ...expected.map((k) => `${k.display_name} due ${short(k.due_date)}`)].join(" · ");
  const sceneDue = expected[0]?.days_to_due != null && expected[0].days_to_due >= 0 ? expected[0].days_to_due : null;

  // ── Writes ──────────────────────────────────────────────────────────────────
  const markSeen = (m: ProgenyMilestone) => {
    setRowError(null);
    progenyApi.log("milestones", { kid: m.kid_id, milestone_id: m.milestone_id, observed_date: today })
      .then(() => setSeen((s) => ({ ...s, [`${m.kid_id}|${m.milestone_id}`]: today })))
      .catch((e) => setRowError(`Couldn't save: ${e.message}`));
  };
  const markDone = (t: ProgenyTask) => {
    setRowError(null);
    progenyApi.log("prep_tasks", { task: t.task, category: t.category, due_date: t.due_date, created_date: t.created_date, done_date: today }, t.task_id)
      .then(() => setDone((s) => ({ ...s, [t.task_id]: today })))
      .catch((e) => setRowError(`Couldn't save: ${e.message}`));
  };

  const tileCols = Math.min(4, ov.kids.length + (reading0 ? 1 : 0) + (expected.length ? 1 : 0)) || 1;

  return (
    <div className="ons-page" style={pad}>
      <PageHead
        title="Progeny"
        kicker={kicker}
        sub={lede}
        scene={<PixelScene scene="progeny" data={{ reads: reading0?.total_reads ?? 0, due: sceneDue }}
          label={`a kid kicking a ball across the lawn with the puggle; ${reading0 ? `${Math.floor(reading0.total_reads / 100)} books on the pile, one per 100 read-alouds` : "no books on the pile yet"}${sceneDue != null ? `; a pram by a sign reading ${sceneDue} days to the due date` : ""}`} />}
      />

      {/* ── Tiles ── */}
      <div className="ons-tiles" style={{ gridTemplateColumns: `repeat(${tileCols}, minmax(0, 1fr))` }}>
        {born.map((k) => (
          <section key={k.kid_id} className="ons-tile">
            <h2>{k.display_name} · {k.age_label}</h2>
            <div className="big n">{k.days_to_birthday === 0 ? "Today" : plural(k.days_to_birthday ?? 0, "day")}</div>
            <p>{k.days_to_birthday === 0 ? `Turning ${k.turning_age} today` : `Until turning ${k.turning_age} · ${fmt(k.next_birthday)}`}</p>
            {k.kindergarten_target && <p className="tnote">Kindergarten {fmt(k.kindergarten_target, { month: "short", year: "numeric" })}</p>}
          </section>
        ))}
        {expected.map((k) => (
          <section key={k.kid_id} className="ons-tile">
            <h2>{k.display_name} · due {short(k.due_date)}</h2>
            <div className="big n">{(k.days_to_due ?? 0) >= 0 ? plural(k.days_to_due ?? 0, "day") : `${plural(-(k.days_to_due ?? 0), "day")} past`}</div>
            <p>{(k.days_to_due ?? 0) >= 0 ? `Until the due date, ${fmt(k.due_date)}` : "Add the birthdate to kids.yaml"}</p>
            <p className="tnote">Rename and add the birthdate in kids.yaml when the baby arrives.</p>
          </section>
        ))}
        {reading0 && (
          <section className="ons-tile">
            <h2>{reading0.display_name} · read-alouds</h2>
            <div className="big n">{reading0.total_reads.toLocaleString()} of {reading0.goal_reads.toLocaleString()}</div>
            <p>{reading0.needed_per_day != null ? `${reading0.pace_per_day_30d.toFixed(1)} a day lately · ${reading0.needed_per_day.toFixed(1)} needed` : `${reading0.reads_last_30d} in the last 30 days`}</p>
            <div className="ons-bar l-plain" style={{ marginTop: "auto" }}><b style={{ width: `${Math.min(100, reading0.pct_to_goal)}%` }} /></div>
          </section>
        )}
        {expected.length > 0 && (
          <section className="ons-tile">
            <h2>Baby prep</h2>
            <div className="big n">{tasks.length ? `${tasks.length - openTasks.length} of ${tasks.length}` : "None yet"}</div>
            <p>{tasks.length ? `${plural(openTasks.length, "task")} open${overdue ? ` · ${overdue} overdue` : ""}` : "Add tasks in Log → Prep task."}</p>
            {tasks.length > 0 && <div className="ons-bar l-plain" style={{ marginTop: "auto" }}><b style={{ width: `${((tasks.length - openTasks.length) / tasks.length) * 100}%` }} /></div>}
          </section>
        )}
      </div>

      <div className="ons-grid">
        <div className="s8" style={{ minWidth: 0 }}>
          <div className="ons-tabs" role="tablist" aria-label="Progeny views">
            {TABS.map((t) => <button key={t} type="button" role="tab" aria-selected={t === tab} onClick={() => setTab(t)}>{t}</button>)}
          </div>
          {rowError && <p role="alert" style={{ color: "var(--neg)", fontSize: 13, margin: "0 0 12px" }}>{rowError}</p>}
          <div className="ons-col">
            {tab === "Timeline" && <Timeline events={data.timeline} />}
            {tab === "Learning paths" && <Paths paths={data.paths} />}
            {tab === "Milestones" && <Milestones rows={data.milestones} seen={seen} onSeen={markSeen} unborn={expected.map((k) => k.display_name)} />}
            {tab === "Reading" && <Reading reading={data.reading} />}
            {tab === "Baby prep" && <Prep tasks={tasks} burndown={data.prep.burndown} onDone={markDone} justDone={done} />}
          </div>
        </div>

        <div className="ons-col s4">
          {ov.focus.map((f) => (
            <section key={f.kid_id} className="ons-card" aria-labelledby={`focus-${f.kid_id}`}>
              <div className="ons-ch"><h2 id={`focus-${f.kid_id}`}>This week · {f.path_name}</h2><span className="aside">{f.display_name}</span></div>
              <div style={{ fontWeight: 600, fontSize: 15 }}>{f.focus_level_name}</div>
              <p className="m-0" style={{ fontSize: 13, color: "var(--muted)", marginTop: 2 }}>{f.is_complete ? "Path complete; keep practising" : `Level ${f.focus_level} of ${f.total_levels}`}</p>
              {f.focus_description && <p className="m-0" style={{ fontSize: 14, lineHeight: "21px", color: "var(--ink-2)", marginTop: 8 }}>{f.focus_description}</p>}
              {f.activities.length > 0 && <ul className="pg-acts">{f.activities.map((a) => <li key={a}>{a}</li>)}</ul>}
            </section>
          ))}
          <LogCard options={data.options} today={today} />
        </div>
      </div>
    </div>
  );
}

// ── Log ───────────────────────────────────────────────────────────────────────

const KINDS: { key: ProgenyKind; label: string }[] = [
  { key: "quotes", label: "Quote" }, { key: "firsts", label: "First" }, { key: "books", label: "Book" },
  { key: "path_evidence", label: "Learning" }, { key: "milestones", label: "Milestone" }, { key: "prep_tasks", label: "Prep task" },
];

function LogCard({ options, today }: { options: ProgenyOptions; today: string }) {
  const kids = options.kids;
  const bornKids = kids.filter((k) => k.birthdate);
  const [kind, setKind] = useState<ProgenyKind>("quotes");
  const [f, setF] = useState<Record<string, string>>({});
  const [bookKids, setBookKids] = useState<string[]>(bornKids[0] ? [bornKids[0].kid_id] : []);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ ok: boolean; msg: string } | null>(null);
  const set = (k: string) => (e: { target: { value: string } }) => setF((s) => ({ ...s, [k]: e.target.value }));
  const kidList = kind === "quotes" || kind === "firsts" ? kids : bornKids.length ? bornKids : kids;
  const kid = f.kid && kidList.some((k) => k.kid_id === f.kid) ? f.kid : kidList[0]?.kid_id ?? "";
  const date = f.date || today;

  const levelGroups = useMemo(() => {
    const g = new Map<string, ProgenyOptions["levels"]>();
    options.levels.forEach((l) => g.set(l.path_name, [...(g.get(l.path_name) ?? []), l]));
    return Array.from(g.entries());
  }, [options.levels]);
  const bandGroups = useMemo(() => {
    const g = new Map<string, ProgenyOptions["milestones"]>();
    options.milestones.forEach((m) => g.set(m.band_label, [...(g.get(m.band_label) ?? []), m]));
    return Array.from(g.entries());
  }, [options.milestones]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setStatus(null);
    try {
      let label = "";
      if (kind === "books") {
        if (!bookKids.length) throw new Error("pick at least one kid");
        for (const k of bookKids) await progenyApi.log("books", { kid: k, date, title: f.title, author: f.author });
        label = `“${f.title}”`;
      } else if (kind === "prep_tasks") {
        await progenyApi.log(kind, { task: f.task, category: f.category || options.prep_categories[0], due_date: f.due_date || null });
        label = "the task";
      } else if (kind === "path_evidence") {
        const [path, level] = (f.level || "").split("|");
        await progenyApi.log(kind, { kid, date, path, level, notes: f.notes });
        label = "the learning entry";
      } else if (kind === "milestones") {
        await progenyApi.log(kind, { kid, observed_date: date, milestone_id: f.milestone_id, notes: f.notes });
        label = "the milestone";
      } else if (kind === "quotes") {
        await progenyApi.log(kind, { kid, date, quote: f.quote, context: f.context });
        label = "the quote";
      } else {
        await progenyApi.log(kind, { kid, date, title: f.title, notes: f.notes });
        label = "the first";
      }
      setStatus({ ok: true, msg: `Saved ${label}. ${SYNC}` });
      setF({});
    } catch (err) {
      setStatus({ ok: false, msg: `Not saved: ${(err as Error).message}` });
    } finally {
      setBusy(false);
    }
  };

  const kidSelect = (
    <label>Kid
      <select className="ons-input" value={kid} onChange={set("kid")}>
        {kidList.map((k) => <option key={k.kid_id} value={k.kid_id}>{k.display_name}</option>)}
      </select>
    </label>
  );
  const dateInput = (label = "Date") => (
    <label>{label}<input className="ons-input" type="date" value={date} max={today} onChange={set("date")} required /></label>
  );

  return (
    <section className="ons-card" aria-labelledby="log-h">
      <div className="ons-ch"><h2 id="log-h">Log</h2><span className="aside">Loads at the 9am sync</span></div>
      <div className="pg-kinds" role="group" aria-label="What to log">
        {KINDS.map((k) => <Pill key={k.key} active={kind === k.key} onClick={() => { setKind(k.key); setStatus(null); }}>{k.label}</Pill>)}
      </div>
      <form className="pg-form" onSubmit={submit}>
        {kind === "quotes" && <>
          <div className="two">{kidSelect}{dateInput()}</div>
          <label>What they said<textarea className="ons-input" rows={3} value={f.quote ?? ""} onChange={set("quote")} required style={{ resize: "vertical" }} /></label>
          <label>Context (optional)<input className="ons-input" value={f.context ?? ""} onChange={set("context")} placeholder="At breakfast, in the car…" /></label>
        </>}
        {kind === "firsts" && <>
          <div className="two">{kidSelect}{dateInput()}</div>
          <label>First what?<input className="ons-input" value={f.title ?? ""} onChange={set("title")} required placeholder="Rode a bike without help" /></label>
          <label>Notes (optional)<textarea className="ons-input" rows={2} value={f.notes ?? ""} onChange={set("notes")} style={{ resize: "vertical" }} /></label>
        </>}
        {kind === "books" && <>
          <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
            <legend style={{ fontSize: 12, color: "var(--muted)", marginBottom: 6 }}>Read to</legend>
            <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
              {kids.map((k) => (
                <label key={k.kid_id} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 14, color: "var(--ink)" }}>
                  <input type="checkbox" checked={bookKids.includes(k.kid_id)} onChange={(e) => setBookKids((s) => e.target.checked ? [...s, k.kid_id] : s.filter((x) => x !== k.kid_id))} />
                  {k.display_name}
                </label>
              ))}
            </div>
          </fieldset>
          {dateInput()}
          <label>Title<input className="ons-input" list="pg-titles" value={f.title ?? ""} onChange={set("title")} required placeholder="Pick a past book or type a new one" /></label>
          <datalist id="pg-titles">{options.known_titles.map((t) => <option key={t} value={t} />)}</datalist>
          <label>Author (optional)<input className="ons-input" value={f.author ?? ""} onChange={set("author")} /></label>
          <p className="ons-note m-0">Re-reads count toward the 1,000 and are spotted automatically.</p>
        </>}
        {kind === "path_evidence" && <>
          <div className="two">{kidSelect}{dateInput()}</div>
          <label>Showed this level
            <select className="ons-input" value={f.level ?? ""} onChange={set("level")} required>
              <option value="" disabled>Pick a path and level</option>
              {levelGroups.map(([name, levels]) => (
                <optgroup key={name} label={name}>{levels.map((l) => <option key={l.level_key} value={`${l.path_key}|${l.level_key}`}>{l.level_num}. {l.level_name}</option>)}</optgroup>
              ))}
            </select>
          </label>
          <label>What you saw (optional)<input className="ons-input" value={f.notes ?? ""} onChange={set("notes")} /></label>
        </>}
        {kind === "milestones" && <>
          <div className="two">{kidSelect}{dateInput("Observed on")}</div>
          <label>Milestone
            <select className="ons-input" value={f.milestone_id ?? ""} onChange={set("milestone_id")} required>
              <option value="" disabled>Pick from the CDC checklist</option>
              {bandGroups.map(([band, ms]) => (
                <optgroup key={band} label={band}>{ms.map((m) => <option key={m.milestone_id} value={m.milestone_id}>{m.domain_label.split(" (")[0]} · {m.milestone}</option>)}</optgroup>
              ))}
            </select>
          </label>
          <label>Notes (optional)<input className="ons-input" value={f.notes ?? ""} onChange={set("notes")} /></label>
          <p className="ons-note m-0">Faster: the Milestones tab has a “Seen it” button on each item for the current and next age.</p>
        </>}
        {kind === "prep_tasks" && <>
          <label>Task<input className="ons-input" value={f.task ?? ""} onChange={set("task")} required placeholder="Install the car seat" /></label>
          <div className="two">
            <label>Category
              <select className="ons-input" value={f.category ?? options.prep_categories[0]} onChange={set("category")}>
                {options.prep_categories.map((c) => <option key={c}>{c}</option>)}
              </select>
            </label>
            <label>Due (optional)<input className="ons-input" type="date" value={f.due_date ?? ""} onChange={set("due_date")} /></label>
          </div>
        </>}
        <button className="ons-btn pri ons-tap" type="submit" disabled={busy} style={{ justifyContent: "center" }}>{busy ? "Saving…" : "Save"}</button>
        {status && <p role="status" className="m-0" style={{ fontSize: 13, color: status.ok ? "var(--ink-2)" : "var(--neg)" }}>{status.msg}</p>}
      </form>
    </section>
  );
}

// ── Timeline ──────────────────────────────────────────────────────────────────

function Timeline({ events }: { events: ProgenyEvent[] }) {
  const names = Array.from(new Set(events.map((e) => e.display_name)));
  const [who, setWho] = useState<string>("All");
  const [types, setTypes] = useState<ProgenyEventType[]>(["quote", "first", "milestone", "path"]);
  const view = events.filter((e) => types.includes(e.event_type) && (who === "All" || e.display_name === who));
  return (
    <Section id="tl-h" title="Timeline" aside="Newest first · age at the time">
      {events.length === 0 ? (
        <p className="ons-note m-0">No quotes, firsts, milestones or learning entries yet. Log one on the right. {SYNC}</p>
      ) : <>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 14 }}>
          {names.length > 1 && ["All", ...names].map((n) => <Pill key={n} active={who === n} onClick={() => setWho(n)}>{n}</Pill>)}
          {names.length > 1 && <span style={{ width: 10 }} />}
          {(Object.keys(EVENT_LABEL) as ProgenyEventType[]).map((t) => (
            <Pill key={t} active={types.includes(t)} onClick={() => setTypes((s) => s.includes(t) ? s.filter((x) => x !== t) : [...s, t])}>{EVENT_LABEL[t]}</Pill>
          ))}
        </div>
        {view.length === 0 ? <p className="ons-note m-0">Nothing matches those filters.</p> : (
          <div style={{ overflowX: "auto" }}>
            <table className="ons-table">
              <thead><tr><th>Date</th><th>What</th><th className="hide-p">Kind</th><th className="r hide-p">Age</th></tr></thead>
              <tbody>
                {view.map((e) => (
                  <tr key={e.event_id}>
                    <td className="ons-n" style={{ whiteSpace: "nowrap", verticalAlign: "top" }}>{short(e.event_date)}<span className="sub">{e.event_date.slice(0, 4)}</span></td>
                    <td>
                      <span className={e.event_type === "quote" ? "pg-quote" : undefined} style={{ fontWeight: e.event_type === "quote" ? 400 : 500 }}>{e.event_type === "quote" ? `“${e.title}”` : e.title}</span>
                      <span className="sub">{[names.length > 1 ? e.display_name : null, e.detail].filter(Boolean).join(" · ")}</span>
                    </td>
                    <td className="hide-p" style={{ verticalAlign: "top" }}><span className="pg-chip">{EVENT_LABEL[e.event_type]}</span></td>
                    <td className="r hide-p text-muted" style={{ whiteSpace: "nowrap", verticalAlign: "top", fontSize: 13 }}>{e.age_at_event ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </>}
    </Section>
  );
}

// ── Learning paths ────────────────────────────────────────────────────────────

function Paths({ paths }: { paths: ProgenyPath[] }) {
  const kids = Array.from(new Set(paths.map((p) => p.kid_id)));
  if (!kids.length) return <Section id="lp-h" title="Learning paths"><p className="ons-note m-0">Paths start at age 2, most at 2½. They appear once a kid is old enough and the sync has run.</p></Section>;
  return <>
    {kids.map((kid) => {
      const rows = paths.filter((p) => p.kid_id === kid);
      return (
        <Section key={kid} id={`lp-${kid}`} title={`Learning paths · ${rows[0].display_name}`} aside="Log a level you saw with Log → Learning">
          <div style={{ overflowX: "auto" }}>
            <table className="ons-table">
              <thead><tr><th>Path</th><th style={{ width: "22%" }}>Progress</th><th>Working on</th><th className="hide-p">Last seen</th></tr></thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={p.path_key}>
                    <td><span style={{ fontWeight: 500 }}>{p.path_name}</span><span className="sub">{p.reached_level_name ? `Reached: ${p.reached_level_name}` : "Not started"}</span></td>
                    <td><div className="ons-bar l-plain"><b style={{ width: `${p.pct_complete}%` }} /></div><span className="sub ons-n" style={{ fontSize: 12 }}>{p.reached_level ?? 0} of {p.total_levels}</span></td>
                    <td>{p.is_complete ? "Complete" : p.focus_level_name}<span className="sub">{p.activities[0] ?? ""}</span></td>
                    <td className="hide-p ons-n" style={{ whiteSpace: "nowrap", fontSize: 13 }}>{p.latest_evidence_date ? short(p.latest_evidence_date) : "–"}{p.latest_evidence_notes && <span className="sub" style={{ fontFamily: "inherit", whiteSpace: "normal" }}>{p.latest_evidence_notes}</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="ons-note">Paths and levels live in <code>progeny/reference/learning_paths.yaml</code>.</p>
        </Section>
      );
    })}
  </>;
}

// ── Milestones ────────────────────────────────────────────────────────────────

function Milestones({ rows, seen, onSeen, unborn }: { rows: ProgenyMilestone[]; seen: Record<string, string>; onSeen: (m: ProgenyMilestone) => void; unborn: string[] }) {
  const kids = Array.from(new Set(rows.map((r) => r.kid_id)));
  const intro = (
    <p className="ons-note m-0" style={{ marginBottom: 4 }}>
      From the CDC&apos;s <a className="ons-quietlink" href="https://www.cdc.gov/act-early/milestones/index.html" target="_blank" rel="noreferrer" style={{ textDecoration: "underline" }}>Learn the Signs. Act Early.</a> checklists: what most children (75% or more) do by each age. Something to bring to well-child visits, not a test.
      {unborn.length > 0 && <> {unborn.join(", ")}: the checklist starts once the birthdate is in kids.yaml.</>}
    </p>
  );
  if (!kids.length) return <Section id="ms-h" title="Milestones">{intro}</Section>;
  return <>
    {kids.flatMap((kid) => (["current", "next"] as const).map((role) => {
      const band = rows.filter((r) => r.kid_id === kid && r.band_role === role);
      if (!band.length) return null;
      const isSeen = (m: ProgenyMilestone) => m.is_observed || !!seen[`${m.kid_id}|${m.milestone_id}`];
      const n = band.filter(isSeen).length;
      const domains = DOMAIN_ORDER.filter((d) => band.some((m) => m.domain === d)).map((d) => band.find((m) => m.domain === d)!.domain_label);
      return (
        <Section key={`${kid}-${role}`} id={`ms-${kid}-${role}`}
          title={`${band[0].display_name} · ${role === "current" ? "by" : "coming up:"} ${band[0].band_label}`}
          aside={`${n} of ${band.length} seen`}>
          {role === "current" && intro}
          {domains.map((d) => (
            <div key={d}>
              <div className="pg-domain">{d}</div>
              {band.filter((m) => m.domain_label === d).sort((a, b) => a.sort_order - b.sort_order).map((m) => {
                const local = seen[`${m.kid_id}|${m.milestone_id}`];
                const ok = isSeen(m);
                return (
                  <div key={m.milestone_id} className={`pg-check ${ok ? "ok" : "todo"}`}>
                    <Check ok={ok} />
                    <span className="txt">{m.milestone}</span>
                    {m.is_observed ? <span className="when">{short(m.observed_date)}</span>
                      : local ? <span className="when">Saved · loads at 9am</span>
                      : <button className="ons-btn ons-tap" type="button" onClick={() => onSeen(m)} aria-label={`Seen it: ${m.milestone}`}>Seen it</button>}
                  </div>
                );
              })}
            </div>
          ))}
        </Section>
      );
    }))}
  </>;
}

// ── Reading ───────────────────────────────────────────────────────────────────

function Reading({ reading }: { reading: { kids: ProgenyReading[]; titles: ProgenyTitle[] } }) {
  const active = reading.kids.filter((r) => r.total_reads > 0);
  if (!active.length) return <Section id="rd-h" title="1,000 Books Before Kindergarten"><p className="ons-note m-0">No read-alouds logged yet. Log each one with Log → Book; re-reads count. {SYNC}</p></Section>;
  return <>
    {active.map((r) => {
      const titles = reading.titles.filter((t) => t.kid_id === r.kid_id).slice(0, 10);
      const onPace = r.needed_per_day == null || r.pace_per_day_30d >= r.needed_per_day;
      return (
        <Section key={r.kid_id} id={`rd-${r.kid_id}`} title={`1,000 Books Before Kindergarten · ${r.display_name}`} aside={r.kindergarten_target ? `Kindergarten ${fmt(r.kindergarten_target)}` : undefined}>
          <div className="ons-n" style={{ fontSize: 26, lineHeight: "32px", fontWeight: 600 }}>{r.total_reads.toLocaleString()} <span style={{ fontSize: 14, fontWeight: 400, color: "var(--muted)" }}>of {r.goal_reads.toLocaleString()}</span></div>
          <div className="ons-bar l-plain" style={{ margin: "10px 0 12px" }}><b style={{ width: `${Math.min(100, r.pct_to_goal)}%` }} /></div>
          <p className="m-0" style={{ fontSize: 14, lineHeight: "22px", color: "var(--ink-2)", maxWidth: "68ch" }}>
            {plural(r.unique_titles, "different title")}, {plural(r.repeat_reads, "re-read")}. {plural(r.reads_last_30d, "read")} in the last 30 days, {r.pace_per_day_30d.toFixed(1)} a day.
            {r.needed_per_day != null && r.days_to_kindergarten != null && r.days_to_kindergarten > 0 && <> {onPace ? "On pace" : <b>Behind pace</b>}: {r.reads_remaining.toLocaleString()} to go in {plural(r.days_to_kindergarten, "day")} needs {r.needed_per_day.toFixed(1)} a day.</>}
          </p>
          {titles.length > 0 && (
            <div style={{ overflowX: "auto", marginTop: 16 }}>
              <table className="ons-table">
                <thead><tr><th>Most read</th><th className="r">Reads</th><th className="r hide-p">Last read</th></tr></thead>
                <tbody>{titles.map((t) => (
                  <tr key={t.title_key}><td><span style={{ fontWeight: 500 }}>{t.title}</span>{t.author && <span className="sub">{t.author}</span>}</td><td className="r ons-n">{t.times_read}</td><td className="r hide-p ons-n">{short(t.last_read)}</td></tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </Section>
      );
    })}
  </>;
}

// ── Baby prep ─────────────────────────────────────────────────────────────────

function Burndown({ days }: { days: ProgenyBurnDay[] }) {
  if (days.length < 2) return null;
  const W = 640, Hh = 200, L = 30, R = 16, T = 10, B = 26;
  const t0 = fromIso(days[0].day).getTime(), t1 = fromIso(days[days.length - 1].day).getTime();
  const xOf = (iso: string) => L + ((fromIso(iso).getTime() - t0) / Math.max(DAY, t1 - t0)) * (W - L - R);
  const top = Math.max(1, ...days.map((d) => Math.max(d.open_tasks, d.ideal_open ?? 0)));
  const yOf = (v: number) => T + (1 - v / top) * (Hh - T - B);
  const past = days.filter((d) => !d.is_future);
  let actual = "";
  past.forEach((d, i) => { actual += i ? ` H${xOf(d.day).toFixed(1)} V${yOf(d.open_tasks).toFixed(1)}` : `M${xOf(d.day).toFixed(1)} ${yOf(d.open_tasks).toFixed(1)}`; });
  const ideal = days.filter((d) => d.ideal_open != null).map((d, i) => `${i ? "L" : "M"}${xOf(d.day).toFixed(1)} ${yOf(d.ideal_open as number).toFixed(1)}`).join(" ");
  const ticks = [0, Math.round(top / 2), top].filter((v, i, a) => a.indexOf(v) === i);
  const last = past[past.length - 1];
  const months = days.filter((d) => d.day.endsWith("-01"));
  return (
    <svg viewBox={`0 0 ${W} ${Hh}`} width="100%" role="img" style={{ display: "block", overflow: "visible", marginBottom: 8 }}
         aria-label={`Open prep tasks over time: ${last ? last.open_tasks : 0} open now; the dashed line reaches zero on the due date.`}>
      {ticks.map((v) => <g key={v}><line x1={L} x2={W - R} y1={yOf(v)} y2={yOf(v)} stroke="var(--rule)" /><text x={L - 8} y={yOf(v) + 4} textAnchor="end" fontSize="12" fill="var(--muted)" fontFamily="IBM Plex Mono, monospace">{v}</text></g>)}
      {months.map((d) => <text key={d.day} x={xOf(d.day) + 2} y={Hh - 6} fontSize="12" fill="var(--muted)">{fmt(d.day, { month: "short" })}</text>)}
      {ideal && <path d={ideal} fill="none" stroke="var(--muted)" strokeDasharray="4 4" />}
      {last && <line x1={xOf(last.day)} x2={xOf(last.day)} y1={T} y2={Hh - B} stroke="var(--hue)" />}
      {actual && <path d={actual} fill="none" stroke="var(--ink)" strokeWidth="2.5" strokeLinejoin="round" />}
      {last && <text x={xOf(last.day) + 6} y={yOf(last.open_tasks) - 6} fontSize="12" fontWeight="600" fill="var(--ink)" fontFamily="IBM Plex Mono, monospace">{last.open_tasks}</text>}
    </svg>
  );
}

function Prep({ tasks, burndown, onDone, justDone }: { tasks: ProgenyTask[]; burndown: ProgenyBurnDay[]; onDone: (t: ProgenyTask) => void; justDone: Record<string, string> }) {
  const [showDone, setShowDone] = useState(false);
  if (!tasks.length) return <Section id="pp-h" title="Baby prep"><p className="ons-note m-0">No prep tasks yet. Add some with Log → Prep task. {SYNC}</p></Section>;
  const open = tasks.filter((t) => t.status !== "done");
  const finished = tasks.filter((t) => t.status === "done");
  const cats = Array.from(new Set(open.map((t) => t.category || "Other")));
  const due = burndown.find((d) => d.baby_due_date)?.baby_due_date;
  return <>
    <Section id="pp-chart" title="Open tasks" aside={due ? `Dashed line: all done by the due date, ${fmt(due)}` : undefined}>
      <Burndown days={burndown} />
    </Section>
    <Section id="pp-h" title="To do" aside={`${open.length} open · ${finished.length} done`}>
      {open.length === 0 && <p className="ons-note m-0">Everything&apos;s done.</p>}
      {cats.map((c) => (
        <div key={c}>
          <div className="pg-domain">{c}</div>
          {open.filter((t) => (t.category || "Other") === c).map((t) => (
            <div key={t.task_id} className="pg-check todo">
              <Check ok={false} />
              <span className="txt">{t.task}{t.due_date && <span className="sub" style={{ display: "block", fontSize: 13, color: t.status === "overdue" ? "var(--neg)" : "var(--muted)" }}>{t.status === "overdue" ? `Overdue since ${short(t.due_date)}` : `Due ${short(t.due_date)}`}</span>}</span>
              <button className="ons-btn ons-tap" type="button" onClick={() => onDone(t)} aria-label={`Done: ${t.task}`}>Done</button>
            </div>
          ))}
        </div>
      ))}
      {finished.length > 0 && <>
        <button type="button" className="ons-btn ons-tap" style={{ marginTop: 16 }} onClick={() => setShowDone((s) => !s)} aria-expanded={showDone}>{showDone ? "Hide done" : `Show done (${finished.length})`}</button>
        {showDone && finished.map((t) => (
          <div key={t.task_id} className="pg-check ok">
            <Check ok />
            <span className="txt">{t.task}</span>
            <span className="when">{justDone[t.task_id] ? "Saved · loads at 9am" : short(t.done_date)}</span>
          </div>
        ))}
      </>}
    </Section>
  </>;
}
