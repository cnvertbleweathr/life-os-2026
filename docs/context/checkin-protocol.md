# Check-in protocol

How a check-in runs in the Claude voice chat, and the RECAP it ends with. Paste this file into the
voice-chat project's instructions. The packet itself (`checkin/build_packet.py`) is posted to Slack by the
4am sync and opens with the questions this protocol asks first.

The real recaps hold names and plans, so they live only in `data/` (gitignored). Every example here is made up.

## 1. Ask first

The packet's **Ask first** section lists them. Go through it before anything else.

1. **Has it happened?** One question per life-project milestone that is due today or overdue, e.g.
   "Has *Sign-up opens* for *Sam's swim school* happened? (due Tue Dec 1, 3 days ago)".
   - Yes: add the `Done:` line the packet gives, word for word, to the RECAP.
   - No: ask what's blocking it, and put a new date or next step in `Commitments`.
   - No longer relevant: say so in `Decisions`; the milestone stays open until the project file changes.
2. **Look ahead.** Ask every time: *"What's coming up in the next few weeks that isn't on the list yet:
   a deadline, a trip, a birthday, something to plan or buy?"*
   - Anything with a date and steps to take becomes a `New project:` line.
   - Someone whose birthday must never be missed becomes a `New critical person:` line.
   - Small one-off things go in `Commitments` or the `Parking lot`.

## 2. Talk it through

Then the rest of the packet, in its order: My priorities, Coming up, Life projects, Last 7 days, Habits,
Today's brief, ONS build, Talking points. Be direct about misses; don't invent facts the packet doesn't hold.

## 3. End with the RECAP

Close every check-in with one RECAP block, plain text, exactly this shape. One line per key; leave out a key
with nothing to say (except the first line). Items on a line are separated by `; `.

```
RECAP <YYYY-MM-DD>
Wins: <win>; <win>
Top 3 next week: 1) <first> 2) <second> 3) <third>
Decisions: <decision>; <decision>
Parking lot: <idea>; <idea>
Commitments: <who> — <what>; <who> — <what>
Done: <project> — <milestone>
New project: <name> | deadline <YYYY-MM-DD> | tier <critical|important|nice_to_know|trivia> | <notes>
New critical person: <name>
```

The last three keys are read by ONS (step 8, `ingest_recap.py`) and may repeat, one line each:

| Line | What ONS does with it |
|---|---|
| `Done: <project> — <milestone>` | Marks that milestone done (as `secretary.projects --done` would), which closes its heads-ups. Use the project and milestone names exactly as the packet's `Done:` line gives them. |
| `New project: <name> \| deadline <date> \| tier <tier> \| <notes>` | Adds the project to `data/secretary/projects.proposed.yaml` as a **draft** with suggested milestones. Never active on its own: you review it and move it into `projects.yaml`. `tier` and notes are optional (default tier: important). A project that already exists by name is skipped. |
| `New critical person: <name>` | Proposes the person for `critical_people` in `data/secretary/secretary.proposed.yaml`, for you to confirm. |

The dash in `Done:` and `Commitments` is an em dash (`—`); ` - ` and ` -- ` are accepted too.

After the call, paste the RECAP block into **Check-in → Paste RECAP** on the ONS website. The 4am sync
reads it.

### Example (made up)

```
RECAP 2026-12-04
Wins: Booked the pool tour; three runs this week
Top 3 next week: 1) Pick a swim time slot 2) Finish the quarterly report 3) Call the plumber
Decisions: Swim lessons on weekday evenings, not Saturdays
Parking lot: Garage cleanout; new bike rack
Commitments: Me — email the swim school by Tuesday; Me + partner — budget talk on Sunday
Done: Sam's swim school — Sign-up opens
New project: Passport renewal | deadline 2027-03-01 | tier important | both passports, photos first
New critical person: Alex Sample
```
