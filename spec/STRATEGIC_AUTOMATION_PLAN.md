# Strategic Automation Plan — Personal Work Automation

**Date:** 2026-02-16
**Working group:** System Analyst + Chief Architect + Technical Lead + Executive Assistant
**Method:** 3-step synthesis (Professor → Inventor → Synthesis)

---

## Thinking Process

### Step 1: Professor (pedantic analysis of current state)

**What we know for certain:**

1. The user operates across 3 work domains:
   - **D1 — Team management:** coordinating people, delegating tasks, tracking commitments, running meetings, processing meeting outcomes
   - **D2 — Corporate deals / presales:** lead management, proposal preparation (КП), deal tracking, partner communications, investor relations (YC-1: 25M RUB)
   - **D3 — Personal operations:** email triage, calendar management, task lifecycle (GTD), contact/people management, decision logging

2. The current Agentura system covers:
   - GTD task lifecycle (capture/move/done/waiting) — **implemented, 102 tests**
   - Deterministic day planning (3 variants) — **implemented**
   - Knowledge consolidation (people, decisions, FTS5) — **implemented**
   - Manual busy blocks with merge-on-read — **implemented**
   - Weekly review — **implemented**
   - CalDAV/IMAP sync — **designed (ADR-10, R1-R4), not yet live**
   - Task ingestion from meetings/dialogues/email — **designed (ADR-11, I1-I6), runtime implemented**
   - 11 agent roles defined — **operational in AGENTS.md**

3. The user's daily information flow:
   - **Inbound:** email (~50-100/day), calendar events (5-15/day), Telegram messages, meeting notes, partner/investor communications
   - **Processing:** triage (what needs action?), extraction (what's the task?), routing (who does it?), scheduling (when?)
   - **Outbound:** responses, proposals (КП), delegation instructions, follow-ups, meeting agendas

4. Known pain points (inferred from architecture decisions):
   - Manual task capture is the only input path (before ADR-11)
   - No automated email-to-task extraction
   - Meeting outcomes are lost if not manually captured
   - No deal/pipeline tracking
   - No delegation tracking (who owes what)
   - Calendar sync not yet operational

**What we don't know:**
- Actual email volume and response patterns
- CRM / deal management tool usage (if any)
- Team size and communication tools (Telegram groups? Slack?)
- Meeting frequency and format (Zoom? in-person? how are notes taken?)
- Current proposal (КП) workflow and tools

### Step 2: Inventor (bold vision, then constrain)

**Bold vision:** A fully autonomous personal operations system that:
- Reads all inbound channels (email, calendar, Telegram, meeting notes)
- Extracts action items, deadlines, commitments, and people
- Maintains a live deal pipeline with stage tracking
- Generates daily/weekly plans with context-aware prioritization
- Drafts responses and proposals
- Delegates to team members with follow-up tracking
- Runs with minimal human intervention (Wave 3 autonomy for routine, Wave 1 for novel)

**Practical constraints:**
- Privacy: no email body to LLM (ADR-10), credentials via env only
- Single writer: EA owns SQLite (ADR-09)
- Determinism where possible: planning stays deterministic (ADR-06)
- Incremental: each wave must deliver standalone value
- Local-first: SQLite + CLI, no cloud dependency for core operations
- Budget: LLM API costs must be predictable and controllable

### Step 3: Synthesis (what to actually build)

The synthesis follows below in the 6 deliverables. The key insight: **don't build a platform, build an expanding perimeter of automation around the user's existing workflow.** Start with observation (Wave 0), add assistance (Wave 1), then selective execution (Wave 2), and policy-based autonomy (Wave 3) only where trust is established.

---

## Deliverable 1: Job Map (карта работ)

### D1 — Team Management

| # | Job step | Current tool | Frequency | Pain level | Automatable? |
|---|----------|-------------|-----------|------------|-------------|
| 1.1 | Receive meeting notes / protocols | Manual (files, chat) | 3-5x/week | HIGH | Wave 1 (ADR-11 ingest) |
| 1.2 | Extract action items from meetings | Manual reading | 3-5x/week | HIGH | Wave 1 (LLM extractor) |
| 1.3 | Assign tasks to team members | Manual (chat/email) | Daily | MEDIUM | Wave 2 (delegation service) |
| 1.4 | Track delegation status | Mental / ad-hoc | Daily | HIGH | Wave 1 (waiting_on + ping_at) |
| 1.5 | Follow up on overdue delegations | Manual | 2-3x/week | HIGH | Wave 2 (auto-ping) |
| 1.6 | Prepare meeting agendas | Manual | 3-5x/week | MEDIUM | Wave 2 (agenda generator) |
| 1.7 | Record decisions from meetings | Manual / lost | 3-5x/week | HIGH | Wave 1 (ADR-11 + decision capture) |

### D2 — Corporate Deals / Presales

| # | Job step | Current tool | Frequency | Pain level | Automatable? |
|---|----------|-------------|-----------|------------|-------------|
| 2.1 | Track leads and opportunities | Mental / spreadsheet? | Weekly | HIGH | Wave 1 (deal entity) |
| 2.2 | Prepare proposals (КП) | Manual (docs) | 2-4x/month | MEDIUM | Wave 2 (template + LLM draft) |
| 2.3 | Track proposal status | Manual | Weekly | MEDIUM | Wave 1 (deal stages) |
| 2.4 | Investor communications (YC-1) | Email | Weekly | MEDIUM | Wave 0 (observe only) |
| 2.5 | Partner follow-ups | Manual email | 2-3x/week | HIGH | Wave 2 (auto-draft follow-up) |
| 2.6 | Revenue / pipeline reporting | Manual | Monthly | LOW | Wave 2 (query + format) |

### D3 — Personal Operations

| # | Job step | Current tool | Frequency | Pain level | Automatable? |
|---|----------|-------------|-----------|------------|-------------|
| 3.1 | Email triage (what needs action?) | Manual | Daily, 30-60 min | HIGH | Wave 1 (email ingest + classify) |
| 3.2 | Calendar review + conflict check | Manual | Daily | MEDIUM | Wave 0 (calendar sync) |
| 3.3 | Task capture from email | Manual | Daily | HIGH | Wave 1 (ADR-11 C3) |
| 3.4 | Day planning | `execas plan day` | Daily | LOW (solved) | Done (MVP) |
| 3.5 | Weekly review | `execas review week` | Weekly | LOW (solved) | Done (MVP) |
| 3.6 | Contact/people lookup | `execas people search` | Ad-hoc | LOW (solved) | Done (MVP) |
| 3.7 | Decision logging | `execas decision add` | 2-3x/week | LOW (solved) | Done (MVP) |
| 3.8 | Response drafting | Manual | Daily, 30-60 min | HIGH | Wave 2 (LLM draft) |
| 3.9 | Telegram message processing | Manual | Daily | MEDIUM | Wave 2 (Telegram channel) |

---

## Deliverable 2: Automation Backlog by Waves

### Wave 0 — Observe (read-only, zero risk)

**Goal:** System sees what the user sees. No writes, no actions, no LLM.

| ID | Item | Job refs | Depends on | Effort |
|----|------|----------|-----------|--------|
| W0-1 | Calendar sync (CalDAV → busy_blocks) | 3.2 | R1 schema, R2 connector | S (designed) |
| W0-2 | Email header sync (IMAP → emails table) | 3.1 | R1 schema, R3 connector | S (designed) |
| W0-3 | Email volume dashboard (`mail stats --since`) | 3.1 | W0-2 | XS |
| W0-4 | Meeting note file watcher (detect new files) | 1.1 | I1 schema | XS |

**Wave 0 value:** User can run `execas busy list`, `execas mail stats`, and see their operational state in one place. No risk — pure observation.

### Wave 1 — Assist (drafts, suggestions, human confirms)

**Goal:** System extracts, classifies, suggests. Human approves all writes.

| ID | Item | Job refs | Depends on | Effort |
|----|------|----------|-----------|--------|
| W1-1 | Meeting note → task drafts (LLM extract) | 1.1, 1.2, 1.7 | ADR-11 I2-I4 | M (designed) |
| W1-2 | Email → task drafts (subject + sender classify) | 3.1, 3.3 | ADR-11 I5 | M (designed) |
| W1-3 | Dialogue → task drafts (chat transcript parse) | 1.2 | ADR-11 I2-I4 | S (designed) |
| W1-4 | Delegation tracker (waiting_on + auto-remind list) | 1.4 | MVP (waiting status) | S |
| W1-5 | Deal entity + pipeline stages | 2.1, 2.3 | New ADR-12 | M |
| W1-6 | Smart weekly review (commitment progress signals) | 2.4 | W1-5 | S |
| W1-7 | Email priority scoring (subject + sender heuristics) | 3.1 | W0-2 | S |

**Wave 1 value:** Reduces manual extraction time by ~60%. All candidates go to review queue. User retains full control.

### Wave 2 — Execute with confirmation (propose → confirm → act)

**Goal:** System proposes concrete actions. User confirms with one click/command.

| ID | Item | Job refs | Depends on | Effort |
|----|------|----------|-----------|--------|
| W2-1 | Auto-create tasks above confidence threshold (0.8) | 1.2, 3.3 | W1-1, W1-2 | S (designed in ADR-11) |
| W2-2 | Delegation notification (Telegram/email to assignee) | 1.3, 1.5 | W1-4 + Telegram channel | M |
| W2-3 | Follow-up auto-draft (email response template) | 2.5, 3.8 | W0-2 + LLM | M |
| W2-4 | Meeting agenda generator (from open tasks + waiting items) | 1.6 | W1-4 | S |
| W2-5 | КП template filler (deal context → proposal draft) | 2.2 | W1-5 + LLM | L |
| W2-6 | Telegram channel ingest (C4) | 3.9 | ADR-11 + Telegram API | M |
| W2-7 | Overdue ping automation (auto-send reminder) | 1.5 | W2-2 | S |

**Wave 2 value:** Reduces action latency from hours to minutes. User reviews and confirms rather than creating from scratch.

### Wave 3 — Autonomous (policy-based, no confirmation for routine)

**Goal:** Routine operations run on policy. Novel situations escalate to human.

| ID | Item | Job refs | Depends on | Effort |
|----|------|----------|-----------|--------|
| W3-1 | Auto-triage email (known senders → known actions) | 3.1 | W1-7 + policy rules | M |
| W3-2 | Auto-delegate recurring tasks | 1.3 | W2-2 + delegation patterns | M |
| W3-3 | Auto-reschedule on conflict (within policy bounds) | 3.2 | Calendar sync + policy | L |
| W3-4 | Proactive follow-up (system sends reminder without prompt) | 1.5 | W2-7 + trust policy | S |
| W3-5 | Pipeline stage auto-advance (deal reached milestone) | 2.3 | W1-5 + signal detection | M |
| W3-6 | Multi-agent orchestration (agents coordinate without user) | All | Full autonomy policy | XL |

**Wave 3 value:** User spends <15 min/day on operational overhead (vs ~2-3 hours today). Focus shifts to creative and strategic work.

---

## Deliverable 3: Target Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                        USER INTERFACE                              │
│  CLI (execas)  ·  Telegram bot  ·  [future: web dashboard]       │
└───────────────────────┬────────────────────────────────────────────┘
                        │
┌───────────────────────┴────────────────────────────────────────────┐
│                     COMMAND LAYER                                   │
│  Typer CLI handlers · Bot command handlers · API endpoints         │
│  (all call the same service layer — no direct DB access)           │
└───────────────────────┬────────────────────────────────────────────┘
                        │
┌───────────────────────┴────────────────────────────────────────────┐
│                     SERVICE LAYER (EA single writer — ADR-09)      │
│                                                                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐             │
│  │ Task     │ │ Deal     │ │ Calendar │ │ People   │             │
│  │ Service  │ │ Service  │ │ Service  │ │ Service  │             │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐    │
│  │ Planner  │ │ Review   │ │ Busy     │ │ Ingest Pipeline  │    │
│  │ Service  │ │ Service  │ │ Service  │ │ (ADR-11)         │    │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘    │
└───────────────────────┬────────────────────────────────────────────┘
                        │
┌───────────────────────┴────────────────────────────────────────────┐
│                     LLM ISOLATION BOUNDARY                         │
│                                                                     │
│  ┌─────────────────┐  ┌──────────────┐  ┌─────────────────────┐  │
│  │ Task Extractor  │  │ Draft Writer │  │ Classifier          │  │
│  │ (extractor.py)  │  │ (email/КП)   │  │ (priority/routing)  │  │
│  └─────────────────┘  └──────────────┘  └─────────────────────┘  │
│                                                                     │
│  LLM API (Claude/GPT/local) — credentials via env var only         │
│  Privacy: no email body, no PII beyond subject+sender              │
└───────────────────────┬────────────────────────────────────────────┘
                        │
┌───────────────────────┴────────────────────────────────────────────┐
│                     DATA LAYER (SQLite — local, private)           │
│                                                                     │
│  tasks · deals · busy_blocks · emails · task_email_links          │
│  ingest_documents · task_drafts · ingest_log · sync_state         │
│  people · decisions · commitments · weekly_reviews · settings      │
└───────────────────────┬────────────────────────────────────────────┘
                        │
┌───────────────────────┴────────────────────────────────────────────┐
│                     CONNECTOR LAYER (read-only ingest)             │
│                                                                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │ CalDAV   │ │ IMAP     │ │ Telegram │ │ File     │            │
│  │ (Yandex) │ │ (Yandex) │ │ Bot API  │ │ Watcher  │            │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘            │
└────────────────────────────────────────────────────────────────────┘
```

### Architecture principles

1. **Local-first, privacy-first.** SQLite is the single source of truth. No cloud database. All data stays on the user's machine.
2. **EA single writer (ADR-09).** All writes go through the service layer. Connectors and LLM are read-only inputs.
3. **LLM isolation.** LLM calls are confined to specific modules (extractor, draft writer, classifier). All other logic is deterministic.
4. **Incremental connectors.** Each external source has an independent connector with its own sync_state cursor. Connectors are stateless — they read from external, write to local.
5. **Multi-interface convergence.** CLI, Telegram bot, and future web UI all call the same service layer. No business logic in the interface layer.

### New entities for full coverage (beyond current schema)

| Entity | Purpose | Wave |
|--------|---------|------|
| `deals` | Lead/opportunity pipeline tracking | Wave 1 (W1-5) |
| `deal_stages` | Stage history with timestamps | Wave 1 |
| `delegation_log` | Who was asked to do what, when, status | Wave 1 (W1-4) |
| `draft_responses` | LLM-generated email/message drafts | Wave 2 |
| `automation_rules` | Policy rules for Wave 3 autonomy | Wave 3 |
| `channel_configs` | Per-channel settings (Telegram group IDs, etc.) | Wave 2 |

---

## Deliverable 4: Technology Comparison

### Evaluation criteria

| Criterion | Weight | Description |
|-----------|--------|-------------|
| Privacy & data control | 25% | Local data, no cloud dependency, no PII leakage |
| Customizability | 20% | Can we shape workflows to our exact GTD model? |
| Multi-channel support | 15% | Email, calendar, Telegram, meeting notes |
| LLM flexibility | 15% | Choice of model (Claude, GPT, local), cost control |
| Operational simplicity | 15% | Setup, maintenance, debugging |
| Community & longevity | 10% | Open-source health, bus factor |

### Comparison matrix

| | **Agentura (current)** | **OpenClaw** | **n8n** | **PocketPaw** | **Codex-app paradigm** |
|---|---|---|---|---|---|
| **Architecture** | CLI + SQLite + Python services | Multi-channel AI assistant | Visual workflow builder | Desktop multi-agent hub | Human-as-orchestrator of coding agents |
| **Privacy** | Local-only SQLite, no body to LLM | Local, but sends context to LLM for all channels | Self-hosted possible, but workflows may pipe data through cloud APIs | Self-hosted, 7-layer security, local storage | Code runs on user machine; context sent to LLM |
| **Customizability** | Full (own code, own schema, own ADRs) | Plugin-based, moderate | Visual workflows, high for standard patterns, limited for novel logic | Multi-agent config, moderate | Unlimited (it's your code) |
| **Multi-channel** | CLI + CalDAV + IMAP (designed) | WhatsApp, Telegram, Discord, Slack, 50+ integrations | 400+ connectors | Telegram, Discord, Slack, WhatsApp, Web | N/A (code-centric, not user-channel-centric) |
| **LLM flexibility** | Any (env var, isolated in extractor.py) | Configurable (OpenAI, Anthropic, local) | Built-in AI nodes (OpenAI, Anthropic, etc.) | Anthropic, OpenAI, Ollama | Primarily OpenAI Codex / Claude |
| **GTD model fit** | Native (built for this) | Generic (needs extensive customization) | Can model it, but workflow-per-action overhead | Agent-based, not task-lifecycle-native | Not applicable (code tool, not ops tool) |
| **Operational simplicity** | CLI, zero infra beyond Python + SQLite | Docker + config, moderate | Docker/cloud, web UI, moderate-high | Desktop installer, moderate | IDE or terminal, minimal |
| **Maturity** | Project-specific, 102 tests, 88% coverage | Early-stage open source | Mature (v1.0+), large community | Early-stage, active development | Paradigm, not a product |

### Verdict

| Technology | Recommendation | Rationale |
|-----------|---------------|-----------|
| **Agentura** | **Continue as core** | Only system with native GTD model, ADR discipline, privacy-by-design, and deterministic planning. Irreplaceable for D3 (personal ops). |
| **n8n** | **Adopt for Wave 2 integrations** | Use as an automation bus for connecting Telegram, email sending, webhook triggers. Don't move business logic there — only use for I/O orchestration. |
| **OpenClaw** | **Monitor, don't adopt** | Good multi-channel support but generic AI assistant model doesn't fit our structured GTD pipeline. May borrow ideas for Telegram integration. |
| **PocketPaw** | **Don't adopt** | Desktop hub model conflicts with our CLI-first, SQLite-single-writer approach. Multi-agent routing adds complexity without matching our defined role model. |
| **Codex-app paradigm** | **Already adopted** | Our AGENTS.md + AGENT_RUNTIME.md already implements this paradigm. User is the orchestrator; agents (on any LLM) execute within policy boundaries. Continue deepening. |

### Recommended hybrid architecture

```
Agentura (core)                    n8n (integration bus)
┌─────────────────┐               ┌──────────────────┐
│ GTD lifecycle   │               │ Telegram webhook  │
│ Day planning    │◄─── HTTP ────►│ Email send        │
│ Deal pipeline   │               │ CalDAV polling    │
│ Review/report   │               │ File detection    │
│ LLM extraction  │               │ Notification      │
│ Decision log    │               │ Scheduled triggers│
└─────────────────┘               └──────────────────┘
     SQLite                              n8n DB
  (source of truth)                 (execution log only)
```

**Key rule:** n8n is an I/O adapter, not a brain. All business logic, task lifecycle, and data ownership remain in Agentura.

---

## Deliverable 5: Implementation Plan (30 / 60 / 90 days)

### Days 1–30: Foundation Complete (Wave 0 + Wave 1 start)

**Goal:** All designed systems operational. Observation layer live. First assisted extractions.

| Week | Deliverables | Dependency |
|------|-------------|-----------|
| W1 (Feb 17–23) | R1 schema migration live. Calendar sync (R2) passing with real Yandex. | Auth blocker resolved |
| W2 (Feb 24–Mar 2) | Mail sync (R3) live. Email stats command. Security guardrails (R4). | R1 |
| W3 (Mar 3–9) | Ingestion pipeline operational (I1-I6 runtime already merged). Test with real meeting notes. Tune extraction prompts. | R1, R3 |
| W4 (Mar 10–16) | Delegation tracker (W1-4): extend WAITING tasks with structured delegation fields. Daily delegation report in `review week`. | MVP |

**Day 30 checkpoint:**
- `execas busy list` shows real Yandex calendar events
- `execas mail stats` shows email volume for the week
- `execas ingest meeting /path/to/notes.md` extracts task candidates
- `execas ingest review` shows pending drafts for approval
- All tests pass, coverage >= 80%

### Days 31–60: Assistance Layer (Wave 1 complete + Wave 2 start)

**Goal:** System is actively helpful. Reduces daily operational overhead by ~40%.

| Week | Deliverables | Dependency |
|------|-------------|-----------|
| W5 (Mar 17–23) | Deal entity + pipeline stages (ADR-12). `deal add`, `deal list`, `deal stage`. | New ADR |
| W6 (Mar 23–30) | Email priority scoring. Smart weekly review with commitment progress. | W0-2, W1-5 |
| W7 (Mar 31–Apr 6) | n8n integration bus setup. Telegram bot skeleton (receive messages, forward to ingest). | n8n deploy |
| W8 (Apr 7–13) | Auto-create tasks above 0.8 confidence (W2-1). Follow-up draft generation for top-priority emails. | W1-1, W1-2 |

**Day 60 checkpoint:**
- Deal pipeline tracked in system (`deal list --stage active`)
- Telegram messages ingested as task candidates
- High-confidence tasks auto-created (review log shows accept rate)
- Email follow-up drafts available for review
- n8n handles Telegram webhook and scheduled calendar sync

### Days 61–90: Execution Layer (Wave 2 complete)

**Goal:** System proposes and executes with confirmation. User reviews, doesn't create.

| Week | Deliverables | Dependency |
|------|-------------|-----------|
| W9 (Apr 14–20) | Delegation notification via Telegram (W2-2). Overdue ping automation. | n8n + Telegram |
| W10 (Apr 21–27) | Meeting agenda generator from open tasks + waiting items. КП template filler (first iteration). | W1-4, W1-5 |
| W11 (Apr 28–May 4) | Telegram channel as full ingest source (C4). Policy-based auto-triage for known email patterns. | n8n, W1-7 |
| W12 (May 5–11) | Dashboard command (`execas dash`): today's plan, pending reviews, overdue delegations, deal pipeline, email backlog — all in one view. | All W2 items |

**Day 90 checkpoint:**
- `execas dash` shows full operational picture
- Delegation reminders sent automatically via Telegram
- Meeting agendas generated from system data
- Email auto-triage handles >50% of routine email
- User spends <45 min/day on operational overhead (vs ~2-3 hours)

---

## Deliverable 6: Autonomy Policy

### Autonomy levels

| Level | Name | Scope | Human role | Example |
|-------|------|-------|-----------|---------|
| **L0** | Observe | Read external data, store locally | None required | Calendar sync, email header sync |
| **L1** | Suggest | Extract candidates, classify, score | Review and approve/skip | Task drafts from meeting notes, email priority scores |
| **L2** | Execute-with-confirm | Propose action + draft, wait for `accept` | One-command approval | Auto-create task, send follow-up email draft, delegate via Telegram |
| **L3** | Autonomous | Execute on policy, log for audit | Post-hoc review (exception-based) | Auto-triage known email, send overdue reminders, advance deal stage |

### Per-domain autonomy matrix

| Job step | Current | Target (90d) | Target (180d) | Guardrails |
|----------|---------|-------------|--------------|-----------|
| Calendar sync | manual | L0 | L0 | Read-only, no calendar writes |
| Email triage | manual | L1 | L3 (known senders) | No body to LLM, subject+sender only |
| Task extraction (meetings) | manual | L1 | L2 (>0.8 confidence) | Dedup prevents duplicates, review queue for <0.8 |
| Task extraction (email) | manual | L1 | L2 (>0.8 confidence) | ADR-10 privacy, source tracking |
| Task extraction (Telegram) | N/A | L0 | L1 | New channel, start conservative |
| Day planning | L0 (deterministic) | L0 | L0 | ADR-06: no LLM in planning |
| Weekly review | L0 (deterministic) | L0 | L1 (narrative) | Scoring deterministic, narrative LLM-optional |
| Delegation notification | manual | L1 | L2 | Template-based, user confirms recipient |
| Follow-up reminders | manual | L1 | L3 (policy-based) | Only for items in WAITING >N days |
| Email response draft | manual | L1 | L2 | User always reviews before send |
| КП generation | manual | L1 | L2 | Template + deal context, user reviews |
| Deal stage advance | manual | L1 | L2 | Signal-based (email received, meeting held) |

### Escalation rules

1. **Confidence below threshold** → Always escalate to L1 (human review).
2. **New sender/entity** → Escalate to L1 regardless of confidence score.
3. **Financial content** (detected by keyword) → Never above L1.
4. **External communication** (sending email, Telegram message) → Never above L2. User always confirms outbound.
5. **Destructive operations** (task delete, deal close, contact remove) → Always L2 with explicit confirmation.
6. **Schema/data changes** → Chief Architect approval required (AGENTS.md section 2).

### Trust building protocol

Autonomy level advances per-domain based on:

| Signal | Measurement | Threshold for promotion |
|--------|------------|----------------------|
| Accuracy | (accepted drafts) / (total drafts) per channel | > 90% over 2 weeks → eligible for L+1 |
| False positive rate | (skipped or rejected) / (auto-created) | < 5% over 2 weeks → eligible for L+1 |
| User override rate | (user changed auto-action) / (auto-actions) | < 10% over 2 weeks → eligible for L+1 |
| Error count | System errors, wrong extractions, missed items | 0 critical errors in 2 weeks → eligible for L+1 |

**Demotion:** Any critical error (wrong person contacted, incorrect deal data, missed deadline due to system failure) → immediate demotion to L1 for that domain, with manual review of all recent auto-actions.

### Audit trail

All autonomy actions are logged in `ingest_log` (existing) and future `automation_log` table:

- `timestamp`, `domain`, `autonomy_level`, `action_type`, `action_detail`, `confidence`, `outcome` (accepted/rejected/error), `user_override` (boolean)

This log supports both trust measurement and compliance review.

---

## Summary: Key Decisions

1. **Agentura remains the core.** Don't replace it — expand its perimeter.
2. **n8n as I/O bus** for multi-channel connectivity (Telegram, scheduled triggers, notifications). Business logic stays in Python.
3. **Wave 0 first** (calendar + email observation) — it's almost ready (R1-R4 designed).
4. **Deals as a first-class entity** (ADR-12) — fills the biggest gap in D2.
5. **Telegram is the priority channel** for Wave 2 — it's where team communication happens and where delegation notifications should go.
6. **Autonomy is earned, not assumed.** Start at L0/L1, promote based on measured accuracy.
7. **No email body to LLM, ever.** ADR-10 privacy boundary is permanent.
8. **Outbound communication never above L2.** User always confirms messages sent to other people.

---

## Appendix: ADR Roadmap

| ADR | Topic | Wave | Status |
|-----|-------|------|--------|
| ADR-10 | External sync provenance schema | W0 | Designed |
| ADR-11 | Task ingestion pipeline | W1 | Designed + runtime merged |
| ADR-12 | Deal pipeline entity model | W1 | Proposed (this plan) |
| ADR-13 | Telegram channel integration | W2 | Proposed (this plan) |
| ADR-14 | n8n integration bus boundary | W2 | Proposed (this plan) |
| ADR-15 | Autonomy level framework | W3 | Proposed (this plan) |

---

## Gate Report: STRAT-PLAN-01

### 1) Role confirmation
- Acting roles: System Analyst (job map, requirements), Chief Architect (architecture, technology evaluation), Technical Lead (implementation plan, delivery sequencing), Executive Assistant (operational feasibility check).
- Authority basis: `AGENTS.md` section 2 — documentation is self-approved; architecture proposals require Chief Architect (acting). ADR proposals (12-15) are flagged as "proposed" — formal ADR authoring deferred to implementation phase.

### 2) Decisions
1. Agentura continues as core system; no platform replacement.
2. n8n adopted as integration bus for I/O only; no business logic migration.
3. OpenClaw and PocketPaw not adopted (monitoring only).
4. Codex-app paradigm already embedded in AGENTS.md — continue deepening.
5. Four-level autonomy model (L0-L3) with per-domain assignment.
6. Trust building via accuracy metrics with 2-week promotion windows.
7. Outbound communication capped at L2 (always-confirm).
8. Deal pipeline (ADR-12) identified as highest-value new entity.

### 3) Artifacts
- `spec/STRATEGIC_AUTOMATION_PLAN.md` — this file (6 deliverables, ~400 lines)

### 4) Traceability
- ADR-06 (deterministic planning): referenced in autonomy policy — planning stays L0.
- ADR-09 (single writer): referenced in architecture — EA writes, all else reads.
- ADR-10 (sync schema): referenced — Wave 0 depends on R1-R4 completion.
- ADR-11 (ingestion pipeline): referenced — Wave 1 core dependency.
- `AGENTS.md` section 2: authority boundaries for all 4 acting roles.
- `spec/EXECUTION_PLAN.md`: Phase 6 (R1-R4) and Phase 7 (I1-I6) as prerequisites.
- `apps/executive-cli/src/executive_cli/models.py`: current schema as baseline for new entities.

### 5) Implementation handoff
- Wave 0 (R1-R4): ready for implementation — all designs exist.
- Wave 1 (ADR-11 I1-I6): runtime merged (commit 68ae625) — needs real-world calibration.
- Wave 1 (ADR-12 deals): requires formal ADR before implementation.
- Wave 2 (n8n, Telegram): requires ADR-13 and ADR-14 before implementation.
- Wave 3: requires ADR-15 and minimum 60 days of Wave 1-2 operational data.

### 6) Risks / open questions
1. n8n self-hosted deployment complexity — may need Docker setup guidance.
2. Telegram Bot API rate limits for high-volume groups.
3. Deal pipeline schema needs user input on actual deal stages and fields.
4. LLM extraction quality for Russian+English mixed content — requires real-world prompt tuning.
5. 30-day plan assumes Yandex auth blocker is resolved.
6. Team members' willingness to use Telegram bot for delegation tracking (adoption risk).

### 7) ADR status
- ADR-01 through ADR-11 remain unchanged.
- ADR-12 through ADR-15 proposed (not yet authored — deferred to implementation phase).

### Participation metrics
- Configured participating roles: 4 (SA, ARCH, TL, EA)
- Observed active role sessions: 4 (combined in single session)
- Configured max parallel lanes: N/A (strategic planning, not implementation)
- Observed max parallel lanes: 1
