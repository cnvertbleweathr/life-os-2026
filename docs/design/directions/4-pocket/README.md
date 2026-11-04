# 4 · Pocket: phone-first, one tint per area

**Idea.** The owner's daily touches happen on a phone, so design for the thumb and let the desktop be a wider phone. Home opens with **To do today**: four habit toggles and a Start check-in button, in 56px rows. Below that, each life area gets its own pale tile with the sum inside the card that explains it: running blue, CrossFit amber, reading teal, CFB sand, each in the dark ink of its own hue. The copy carries the coach voice ("Running's on pace; CrossFit needs a class this week"). On the slate, picks become big, readable slips: the pick and line at 22px, the kick time as a chip, and one plain-language reason.

| | |
|---|---|
| **Palette** | Ground `#f3f5f7`, white cards. Area tints with their own ink: run `#dcefff`/`#0a3a80`, lift `#fdeed2`/`#693c00`, read `#d7f2ec`/`#0b4840`, habits `#e2f4d9`/`#1f4a12`, edge `#eeebe3`/`#3a3322`. Wins `#22603a` with a plus sign; losses in quiet ink, not red. |
| **Type** | Manrope 500/600/700 only. 28px title, 20px card titles, 16px body, sums at 34px, tabular figures. |
| **Density** | Low to medium. A 20px radius stepping to 12 and 8 inside, 24px gaps, 56–72px rows. |
| **Motion** | Toggles slide their knob in 150ms ease-out (the one place motion helps: it confirms the tap). Press `scale(.97)` on buttons. Nothing animates on load. Reduced motion turns it all off. |
| **Shell** | Desktop: a light sidebar with only two groups ("Your year", "Fun"), with Music and Gizz merged. Phone: a bottom bar of Today, Year, Capture, Picks, More. Picks earns a tab because it's a Saturday ritual. |

**Signature element:** *The Today stack:* toggles you can hit with a thumb, in the top 60% of the phone screen, before any stats.

**How it fixes the top critique problems**

1. *Trust:* the CFB tile shows live units only. The season card names the backtest as "the model's history, not this season".
2. *Coaching:* every tile's sentence is a coach line with a next action ("Finish the next by Nov 22 to catch up").
3. *Legibility:* 14px is the smallest text, and every tint pairs with its own dark ink at over 7:1.
5. *Phone:* the actions come first; no row is shorter than 44px; picks don't truncate (names wrap on slips).
6. *IA:* six nav items in two groups; Music and King Gizzard are merged.
8. *Machine voice:* no signal keys at all, just one sentence of reasoning per pick.

**Trade-offs.** It's the least dense, so the desktop shows less per screen and power use (sorting, comparing picks) is weaker. The pastel tiles are friendly, but the most "consumer" in tone. The taste gate flags the tinted icon squares in the Today list (kept to tie each row to its area) and the sand CFB tint as near-cream.

Files: `home.html`, `cfb.html`, `style.css`; screenshots `*-1440.png`, `*-390.png`.
