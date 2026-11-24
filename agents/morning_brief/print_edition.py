"""
Print the morning paper: a saved edition → a one-page newspaper PDF → the printer.

    data/brief/<date>.json ──► HTML (newspaper layout) ──► Chrome headless ──► <date>.pdf ──► lp

Rules:
- Only published editions print automatically; needs_review editions print
  only when asked by date with --force (they carry a "needs review" banner).
- --auto (the daily_sync path) prints Monday–Friday only, as chosen Nov 2026.
- An edition prints once; --force prints it again.
- Black and white on Letter by default (ColorModel=Mono) to save colour ink.

Printer: ONS_PRINTER, else the system default (set to the Epson Artisan 720's
network queue, EPSONE0E8CD__Artisan_720___IP_, in Nov 2026).

    uv run python -m agents.morning_brief.print_edition                    # today's edition
    uv run python -m agents.morning_brief.print_edition --date 2026-11-23
    uv run python -m agents.morning_brief.print_edition --pdf-only         # make the PDF, don't print
    uv run python -m agents.morning_brief.print_edition --file data/ai/morning_brief/fixture_runs/2026-11-21.json --pdf-only
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import tempfile
from datetime import date, datetime
from datetime import time as dt_time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from api.store import JsonlLog, now_local, timestamp, today_local
from agents.morning_brief.writer import brief_dir

CHROME = os.getenv("ONS_CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
PRINTER = os.getenv("ONS_PRINTER")                       # None → system default destination
COLOR_MODEL = os.getenv("ONS_PRINT_COLOR", "Mono")       # "RGB" for colour
DEFAULT_PRINT_AT = "05:00"                               # override with ONS_PRINT_AT
DEFAULT_PRINT_UNTIL = "06:00"                            # override with ONS_PRINT_UNTIL
RETRY_EVERY_S = 600                                      # --scheduled: look again every 10 minutes
PAPER = "Letter"
FIT_STEPS = (1.0, 0.94, 0.88, 0.82, 0.76)   # zoom levels tried to fit one page

CSS = """
@page { size: letter; margin: 0.45in 0.5in; }
* { box-sizing: border-box; }
body { margin: 0; color: #111; font-family: Georgia, "Times New Roman", serif; font-size: 9.6pt; line-height: 1.32; }
.banner { border: 1.5pt solid #111; padding: 5pt 8pt; margin-bottom: 8pt; font-family: Helvetica, Arial, sans-serif; font-size: 8.5pt; }
.banner b { letter-spacing: .08em; }
.notice { border-top: .75pt solid #111; border-bottom: .75pt solid #111; padding: 3pt 0; margin: 4pt 0 6pt; font-family: Helvetica, Arial, sans-serif; font-size: 8pt; }
.masthead { text-align: center; border-bottom: 3pt double #111; padding-bottom: 4pt; }
.masthead h1 { font-family: "Baskerville", "Didot", Georgia, serif; font-size: 40pt; font-weight: 700; margin: 0; letter-spacing: .01em; }
.motto { font-style: italic; font-size: 10pt; margin-top: 1pt; }
.dateline { display: flex; justify-content: space-between; border-bottom: 0.75pt solid #111; padding: 3pt 0;
            font-family: Helvetica, Arial, sans-serif; font-size: 7.5pt; letter-spacing: .1em; text-transform: uppercase; }
.lead { font-family: "Baskerville", Georgia, serif; font-size: 25pt; line-height: 1.08; font-weight: 700; text-align: center;
        margin: 9pt 0 8pt; padding-bottom: 8pt; border-bottom: 0.75pt solid #111; }
.columns { column-count: 3; column-gap: 16pt; column-rule: 0.5pt solid #999; column-fill: balance; }
.section { margin: 0 0 7pt; }
.kicker { break-after: avoid; }
.kicker { font-family: Helvetica, Arial, sans-serif; font-size: 7.5pt; font-weight: 700; letter-spacing: .14em; text-transform: uppercase;
          border-top: 2pt solid #111; border-bottom: 0.5pt solid #111; padding: 2pt 0; margin: 0 0 5pt; }
.item { break-inside: avoid; margin: 0 0 7pt; }
.item h3 { font-family: Georgia, serif; font-size: 11.5pt; line-height: 1.15; margin: 0 0 2pt; font-weight: 700; }
.item p { margin: 0; text-align: justify; hyphens: auto; }
.src { font-style: italic; font-size: 7.5pt; color: #444; margin-top: 1.5pt; }
.tip { border: 1pt solid #111; padding: 5pt 7pt; }
.tip .kicker { border-top: 0; margin-top: 0; }
.sec-lead { border: 2pt solid #111; padding: 4pt 8pt; margin: 6pt 0 0; text-align: center;
            font-family: Helvetica, Arial, sans-serif; font-size: 12pt; font-weight: 700; }
.secretary { display: flex; gap: 14pt; border-bottom: 0.75pt solid #111; padding: 0 0 6pt; margin: 0 0 8pt;
             font-family: Helvetica, Arial, sans-serif; font-size: 8pt; line-height: 1.3; }
.secretary > div { flex: 1; }
.secretary .kicker { margin-bottom: 3pt; }
.secretary ul { list-style: none; margin: 0; padding: 0; }
.secretary li { margin: 0 0 1.5pt; padding-left: 9pt; text-indent: -9pt; }
.secretary .critical { font-weight: 700; }
.secretary .trivia, .secretary .nice_to_know { color: #333; }
.secretary .trivia { font-style: italic; }
.secretary .more { color: #555; font-style: italic; }
.foot { margin-top: 6pt; border-top: 0.75pt solid #111; padding-top: 3pt; text-align: center;
        font-family: Helvetica, Arial, sans-serif; font-size: 6.5pt; color: #555; letter-spacing: .08em; }
"""


def _e(text: Any) -> str:
    return html.escape(str(text or ""))


def _source(link: str | None) -> str:
    if not link:
        return ""
    host = urlsplit(link).netloc.lower()
    return re.sub(r"^www\.", "", host)


def edition_number(day: str) -> int:
    """Vol. 1, No. N: how many editions have been saved up to and including this day."""
    return sum(1 for p in brief_dir().glob("????-??-??.json") if p.stem <= day) or 1


def calendar_notice(day: date) -> str:
    """'Calendar unavailable today: ...' when the morning's calendar sync didn't succeed."""
    import sys
    scripts = str(Path(__file__).resolve().parents[2] / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from calendar_export import read_status
    status = read_status(day)
    if status.get("ok"):
        return ""
    msg = status.get("message") or "Calendar unavailable today."
    return msg if msg.startswith("Calendar unavailable") else f"Calendar unavailable today: {msg}."


MARK = {"critical": "■", "important": "●", "nice_to_know": "○", "trivia": "·"}


def secretary_sheet(day: date) -> dict[str, Any] | None:
    """The secretary's saved day sheet (secretary/sheet.py), or None before it existed."""
    try:
        from secretary import sheet
        return sheet.load(day)
    except Exception:
        return None


def secretary_html(day: date) -> tuple[str, str]:
    """(lead bar, Today / This Weekend / Coming Up strip) for the paper. Critical lines are bold."""
    s = secretary_sheet(day)
    if not s:
        return "", ""
    lead = "".join(f'<div class="sec-lead">■ {_e(h["text"])}</div>' for h in s.get("lead", []))

    def li(tier: str, text: str) -> str:
        return f'<li class="{_e(tier)}">{MARK.get(tier, "·")} {_e(text)}</li>'

    cells = []
    today = [li(h["tier"], h["text"]) for h in s.get("today", [])]
    if today:
        cells.append(("Today", today))
    if s.get("weekend"):
        cells.append(("This Weekend", [li(e["tier"], f'{e["label"][:3]}{" " + e["time"] if e["time"] else ""} · {e["title"]}')
                                       for e in s["weekend"]]))
    coming = s.get("coming_up", [])
    if coming:
        rows = [li(e["tier"], f'{e["label"]}{" " + e["time"] if e["time"] else ""} · {e["title"]}')
                for e in coming[:PAPER_COMING_UP_MAX]]
        if len(coming) > PAPER_COMING_UP_MAX:
            rows.append(f'<li class="more">+{len(coming) - PAPER_COMING_UP_MAX} more on the website</li>')
        cells.append(("Coming Up", rows))
    strip = ""
    if cells:
        strip = '<section class="secretary">' + "".join(
            f'<div><div class="kicker">{name}</div><ul>{"".join(rows)}</ul></div>' for name, rows in cells
        ) + "</section>"
    return lead, strip


PAPER_COMING_UP_MAX = 8


def render_html(result: dict[str, Any], zoom: float = 1.0) -> str:
    ed = result["edition"]
    d = date.fromisoformat(ed["date"])
    banner = ""
    if result.get("status") != "published":
        banner = ('<div class="banner"><b>NEEDS REVIEW</b> · this edition failed its checks; '
                  "facts may be off. Printed on request.</div>")
    parts = []
    for s in ed["sections"]:
        items = []
        for it in s["items"]:
            src = _source(it.get("link"))
            items.append(f'<div class="item"><h3>{_e(it["headline"])}</h3><p>{_e(it["body"])}</p>'
                         + (f'<div class="src">{_e(src)}</div>' if src else "") + "</div>")
        cls = "section tip" if s["name"] == "Tip of the Day" else "section"
        parts.append(f'<div class="{cls}"><div class="kicker">{_e(s["name"])}</div>{"".join(items)}</div>')
    cal = calendar_notice(d)
    notice = f'<div class="notice"><b>{_e(cal)}</b></div>' if cal else ""
    sec_lead, sec_strip = secretary_html(d)
    scores = (result.get("evaluation", {}).get("judge") or {}).get("scores") or {}
    foot = (f"Written {result.get('generated_at', '')[:16].replace('T', ' ')} · "
            f"{result.get('revisions', 0)} revision(s) · "
            + " · ".join(f"{k.replace('_', ' ')} {v}/5" for k, v in scores.items()))
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>ONS Morning Edition {_e(ed['date'])}</title>
<style>{CSS} html {{ zoom: {zoom}; }}</style></head><body>
{banner}
<header class="masthead"><h1>The ONS Morning Edition</h1><div class="motto">{_e(ed['masthead_tagline'])}</div></header>
<div class="dateline"><span>Vol. 1 · No. {edition_number(ed['date'])}</span>
<span>{d.strftime('%A, %B')} {d.day}, {d.year}</span><span>Printed for one</span></div>
{notice}
{sec_lead}
<div class="lead">{_e(ed['lead_headline'])}</div>
{sec_strip}
<main class="columns">{''.join(parts)}</main>
<div class="foot">{_e(foot)}</div>
</body></html>"""


def to_pdf(page: str, pdf_path: Path) -> Path:
    """Render HTML to PDF with headless Chrome, using a throwaway profile so an
    open Chrome window is never touched."""
    if not Path(CHROME).exists():
        raise RuntimeError(f"Chrome not found at {CHROME}; set ONS_CHROME.")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "edition.html"
        src.write_text(page, encoding="utf-8")
        subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
             f"--user-data-dir={tmp}/profile", "--no-pdf-header-footer",
             f"--print-to-pdf={pdf_path}", src.as_uri()],
            check=True, capture_output=True, timeout=90,
        )
    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        raise RuntimeError("Chrome produced no PDF.")
    return pdf_path


def pdf_pages(pdf_path: Path) -> int:
    return len(re.findall(rb"/Type\s*/Page[^s]", pdf_path.read_bytes()))


def send_to_printer(pdf_path: Path, title: str, printer: str | None = PRINTER) -> str:
    cmd = ["lp", "-t", title, "-o", f"media={PAPER}", "-o", f"ColorModel={COLOR_MODEL}"]
    if printer:
        cmd += ["-d", printer]
    out = subprocess.run(cmd + [str(pdf_path)], check=True, capture_output=True, text=True, timeout=60).stdout
    m = re.search(r"request id is (\S+)", out)
    return m.group(1) if m else out.strip()


def _env_time(var: str, default: str) -> dt_time:
    try:
        return dt_time.fromisoformat(os.getenv(var, default).strip())
    except ValueError:
        return dt_time.fromisoformat(default)


def print_at() -> dt_time:
    """ONS_PRINT_AT (HH:MM, default 05:00): automatic printing waits until then."""
    return _env_time("ONS_PRINT_AT", DEFAULT_PRINT_AT)


def print_until() -> dt_time:
    """ONS_PRINT_UNTIL (HH:MM, default 06:00): no automatic printing after this."""
    return _env_time("ONS_PRINT_UNTIL", DEFAULT_PRINT_UNTIL)


def print_edition(path: Path, *, auto: bool = False, force: bool = False, pdf_only: bool = False,
                  printer: str | None = PRINTER, today: date | None = None,
                  now: datetime | None = None) -> dict[str, Any]:
    """Make the PDF and (maybe) print it. Returns what happened; records it in the JSON.

    auto (launchd at 5:00 and the end of daily_sync): weekdays only, published
    only, and not before ONS_PRINT_AT. Whichever runs first after that time
    prints; printed_at stops the other.
    """
    result = json.loads(path.read_text())
    day = date.fromisoformat(result["date"])
    if result.get("status") != "published" and (auto or not force):
        return {"printed": False, "reason": f"edition is {result.get('status')}; not printed"}
    if auto and (today or (now.date() if now else None) or today_local()).weekday() >= 5:
        return {"printed": False, "reason": "weekend: automatic printing is weekdays only"}
    if auto and not force and (now or now_local()).time() < print_at():
        return {"printed": False,
                "reason": f"before {print_at().strftime('%H:%M')}; the scheduled print job will print it"}
    if auto and not force and (now or now_local()).time() > print_until():
        return {"printed": False,
                "reason": f"after {print_until().strftime('%H:%M')}; automatic printing window is closed"}
    if result.get("printed_at") and not force and not pdf_only:
        return {"printed": False, "reason": f"already printed {result['printed_at']} (job {result.get('print_job')})"}

    pdf = path.with_suffix(".pdf")
    for zoom in FIT_STEPS:              # one sheet of paper: shrink a step at a time until it fits
        to_pdf(render_html(result, zoom), pdf)
        if pdf_pages(pdf) == 1:
            break
    outcome = {"printed": False, "pdf": str(pdf), "pages": pdf_pages(pdf)}
    if pdf_only:
        return {**outcome, "reason": "PDF only"}
    job = send_to_printer(pdf, f"ONS Morning Edition {day}", printer)
    result.update(printed_at=now_local().isoformat(timespec="seconds"), print_job=job)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return {**outcome, "printed": True, "job": job}


# ── the 5:00 launchd job ─────────────────────────────────────────────────────

def print_log() -> JsonlLog:
    return JsonlLog("brief", "print_log.jsonl")


def _load_today(day: date) -> dict[str, Any] | None:
    """Today's edition if it exists, is complete JSON, and really is today's."""
    path = brief_dir() / f"{day.isoformat()}.json"
    try:
        result = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None                                   # not there yet, or still being written
    return result if result.get("date") == day.isoformat() else None


def review_note(day: date, result: dict[str, Any]) -> str:
    lead = (result.get("edition") or {}).get("lead_headline", "(no headline)")
    problems = (result.get("evaluation") or {}).get("problems") or []
    lines = [f"ONS MORNING BRIEF — {day.isoformat()}: needs review, not printed.",
             f"Lead: \"{lead}\" ({result.get('revisions', '?')} revisions)."]
    if problems:
        lines.append(f"Still flagged: {problems[0][:200]}" + (f" (+{len(problems) - 1} more)" if len(problems) > 1 else ""))
    lines.append(f"Read it in data/brief/{day.isoformat()}.md; print with "
                 f"`python -m agents.morning_brief.print_edition --date {day.isoformat()} --force`.")
    return "\n".join(lines)


def _slack_note(text: str) -> bool:
    from dotenv import load_dotenv
    from checkin.post_slack import ENV_VAR, post
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    url = os.getenv(ENV_VAR, "").strip()
    return bool(url) and post(text, url).ok


def scheduled_print(day: date | None = None, *, now=now_local, sleep=None,
                    notify=_slack_note, every_s: int = RETRY_EVERY_S) -> dict[str, Any]:
    """Print today's edition between ONS_PRINT_AT and ONS_PRINT_UNTIL (5:00–6:00).

    Missing: look again every 10 minutes; at the cutoff, skip and log it.
    needs_review: never printed; one short note to the check-in Slack channel.
    Every outcome is logged to data/brief/print_log.jsonl.
    """
    import time
    sleep = sleep or time.sleep
    day = day or now().date()
    cutoff = datetime.combine(day, print_until(), tzinfo=now().tzinfo)

    def done(outcome: str, **extra) -> dict[str, Any]:
        rec = {"date": day.isoformat(), "at": timestamp(), "outcome": outcome, **extra}
        print_log().append(rec)
        print(f"{day}: {outcome} {extra or ''}".rstrip())
        return {"printed": outcome == "printed", **rec}

    while True:
        result = _load_today(day)
        if result is not None:
            status = result.get("status")
            if status == "needs_review":
                already = any(r.get("date") == day.isoformat() and r.get("outcome") == "needs_review_noted"
                              for r in print_log().rows())
                if already:
                    return done("needs_review_already_noted")
                sent = notify(review_note(day, result))
                return done("needs_review_noted" if sent else "needs_review_note_failed")
            if status != "published":
                return done("skipped_status", status=status)
            out = print_edition(brief_dir() / f"{day.isoformat()}.json", auto=True, today=day, now=now())
            return done("printed" if out["printed"] else "not_printed", job=out.get("job"), reason=out.get("reason"))
        if now() >= cutoff:
            return done("skipped_no_edition", reason=f"no edition for {day} by {print_until().strftime('%H:%M')}")
        sleep(min(every_s, max(1.0, (cutoff - now()).total_seconds())))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--date", type=date.fromisoformat, help="edition date (default: today)")
    p.add_argument("--file", type=Path, help="a saved edition JSON anywhere (e.g. a fixture run)")
    p.add_argument("--auto", action="store_true", help="daily_sync mode: weekdays only, published only")
    p.add_argument("--force", action="store_true", help="print again, or print a needs_review edition")
    p.add_argument("--pdf-only", action="store_true", help="make the PDF next to the JSON; don't print")
    p.add_argument("--printer", default=PRINTER, help="CUPS queue (default: ONS_PRINTER or system default)")
    p.add_argument("--scheduled", action="store_true",
                   help="the 5:00 launchd job: today's edition only, retry every 10 min until 06:00, "
                        "needs_review → Slack note instead of printing")
    args = p.parse_args(argv)
    if args.scheduled:
        scheduled_print()
        return 0

    path = args.file or brief_dir() / f"{(args.date or today_local()).isoformat()}.json"
    if not path.exists():
        # Not an error at 5:00 if the sync is still running: it prints when it finishes.
        print(f"No edition at {path} yet")
        return 0 if args.auto else 1
    try:
        json.loads(path.read_text())
    except json.JSONDecodeError:
        print(f"Edition at {path} is still being written")
        return 0 if args.auto else 1
    out = print_edition(path, auto=args.auto, force=args.force, pdf_only=args.pdf_only, printer=args.printer)
    if out.get("pdf"):
        print(f"PDF: {out['pdf']} ({out['pages']} page{'s' if out['pages'] != 1 else ''})")
    print(f"printed, job {out['job']}" if out["printed"] else f"not printed: {out['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
