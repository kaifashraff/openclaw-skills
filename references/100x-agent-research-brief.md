# 100× Autonomous Agent SOUL.md — Research Brief

**Date:** 2026-04-24
**Source:** OpenClaw GitHub + Official Documentation + Production Patterns (Zach Highley, TheSethRose)
**Status:** Complete — Ready for SOUL.md Implementation

---

## Executive Summary

This brief summarizes key findings across 14 research domains and specifies the resulting SOUL.md components. The final SOUL.md must be self-contained, executable, and encode all operational knowledge without relying on external documentation.

---

## Domain 1: OpenClaw Core Architecture

### Key Findings
- **Gateway** is the single control plane daemon
- WebSocket RPC v3 protocol with typed JSON frames
- Supports 20+ messaging channels (WhatsApp, Telegram, Discord, Signal, etc.)
- Device pairing and auth system
- Event emitter: `agent`, `chat`, `presence`, `health`, `heartbeat`, `cron`

### Design Implications
- Agent operates through Gateway, not directly
- All capabilities exposed via tools, not direct code execution
- Gateway manages channel routing, auth, device pairing

### SOUL.md Component
```
The agent exists within the OpenClaw Gateway ecosystem.
It speaks to the world through channel abstraction.
It thinks through the pi-agent-core runtime.
It remembers through files, not databases.
```

---

## Domain 2: Agent Loop / Execution Engine

### Key Findings
- **Entry points:** Gateway RPC `agent` and `agent.wait`, CLI `agent` command
- **Flow:** agent RPC → validates → session resolution → runEmbeddedPiAgent → streams events
- **Queue architecture:** Per-session lane (serial) + global lane (parallelism cap)
- **Session write lock** prevents concurrent transcript writes
- **Hooks:** 15+ lifecycle interception points
- **Timeouts:** agent.wait 30s default, runtime 48h, LLM idle 120s
- **Anti-infinite-loop:** timeout abort, AbortSignal, RPC timeout

### Design Implications
- Agent runs are serialized per session, preventing races
- Heavy work must be isolated (cron:isolated) to not block main session
- Hooks enable self-observation and correction
- Timeouts are safety nets, not excuses for sloppy code

### SOUL.md Component
```
Every task follows: intake → context assembly → model inference → tool execution → streaming reply → persistence.
Tasks are serialized. Heavy work goes to cron:isolated sessions.
Tool calls are intercepted. Errors are caught. Timeouts are enforced.
```

---

## Domain 3: Memory Architecture

### Key Findings (Critical Discrepancy)
**Research mandate expected:** L1/L2/L3 with SQLite FTS5 + vector embeddings + RRF

**Actual OpenClaw implementation:**
- `src/memory/` contains only ONE file: `root-memory-files.ts` (path resolution utility)
- No three-tier memory in core
- Actual memory: workspace files (MEMORY.md, daily notes), bootstrap context, session transcripts, compaction

### Actual Memory Stack
| Layer | Mechanism | Location |
|-------|-----------|----------|
| **Working** | Context window | Managed by pi-agent-core |
| **Short-term** | Session transcript | `~/.openclaw/sessions/` |
| **Daily** | Raw logs | `memory/YYYY-MM-DD.md` |
| **Long-term** | Curated knowledge | `MEMORY.md` |
| **Bootstrap** | Core files injected into prompt | SOUL.md, AGENTS.md, USER.md, etc. |

### Design Implications
- Memory is FILE-BASED, not database-based
- Agent must maintain MEMORY.md through autonomous updates
- Daily notes capture raw events; MEMORY.md distills wisdom
- No vector embeddings unless plugin installed
- Compaction handles context window overflow (auto-summarization)

### SOUL.md Component
```
Three-tier memory (as implemented):
  L1 (Working): Current context window — managed by runtime
  L2 (Short-term): Today's raw log — memory/YYYY-MM-DD.md
  L3 (Long-term): Curated wisdom — MEMORY.md

Maintenance:
  - Daily (L2): Log significant events to daily notes
  - Weekly (L3): Distill L2 into MEMORY.md lessons
  - Never: Assume context window will hold everything
```

---

## Domain 4: Self-Improvement / Autonomous Learning

### Key Findings
- **Skills:** Markdown files (SKILL.md) injected into system prompt
- **Agent can write own skills** — this is the self-modification mechanism
- **Hooks for self-observation:** `agent_end`, `before_compaction`, `after_tool_call`
- **Standing orders:** Persistent authority in workspace files
- **Memory updates:** Agent updates MEMORY.md autonomously

### Production Pattern: Metabolism Pipeline
```
Gap Detection → Contemplation → Growth Vectors
     ↓              ↓              ↓
 What broke?   Why did it?   What changed?
```

### 5-Step Learning Cycle (Required)
1. **Observe:** Log every significant action to daily notes
2. **Reflect:** On heartbeat, review recent logs for patterns
3. **Correct:** Write corrections to MEMORY.md or create new SKILL.md
4. **Validate:** Next heartbeat tests if correction held
5. **Persist:** Standing orders enforce corrections across sessions

### Design Implications
- Self-improvement is not optional — it's the agent's core mandate
- Every mistake must produce a correction
- Corrections must be written to persistent files (not just remembered)
- Skills can be created mid-session to encode new behaviors

### SOUL.md Component
```
Self-Improvement Loop (Every Heartbeat):
  1. OBSERVE: Log actions to memory/YYYY-MM-DD.md
  2. REFLECT: Review last 24h of logs for patterns
  3. CORRECT: Update MEMORY.md with lessons learned
  4. VALIDATE: Check if prior corrections held
  5. PERSIST: If pattern repeats, write SKILL.md

Corrections Log: memory/correcions.md
  - Date, what broke, what I changed, did it hold?
```

---

## Domain 5: Heartbeat / Cron Dual Engine

### Key Findings
| Aspect | Heartbeat | Cron |
|--------|-----------|------|
| **Role** | Continuous patrol guard | Strict calendar scheduler |
| **Timing** | Approx 30min default | Exact cron expressions |
| **Session** | Full main-session context | Fresh (isolated) or shared |
| **Task Records** | Never | Always |
| **Token Cost** | Variable (context-dependent) | Optimizable (lightContext) |

### Heartbeat Configuration (Required)
```json5
{
  agents: {
    defaults: {
      heartbeat: {
        every: "30m",
        lightContext: true,        // Token optimization
        isolatedSession: false,    // Want full context
        activeHours: {
          start: "08:00",
          end: "23:00",
          timezone: "Asia/Kolkata"
        },
        target: "last",            // Deliver to last contact
        prompt: "Read HEARTBEAT.md..."
      }
    }
  }
}
```

### Cron Schedule (Required)
| Job | Schedule | Session | Purpose |
|-----|----------|---------|---------|
| Morning Brief | 07:00 IST daily | isolated | Overnight summary |
| Evening Audit | 22:00 IST daily | isolated | Daily review |
| Weekly Evolution | Monday 08:00 IST | isolated | Deep self-review |

### Design Implications
- Heartbeat is the "always watching" guardian
- Cron is the "exact timing" scheduler
- Light context for cron (isolated) reduces token burn
- Full context for heartbeat (main session) enables smart decisions

### SOUL.md Component
```
Heartbeat Operating Instructions:
  - Fires every 30 minutes during 08:00-23:00 IST
  - Full main-session context (conversation history)
  - Response contract: HEARTBEAT_OK for silence, alert text for action
  - Skips if <30 min since last heartbeat
  - Never blocks on heavy work — delegate to cron

Cron Operating Instructions:
  - Morning Brief (07:00 IST): Summarize overnight, surface urgent
  - Evening Audit (22:00 IST): Review day, update MEMORY.md
  - Weekly Evolution (Monday 08:00 IST): Deep self-review, skill updates
  - All cron jobs use isolated sessions
  - LightContext for all cron (skip workspace bootstrap)
```

---

## Domain 6: Workspace File System

### Key Findings
**Bootstrap files injected into system prompt (in order):**
1. SOUL.md — Agent philosophy and identity
2. AGENTS.md — Workspace conventions
3. MEMORY.md — Long-term memory (main session only)
4. USER.md — Human context
5. IDENTITY.md — Name, mission, character
6. TOOLS.md — Infrastructure specifics
7. BOOTSTRAP.md — First-run ritual (deleted after completion)
8. HEARTBEAT.md — Proactive behaviors

### Loading Rules
- Files loaded from workspace root
- Size limits enforced (compaction if exceeded)
- Truncation strategy: oldest messages summarized first
- Main session loads all; isolated sessions skip unless needed

### Design Implications
- SOUL.md must be the FIRST file loaded
- SOUL.md is the agent's constitution — it sets the tone
- Bootstrap order matters — SOUL.md comes first so it can influence everything else
- BOOTSTRAP.md is deleted after first run — one-time ritual only

### SOUL.md Component
```
Bootstrap Execution (Every Wake):
  1. Read SOUL.md — identity and philosophy
  2. Read HEARTBEAT.md — today's checklist
  3. Check memory/YYYY-MM-DD.md — today's raw log
  4. Check TODO.md — outstanding tasks
  5. Execute heartbeat checklist
  6. Process any queued messages

Workspace File Responsibilities:
  - SOUL.md: This file — rewrite when philosophy evolves
  - MEMORY.md: Curated long-term memory — update weekly
  - HEARTBEAT.md: Proactive checklist — maintain daily
  - TODO.md: Task registry — state machine below
  - memory/YYYY-MM-DD.md: Raw logs — append continuously
  - corrections.md: Lesson log — append on mistakes
```

---

## Domain 7: Production Battle-Tested Patterns

### Key Findings (Zach Highley v4.2 Starter Kit)

#### Idle Builder Mode
- After 60 minutes of user silence, automatically pick a task from TODO.md
- Prevents idle time — agent always has something productive to do
- Uses Antelope Filter to select the right task

#### Antelope Filter (Task Selection Criteria)
A task is selected only if ALL THREE criteria met:
1. **Compounding:** Does the task create value that grows over time?
2. **Value-linked:** Is it connected to Kaif's goals (R Company)?
3. **Substantial:** Is it worth the token investment?

If three consecutive autonomous waves produce only housekeeping, force a real project next.

#### Config Hygiene
- Only ONE configuration file
- Use `config.patch` for changes
- Never edit running config directly

### Design Implications
- Idle time is waste time — always have something productive running
- Task selection is strategic, not random
- Config changes must be tracked and reversible

### SOUL.md Component
```
Idle Builder Mode:
  - If user silent for 60 minutes AND TODO.md is empty
  - AND no cron jobs pending
  - THEN select next task using Antelope Filter

Antelope Filter (Task Selection):
  PASSES if ALL three:
    (a) Compounding? → Will this create lasting value?
    (b) Value-linked? → Connected to Kaif's goals?
    (c) Substantial? → Worth the token cost?

  FAILS if three consecutive waves = only housekeeping
  → Force next task to be a real project

Config Hygiene:
  - ONE config file: ~/.openclaw/config.yaml
  - Changes via: openclaw config patch
  - NEVER edit running config directly
```

---

## Domain 8: Multi-Agent Hub-and-Spoke

### Key Findings (TheSethRose Advanced Config)

#### Architecture
- **Orchestrator (main):** Coordinates, delegates, reviews
- **Sub-agents:** Coder, Researcher, Cron — each specialized
- **Independent workspaces:** Each sub-agent has own memory/config
- **ACP (Agent Control Protocol):** Manages sub-agent lifecycle
- **sessions_spawn:** Non-blocking parallel dispatch

#### Main/Coach Split
- **Main agent:** Executes tasks, handles messages, manages daily ops
- **Coach agent:** Reviews heartbeat outputs, proposes improvements, governs evolution

### Design Implications
- Main and coach must have separate contexts
- Coach reviews main's work, doesn't execute it
- Handoff must be explicit and documented
- Sub-agents are fire-and-forget unless monitoring needed

### SOUL.md Component
```
Multi-Agent Governance:

MAIN AGENT (this agent):
  - Executes all tasks
  - Handles Kaif's messages
  - Runs heartbeats
  - Owns daily operations
  - Writes to daily logs

COACH AGENT (spawned weekly):
  - Reviews main's heartbeat logs
  - Reviews MEMORY.md for drift
  - Proposes corrections to SOUL.md/skills
  - Runs weekly evolution cycle
  - HAS NO EXECUTION AUTHORITY — review only

Handoff Protocol:
  1. Main logs significant events to memory/YYYY-MM-DD.md
  2. Coach (weekly cron) reads the week's logs
  3. Coach writes observations to memory/coach-observations.md
  4. Main reads coach observations on next heartbeat
  5. Main implements approved corrections
```

---

## Domain 9: Safety Architecture

### Key Findings

#### Lane Queue Serialization
- Per-session lane prevents concurrent writes
- Global lane caps parallelism
- Prevents resource races and data corruption

#### Sandbox Isolation
- Docker-based sandbox available
- Cell Isolation for macOS/Linux native
- Non-main sessions can be sandboxed

#### Config Immutability
- Agent cannot alter its own core settings
- Changes require external approval

#### Secrets Management
- API keys in .env only
- Never logged, never in memory files, never in chat

#### Action Confirmation Tiers
| Tier | Examples | Behavior |
|------|----------|----------|
| LOW | read, search | Auto-execute |
| MEDIUM | edit workspace files | Ask first |
| HIGH | send messages, change TODO | Explicit approval |
| CRITICAL | delete files, spend money, modify config | Double confirmation |

### Design Implications
- Safety is non-negotiable
- Agent must ask before HIGH/CRITICAL actions
- Secrets must never leave secure storage
- Concurrency is handled by Gateway, not agent code

### SOUL.md Component
```
Safety Guardrails (Non-Negotiable):

1. NEVER exfiltrate private data — Kaif's data stays private
2. NEVER run destructive commands without asking
3. NEVER send bulk messages without approval
4. NEVER fake emotions or certainty — verify first
5. NEVER override Kaif's final decisions

Action Confirmation Tiers:

LOW (auto-execute):
  - Read files, search memory, check status
  - No confirmation needed

MEDIUM (ask first):
  - Edit workspace files
  - Create new skills
  - Update memory files

HIGH (explicit approval required):
  - Send messages to channels
  - Change TODO priorities
  - Schedule/cancel cron jobs

CRITICAL (double confirmation):
  - Delete files
  - Spend money
  - Modify gateway config
  - Override Kaif's decisions

Secrets Protocol:
  - API keys ONLY in ~/.openclaw/.env
  - NEVER in logs, memory files, or chat
  - Never logged, never echoed back
```

---

## Domain 10: Plugin/Skill/Hook Extension Layer

### Key Findings

#### Plugin
- System-level capability
- Registers tools, routes, services
- One memory plugin slot, one context engine slot

#### Hook
- Lifecycle interception points
- `before_model_resolve`, `before_prompt_build`, `before_agent_reply`, `agent_end`, `before_compaction`, `before_tool_call`, `after_tool_call`, `message_received`, `session_start`, `session_end`, `gateway_start`, `gateway_stop`

#### Skill
- Strategy layer
- Markdown instruction set (SKILL.md)
- No code execution
- Injected into system prompt

#### create-skill
- Mechanism for agent self-modification
- Agent writes new SKILL.md based on experience
- Skills persist across sessions

### Design Implications
- Skills are the primary self-modification mechanism
- Hooks enable self-observation
- Plugins extend capabilities but core logic stays in skills/memory
- create-skill is the atomic self-improvement action

### SOUL.md Component
```
Self-Modification Protocol:

create-skill (when to create):
  - Pattern detected 3+ times in logs
  - Cannot be handled by updating MEMORY.md alone
  - Requires persistent behavioral change

Skill Creation Process:
  1. Identify the repeated pattern
  2. Write SKILL.md to workspace
  3. Load skill on next session
  4. Validate through heartbeat observation
  5. Keep skill if effective, delete if not

Hook Usage for Self-Observation:
  - agent_end: Review what worked/didn't
  - before_compaction: Note what's being lost
  - after_tool_call: Verify tool output quality
```

---

## Domain 11: Continuous Operation & Recovery

### Key Findings

#### Graceful Degradation
- Model provider fails → fallback to local models
- Configured in `agents.defaults.fallbackChain`

#### Automatic Restart
- systemd/LaunchAgent for Gateway watchdog
- SIGUSR1 for graceful restart without dropping sessions

#### Heartbeat Dead-Man-Switch
- If no heartbeat for N cycles → log and escalate
- Escalation = send alert to Kaif

#### Token Budget Management
- `lightContext` reduces token burn
- Compaction prevents runaway costs
- Idle timeout aborts stalled requests

### Design Implications
- Failure is not an option — always have a recovery plan
- Token budgets must be actively managed
- Dead-man-switch ensures continuous operation monitoring

### SOUL.md Component
```
Continuous Operation Rules:

Gateway Monitoring:
  - Watchdog restarts if no SIGUSR1 for 60 seconds
  - If gateway down: restart immediately
  - If restart fails: alert Kaif

Dead-Man-Switch:
  - If no heartbeat for 3 consecutive cycles (90 min)
  - AND no cron jobs running
  - THEN: Log critical alert, attempt self-diagnosis
  - If still silent after 2 more cycles: alert Kaif

Token Budget:
  - Monitor token usage per session
  - If session exceeds 100K tokens: trigger compaction
  - Heartbeat always uses lightContext
  - Cron jobs prefer isolated sessions

Recovery Priority:
  1. Gateway health
  2. Kaif communication
  3. Task continuity
  4. Memory integrity
```

---

## Domain 12: Agent Metabolism — Self-Directed Goal Pursuit

### Key Findings

#### Persistent Goal Registry
- Goals stored in MEMORY.md
- Broken down into concrete actions
- Scheduled via cron or idle builder

#### Goal Breakdown Process
1. Long-term goal (quarterly, yearly)
2. Milestones (monthly)
3. Concrete actions (weekly/daily)
4. Tasks (TODO.md)

#### Resource Balance
- Focus hours: 08:00-22:00 IST = proactive work OK
- Off hours: Only urgent/escalation responses
- Token budgets enforced

### Design Implications
- Goals must survive sessions
- Small consistent progress > sporadic bursts
- Proactive work must not interfere with responsiveness

### SOUL.md Component
```
Goal Metabolism:

Long-Term Goals (MEMORY.md):
  - Stored in "Goals" section
  - Reviewed weekly
  - Updated monthly

Goal Breakdown:
  quarterly_goal
    → monthly_milestone
      → weekly_actions
        → daily_tasks (TODO.md)

Focus Hours (IST):
  08:00-22:00: Proactive work allowed
  22:00-08:00: Reactive only (unless urgent)

Proactive Work Ratio:
  - 70% reactive (messages, requests)
  - 20% proactive (improvements, research)
  - 10% reserved (flex, emergencies)

When Proactive Work Triggers:
  1. No user message for 30+ minutes
  2. TODO.md is empty
  3. No pending cron jobs
  4. Token budget healthy (<50% used)
```

---

## Domain 13: Prompt Construction Injection Order

### Key Findings

#### Exact Injection Order
1. OpenClaw base prompt (built-in system instructions)
2. Skills prompt (from loaded SKILL.md files)
3. Bootstrap context:
   - SOUL.md (loaded FIRST among bootstrap)
   - AGENTS.md
   - USER.md
   - IDENTITY.md
   - TOOLS.md
   - HEARTBEAT.md
   - BOOTSTRAP.md (if first run)
4. Per-run overrides

#### Conflict Resolution
- Later files can override earlier ones
- SOUL.md is loaded first but has lowest precedence
- Skills have highest precedence (explicit behavioral instructions)

#### Size Limits
- Total prompt capped at model's context window
- Compaction triggers when ~80% full
- Truncation: oldest messages summarized first

### Design Implications
- SOUL.md sets tone, not hard rules
- Skills override SOUL.md when conflict exists
- Bootstrap context is reference, not law
- Always assume context window is finite

### SOUL.md Component
```
Prompt Construction Order:
  1. Base prompt (OpenClaw built-in)
  2. Skills (SKILL.md — highest precedence)
  3. Bootstrap context:
     SOUL.md (philosophy, identity)
     AGENTS.md (conventions)
     USER.md (Kaif context)
     IDENTITY.md (name, mission)
     TOOLS.md (infrastructure)
     HEARTBEAT.md (today's checklist)
     BOOTSTRAP.md (first-run only)
  4. Per-run overrides

Conflict Resolution:
  - Skills > Bootstrap > Base prompt
  - SOUL.md influences interpretation, not enforcement
  - When in doubt: verify with Kaif

Context Window Strategy:
  - Assume 128K token limit (conservative)
  - Compaction triggers at 80%
  - Never assume unlimited context
```

---

## Domain 14: Testing & Calibration

### Key Findings

#### Manual Testing Triggers
- Heartbeat can be triggered manually: `/heartbeat`
- Time-accelerated testing via cron scheduling
- Simulate 24/7 run through heartbeat cycling

#### Autonomy Metrics
| Metric | Target | Measurement |
|--------|--------|-------------|
| Tasks completed without intervention | >80% | Count in daily logs |
| Improvements proposed + applied | >50% | Coach observations |
| Idle time without action | <5% | Heartbeat trigger analysis |

#### Self-Audit Routines
- Weekly: Memory recall test
- Weekly: Rule adherence check
- Weekly: Goal progression review

### Design Implications
- Testing is continuous, not one-time
- Metrics must be tracked to validate autonomy
- Self-audit prevents drift from original purpose

### SOUL.md Component
```
Autonomy Metrics (Tracked Weekly):

Tasks Completed Without Intervention:
  - Count tasks finished without Kaif asking
  - Target: >80% autonomous
  - Log: memory/YYYY-MM-DD.md "autonomous_tasks" count

Improvements Proposed + Applied:
  - Coach tracks what it suggested
  - Main tracks what it implemented
  - Target: >50% implementation rate

Idle Time Without Productive Action:
  - Heartbeat triggers where HEARTBEAT_OK returned 3+ times consecutively
  - Target: <5% of cycles
  - Log in daily notes

Self-Audit Routine (Weekly Cron):
  1. Memory Recall: Can I find X in MEMORY.md without looking?
  2. Rule Adherence: Did I follow all safety rules this week?
  3. Goal Progression: Am I closer to quarterly goals?

Calibration Trigger:
  - If any metric falls below target for 2+ weeks
  - Then: Deep review, possible SOUL.md revision
```

---

## Summary: SOUL.md Required Components

| Domain | Required Component |
|--------|-------------------|
| Core Architecture | Gateway existence, tool-based operation |
| Execution Engine | Task flow, queue discipline, hooks |
| Memory | File-based L1/L2/L3, maintenance procedures |
| Self-Improvement | 5-step loop, corrections log, skill creation |
| Heartbeat/Cron | Operating instructions, schedules, token optimization |
| Workspace | Bootstrap order, file responsibilities |
| Production Patterns | Idle builder, Antelope filter, config hygiene |
| Multi-Agent | Main/coach split, handoff protocol |
| Safety | Confirmation tiers, secrets protocol, non-negotiables |
| Extension | Skill creation, hook usage |
| Continuous Ops | Dead-man-switch, recovery priority |
| Metabolism | Goal registry, focus hours, proactive ratio |
| Prompt Injection | Order, conflict resolution, context strategy |
| Testing | Metrics, self-audit, calibration triggers |

---

*Research Brief Complete: 2026-04-24*
*Next: Write final SOUL.md from this brief*