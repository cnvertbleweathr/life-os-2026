# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

One primary user: the owner, Karey, reviewing their own life data and CFB betting edge. They use it every day in two settings:

- **At the desk, mornings:** a sit-down check of the brief, habits, goals and fitness, and the CFB slate in season.
- **On the phone, through the day and on game days:** quick Capture entries, check-ins and habit logs, plus live scores and team news from the ticker.

There is a small secondary audience: friends, or someone seeing it as a portfolio piece, who are occasionally shown narcisystem.com. They see the owner's product. Nothing is designed for them, and no flow is built for a stranger's first visit.

## Product Purpose

ONS (Operating Narcisystem) treats life as a system that can be observed, measured and improved. It pulls personal data (Strava, Hardcover, SugarWOD, Letterboxd, King Gizzard shows and listening, habits, check-ins, goals) and CFB data through a local data stack. From that it answers three questions: **What is happening? Why does it matter? What should I do next?**

Success means the owner knows, at a glance, whether they're on pace with what they said they'd do, and spends less mental effort working that out. On the CFB side, success means a trustworthy weekly slate of model picks with honest grading.

## Positioning

ONS is built for exactly one person, around their own goals file (`goals/2026.yaml`), their own data sources and their own betting model. No generic habit tracker or sportsbook tool can say that. The CFB edge comes from a documented, walk-forward-validated model that looks for gaps between PPA efficiency and the spread (`docs/SYSTEM_EXPLAINER.md`). It is a real system, not a handicapper's opinion.

## Operating Context

- Live at narcisystem.com through a Cloudflare Tunnel from a Mac mini. The Next.js UI runs on :3000 and the FastAPI read layer on :8000.
- The data runs DLT → DuckDB → dbt → FastAPI → Next.js, with a nightly sync. The UI never writes to the warehouse. Inputs (habits, check-ins, Capture) are appended to JSONL logs and loaded overnight, so data entered in the UI may not appear in the marts until the next sync.
- The AI layer writes the morning brief, the weekly recap and CFB narratives. OpenClaw (single-shot Claude prompts) is being replaced by LangGraph agents that call tools and have evals (`ROADMAP.md`).
- Rituals: the morning brief, the Sunday weekly recap, the daily check-in, and the CFB slate during the season.

## Capabilities and Constraints

- Life routes: Home, Habits, Fitness, Reading, Goals, Check-in, Capture. Entertainment routes: Music, King Gizzard, Sports. Edge route: CFB Betting.
- The top ticker shows the owner's scores, team news and headlines from ESPN.
- Every surface is a working surface (dashboards, trackers, forms, slates). Briefs and reviews are the reading surfaces.
- Daily use rules out slow or decorative interactions on high-frequency surfaces.
- Data can be missing, stale or untracked. The UI has to show that honestly instead of hiding it.

## Brand Commitments

- **Name:** ONS, short for "Operating Narcisystem". The pun is intentional.
- **Voice:** coach-like. Direct and honest about pace and misses, but pushes toward the goal rather than just reporting it. It never fakes progress, never hides a miss, and never uses empty cheerleading. Where the facts call for it, the README's bluntness is still in character.
- **Mark:** the globe mark in `web/components/ui/icons.tsx`.

## Evidence on Hand

- The owner's real data in the local DuckDB warehouse, and goals in `goals/2026.yaml`.
- CFB model backtest numbers, as documented in `docs/SYSTEM_EXPLAINER.md` (2021–2025, v3 walk-forward). Quote them from that document only, and never round them up or restate them more strongly.
- There are no testimonials, other users or press. Never invent them.

## Product Principles

1. **Answer the three questions.** Each surface should make plain what's happening, why it matters, and what to do next, in that order.
2. **Honest over flattering.** Show pace, misses and gaps in the data as they are. Being on track has to be earned.
3. **Glanceable first, deep on demand.** The headline numbers read in seconds; the detail sits one level down.
4. **Low-friction input.** Logging a habit, check-in or capture should take seconds on a phone.
5. **One owner, one system.** Optimize for the owner's real routines, not for imagined users.
