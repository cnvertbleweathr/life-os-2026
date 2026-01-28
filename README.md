# Life OS 2026

**Life OS 2026** is a data-driven personal operating system designed to turn intent into execution across professional, physical, financial, and personal domains—using the same principles that power modern analytics platforms.

At its core, Life OS treats *life as a system*: observable, measurable, automatable, and continuously improvable.

This repository serves both as a **living operating system** and as a **proving ground for applied data engineering, automation, and agent-assisted workflows**.

---

## What This Project Is

Life OS 2026 is not a habit tracker.

It is a **modular analytics platform** that:
- Ingests data from multiple real-world sources
- Normalizes and models that data
- Computes metrics, progress, and leading indicators
- Produces daily and weekly artifacts for reflection and decision-making
- Uses automation and AI agents to reduce cognitive overhead

The design mirrors modern data stack principles: separation of concerns, idempotent pipelines, reproducibility, and observability.

---

## Core Design Principles

### 1. Separation of Concerns
The system explicitly separates:
- **Intent** → goals and targets (`goals/2026.yaml`)
- **Facts** → raw and processed data (`data/`)
- **Logic** → deterministic transformations and metrics (`scripts/`)

This allows goals to evolve without rewriting logic, and logic to evolve without corrupting historical data.

---

### 2. Automation Over Willpower
If a behavior or metric matters, it should be:
- Automatically ingested
- Automatically computed
- Automatically surfaced

Manual effort is treated as technical debt.

---

### 3. Analytics-First Thinking
Every domain is treated like an analytics problem:
- Define metrics
- Track progress vs targets
- Surface deltas and trends
- Optimize based on evidence, not intuition

---

### 4. Agent-Assisted Operations
Life OS is intentionally designed to integrate with AI agents:
- Content generation (e.g., Spotify playlist artwork + historical context)
- Insight synthesis
- Future-state planning
- System evolution itself

This repository demonstrates how humans and agents can collaborate inside a structured system.

---

## What It Tracks (Current Scope)

### 🎯 Professional
- Career goals and milestones
- Output-based metrics (e.g., migrations completed, revenue influenced)
- Reading goals and learning velocity
- GitHub activity and technical consistency

### 💪 Fitness & Health
- CrossFit attendance and performance (SugarWOD ingestion)
- Running volume and goal tracking
- Strength benchmarks
- Meditation and recovery habits

### 🎧 Personal & Lifestyle
- Spotify listening analytics
- Daily “Daily 10” playlist generation with:
  - Algorithmic track selection
  - AI-generated cover art
  - Historically contextualized descriptions
- Reading (fiction and non-fiction)
- Date nights and family presence signals

### 💰 Financial
- Savings and investment targets
- Long-term consistency metrics
- Guardrails rather than micromanagement

---

## Architecture Overview

```text
life-os-2026/
├── goals/                  # Declarative intent (YAML)
│   └── 2026.yaml
│
├── data/                   # Source-of-truth facts
│   ├── daily/              # Daily snapshots & history
│   ├── spotify/
│   ├── fitness/
│   ├── calendar/
│   └── ...
│
├── scripts/                # Deterministic logic
│   ├── daily_sync.py
│   ├── spotify_daily10_playlist.py
│   ├── spotify_daily10_decorate.py
│   ├── *_metrics.py
│   └── *_ingest.py
│
├── requirements.txt
└── README.md
```

Key characteristics:
- **Idempotent runs** — scripts can be safely re-run without corrupting state
- **Append-only history** — past data is never mutated, only extended
- **Deterministic logic** — the same inputs always produce the same outputs
- **Explicit state** — no hidden state outside the repository
- **Version-controlled behavior** — changes to logic are reviewable and auditable

---

## Example Workflow

A typical daily execution looks like this:

1. **Ingest new data**
   - Spotify listening history
   - Fitness and training data
   - Calendar and lifestyle signals
   - Other domain-specific sources

2. **Compute metrics**
   - Year-to-date totals
   - Progress vs declared goals
   - Rates, streaks, and leading indicators

3. **Persist history**
   - Update append-only daily history tables
   - Write per-day snapshot artifacts
   - Maintain long-running CSV-based fact tables

4. **Generate artifacts**
   - Human-readable daily summaries
   - Machine-readable metric outputs
   - Audit logs for traceability

5. **Optional agent-assisted enrichment**
   - AI-generated Spotify playlist artwork
   - Historically contextualized descriptions
   - Content enrichment without manual effort

Every step is:
- Scriptable
- Observable
- Repeatable
- Safe to automate

---

## Applied AI in Practice

Life OS does not use AI as a novelty layer.

AI is treated as a **co-processor** that:
- Operates on structured inputs
- Produces bounded, testable outputs
- Enhances experience without replacing deterministic logic

Examples include:
- Generating historically grounded playlist cover art
- Producing concise, trivia-oriented contextual summaries
- Assisting with system evolution and refactoring

The system is intentionally designed so AI **adds value without introducing fragility**.

---

## Why This Matters (Professionally)

This project demonstrates real-world capability in:

- **Systems thinking** — modeling life domains as interoperable systems
- **Data engineering** — ingestion, normalization, metrics, history
- **Analytics design** — progress tracking, goal modeling, leading indicators
- **Automation-first mindset** — reducing friction and cognitive load
- **Responsible AI usage** — constrained, purposeful, production-oriented

It reflects how I approach complex environments:
> Define the system → measure what matters → automate relentlessly → iterate based on evidence.

This is the same mental model required to build and operate modern analytics platforms at scale.

---

## Future Direction

Life OS is intentionally extensible.

Planned and exploratory directions include:
- Deeper agent orchestration across domains
- Natural-language querying of personal metrics
- Predictive signals and anomaly detection
- Snowflake-native experimentation for modeling and storage
- Visualization layers focused on reflection and storytelling

The architecture supports growth without rewrites.

---

## Final Note

Life OS 2026 is both:
- **Deeply personal**, and
- **Professionally rigorous**

It is a living example of how data, automation, and thoughtful system design can make consistent progress the default outcome — not through motivation, but through structure.

This repository represents how I think, build, and operate.
