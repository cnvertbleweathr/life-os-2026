"use client";

/**
 * Capture — the ONS inbox (ROADMAP P0 Capture Inbox).
 *
 * Get a thought out of your head in a few seconds. Items append to
 * data/inbox/capture_inbox.jsonl through POST /api/inbox and land in
 * raw.capture_inbox on the nightly sync. Triage and turning items into
 * actions come later; this page only captures and shows what's waiting.
 */

import { useEffect, useRef, useState } from "react";
import { inboxApi, type CaptureItem, type CaptureKind } from "@/lib/api";
import { Card, PageHead, K, Pill, Empty } from "@/components/ui/primitives";
import { OnsIcon } from "@/components/ui/icons";

const KINDS: { key: CaptureKind; label: string }[] = [
  { key: "note", label: "Note" },
  { key: "idea", label: "Idea" },
  { key: "task", label: "Task" },
  { key: "link", label: "Link" },
  { key: "log", label: "Log" },
];

const DOMAINS = ["fitness", "reading", "music", "habits", "cfb", "ons", "work", "home"];

function looksLikeLink(text: string) {
  return /^https?:\/\/\S+$/i.test(text.trim());
}

function when(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const sameDay = d.toDateString() === new Date().toDateString();
  return sameDay
    ? d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })
    : d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export default function CapturePage() {
  const [text, setText] = useState("");
  const [kind, setKind] = useState<CaptureKind>("note");
  const [domain, setDomain] = useState<string | null>(null);
  const [items, setItems] = useState<CaptureItem[] | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const box = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    inboxApi.list(30).then(setItems).catch(() => setItems([]));
    box.current?.focus();
  }, []);

  const canSave = text.trim().length > 0 && !saving;

  const save = () => {
    if (!canSave) return;
    const k = kind === "note" && looksLikeLink(text) ? "link" : kind;
    setSaving(true);
    setMessage(null);
    inboxApi
      .capture(text, k, domain ?? undefined)
      .then((item) => {
        setItems((prev) => [item, ...(prev ?? [])]);
        setText("");
        setMessage({ ok: true, text: "Captured" });
        box.current?.focus();
      })
      .catch((e) => setMessage({ ok: false, text: `Couldn't save — ${e.message}` }))
      .finally(() => setSaving(false));
  };

  return (
    <div className="ons-page" style={{ padding: "34px 24px 48px", maxWidth: 760, margin: "0 auto" }}>
      <PageHead
        title="Capture"
        kicker="Get it out of your head · sort it later"
        right={
          <div className="font-mono text-right text-faint" style={{ fontSize: 9.5 }}>
            {items ? `${items.length} IN INBOX` : ""}
            <br />⌘↵ TO SAVE
          </div>
        }
      />

      <Card accent style={{ marginBottom: 22 }}>
        <textarea
          ref={box}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            if (message?.ok) setMessage(null);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              save();
            }
          }}
          rows={4}
          maxLength={4000}
          placeholder="An idea, a task, a link, something to log…"
          aria-label="Capture text"
          className="ons-input w-full font-sans"
          style={{ resize: "vertical", fontSize: 15, lineHeight: 1.45 }}
        />

        <div className="flex flex-wrap items-center gap-2 mt-3">
          <K style={{ marginRight: 4 }}>Kind</K>
          {KINDS.map((k) => (
            <Pill key={k.key} active={kind === k.key} onClick={() => setKind(k.key)}>
              {k.label}
            </Pill>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2 mt-[10px]">
          <K style={{ marginRight: 4 }}>Area</K>
          {DOMAINS.map((d) => (
            <Pill
              key={d}
              active={domain === d}
              color="#2f6b43"
              onClick={() => setDomain(domain === d ? null : d)}
            >
              {d}
            </Pill>
          ))}
        </div>

        <div className="flex items-center gap-3 mt-4">
          <button
            className="ons-tap font-semibold"
            onClick={save}
            disabled={!canSave}
            style={{
              padding: "12px 22px", borderRadius: 8, border: "none", fontSize: 14,
              cursor: canSave ? "pointer" : "not-allowed",
              background: canSave ? "#1d5536" : "#e6e3dc",
              color: canSave ? "#fff" : "#a39d8c",
            }}
          >
            {saving ? "Saving…" : "Capture"}
          </button>
          {message && (
            <span
              className="font-mono"
              role={message.ok ? "status" : "alert"}
              style={{ fontSize: 11, color: message.ok ? "#1d5536" : "#a8473a" }}
            >
              {message.text}
            </span>
          )}
        </div>
      </Card>

      <Card pad={0}>
        <div className="flex justify-between items-center" style={{ padding: "16px 18px 10px" }}>
          <K>Inbox · newest first</K>
          <span className="text-green">
            <OnsIcon name="inbox" size={16} />
          </span>
        </div>
        {items === null ? null : items.length === 0 ? (
          <Empty message="Nothing captured yet." detail="Whatever you add shows up here." />
        ) : (
          <ul className="m-0 p-0 list-none">
            {items.map((it) => (
              <li
                key={it.capture_id}
                style={{ padding: "12px 18px", borderTop: "1px solid #ebe5d8" }}
              >
                <div
                  style={{ fontSize: 14, lineHeight: 1.45, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}
                >
                  {it.kind === "link" && looksLikeLink(it.text) ? (
                    <a href={it.text.trim()} target="_blank" rel="noreferrer" className="text-green">
                      {it.text}
                    </a>
                  ) : (
                    it.text
                  )}
                </div>
                <div className="font-mono text-faint mt-[5px]" style={{ fontSize: 9.5, letterSpacing: "0.5px" }}>
                  {it.kind.toUpperCase()}
                  {it.domain ? ` · ${it.domain.toUpperCase()}` : ""}
                  {` · ${when(it.captured_at)}`}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
