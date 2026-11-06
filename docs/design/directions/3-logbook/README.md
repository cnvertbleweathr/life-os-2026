# 3 · Logbook: the week is the unit

**Idea.** Days are noisy and years are abstract; a week is the span you can steer. Home becomes **the week**: a strip with the days across (Mon–Sun) and your lanes down the side (running, CrossFit, habits, check-in, plans, CFB), with today marked by a 1px forest line. Missed things show as dashed outlines ("Not logged", "Due"), and Saturday's picks sit in the CFB lane as an outlined block. The CFB page reuses the idea for Saturday itself: six games placed on a 9 am–midnight kickoff strip, then the ruled table.

| | |
|---|---|
| **Palette** | Frame `#eef2ee` (a green-grey from the forest), sheet `#fff`, borders `#e3e7e3`. Ink `#141714`, muted `#5a605a`. Data hue: forest lifted to `#1f6b46` (5.9:1 on white), with a pale `#e4efe8` for filled marks. Status pills only for on track, behind, out of reach and not wired. |
| **Type** | IBM Plex Sans 400/500/600 (22px title, 16px card titles, 14px body). IBM Plex Mono for figures in tables and marks only. |
| **Density** | Medium. A tinted L-frame (sidebar plus 48px top bar), with the work on a white sheet inset 8px, 16px corners, no shadow. 24px gaps. |
| **Motion** | Press and hover only. The week strip and kickoff strip are static. No live-pulse dots. |
| **Shell** | The top bar holds a breadcrumb, a centred **Ask the system ⌘K** field (the existing command palette, finally prominent) and the sync status. Tabs use a 2px forest underline. On the phone the frame drops away; the week strip scrolls sideways inside its own card. |

**Signature element:** *The week strip.* Every daily input and plan sits on one grid, so "what's left this week" is visible at a glance. It answers the brief's "what should I do next" with the empty cells themselves.

**How it fixes the top critique problems**

1. *Trust:* "last 7 days" (10.2 mi) is labelled distinctly from the calendar week (one run so far). Goals carry an explicit "Not wired" state, and "Out of reach" is explained (9.2 a week against a 1.9 average).
2. *Coaching:* the strip's empty cells and the "Goals on the clock" table (Needs, State) say what's left.
4. *States:* "Not logged" and "Due" are designed states, not blanks.
5. *Phone:* the habits checklist and Capture are cards on Home. The primary action ("Log today's habits") is in the title row.
6. *IA:* one week view replaces Home's three unrelated cards; ⌘K search moves into the frame.
7. *Density:* the kickoff strip plus the table show the slate in one screen; Season and week 9 sit beside it.
10. *Charts:* the strips have real time axes (days, hours).

**Trade-offs.** It needs a new data shape (events per day per lane) that the API doesn't serve yet. The week strip is wide, so the phone has to scroll it sideways. It passed the taste gate with 0 failures and 0 warnings.

Files: `home.html`, `cfb.html`, `style.css`; screenshots `*-1440.png`, `*-390.png`.
