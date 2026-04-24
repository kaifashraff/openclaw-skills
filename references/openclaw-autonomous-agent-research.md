# OpenClaw 100× Autonomous Agent Research Blueprint

**Date:** 2026-04-24
**Source:** OpenClaw GitHub Repo + Official Documentation
**Status:** Research Complete - Ready for SOUL.md Design

---

## Executive Summary

This document provides a code-level research blueprint for designing a fully autonomous, self-improving OpenClaw agent. Investigation covered 5 major domains: Execution Engine, Gateway Control Plane, Heartbeat+Cron Dual Engine, Memory Architecture, and Self-Improvement Ecosystem.

**Key Finding:** The research mandate references architecture components that partially differ from the current OpenClaw implementation. Critical discrepancies exist in the Memory Architecture (expectations vs. reality) and certain file paths. However, the core autonomous operation capabilities are present and well-documented.

---

## Research Domain 1: Execution Engine

### Source Location
- **Docs:** https://docs.openclaw.ai/concepts/agent-loop
- **Key Function:** `runEmbeddedPiAgent` (from pi-agent-core runtime)

### Architecture Overview

```
Entry Points
    ↓
agent RPC → validates params → resolves session → returns { runId, acceptedAt }
    ↓
agentCommand → resolves model + thinking defaults → loads skills → calls runEmbeddedPiAgent
    ↓
runEmbeddedPiAgent → serializes runs via queues → resolves model/auth → subscribes to events → enforces timeout
    ↓
subscribeEmbeddedPiSession → bridges pi-agent-core events to OpenClaw streams
    ↓
Output: lifecycle events, assistant deltas, tool events
```

### Key Components

#### 1. Entry Points
- Gateway RPC: `agent` and `agent.wait`
- CLI: `agent` command

#### 2. Queue Architecture (per-session + global)
```
Session Lane (serial per-session)
    ↓
Global Lane (cross-session fairness, capped by agents.defaults.maxConcurrent)
```
- Prevents tool/session races
- Keeps session history consistent
- Session write lock on transcript file (non-reentrant by default)

#### 3. Session + Workspace Preparation
- Workspace resolved and created
- Skills loaded (or reused from snapshot)
- Bootstrap/context files resolved and injected
- Session write lock acquired before streaming

#### 4. Prompt Assembly
- System prompt built from:
  - OpenClaw base prompt
  - Skills prompt
  - Bootstrap context
  - Per-run overrides
- Model-specific limits enforced
- Compaction reserve tokens applied

#### 5. Hook Points (Plugin Lifecycle)

**Internal Hooks (Gateway):**
- `agent:bootstrap`: runs while building bootstrap files
- Command hooks: `/new`, `/reset`, `/stop`, etc.

**Plugin Hooks:**
| Hook | When | Purpose |
|------|------|---------|
| `before_model_resolve` | Pre-session | Override provider/model |
| `before_prompt_build` | Post-session load | Inject prependContext, systemPrompt |
| `before_agent_reply` | Pre-LLM call | Let plugin claim turn |
| `agent_end` | Post-completion | Inspect final message list |
| `before_compaction` | Pre-compaction | Observe/annotate |
| `before_tool_call` | Pre-tool execution | Intercept tool params |
| `after_tool_call` | Post-tool execution | Intercept results |
| `message_received` | Inbound message | React to incoming |
| `session_start` | Session creation | Initialize session |
| `session_end` | Session closure | Cleanup session |

#### 6. Timeouts
| Type | Default | Config |
|------|---------|--------|
| `agent.wait` | 30s | `timeoutMs` param override |
| Agent runtime | 172800s (48h) | `agents.defaults.timeoutSeconds` |
| LLM idle | 120s (if no explicit) | `agents.defaults.llm.idleTimeoutSeconds` |

#### 7. Anti-Infinite-Loop Guards
- Agent timeout (abort)
- AbortSignal (cancel)
- Gateway disconnect or RPC timeout
- `agent.wait` timeout

---

## Research Domain 2: Gateway Control Plane

### Source Location
- **Docs:** https://docs.openclaw.ai/concepts/architecture
- **Key Files:** `src/gateway/*` (on GitHub)

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         GATEWAY (Daemon)                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │  Channel    │  │   WebSocket │  │   Event     │             │
│  │  Connectors │  │    Server   │  │   Emitter   │             │
│  │  (WhatsApp, │  │  (RPC v3,   │  │  (agent,    │             │
│  │  Telegram,  │  │   JSON)     │  │   chat,     │             │
│  │  Discord)   │  │             │  │   presence) │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────────────────────────────────────────┘
         ↓                    ↓                    ↓
    ┌─────────┐          ┌─────────┐          ┌─────────┐
    │ Clients │          │  Nodes  │          │  Cron   │
    │(mac app,│          │(macOS/  │          │ Runtime │
    │ CLI,web)│          │iOS/Android)       │         │
    └─────────┘          └─────────┘          └─────────┘
```

### WebSocket RPC Protocol v3

#### Message Types
```
// Requests
{ type: "req", id, method, params } → { type: "res", id, ok, payload|error }

// Events (server→client)
{ type: "event", event, payload, seq?, stateVersion? }
```

#### Connection Lifecycle
```
Client → req:connect → Gateway
Gateway → res (ok/hello-ok + snapshot: presence + health)
Gateway → event:presence, event:tick
Client → req:agent → Gateway
Gateway → res:agent (ack: { runId, status: "accepted" })
Gateway → event:agent (streaming)
Gateway → res:agent (final: { runId, status, summary })
```

#### Authentication
- Token-based: `connect.params.auth.token` or `connect.params.auth.password`
- Tailscale Serve: `gateway.auth.allowTailscale: true`
- Trusted-Proxy: `gateway.auth.mode: "trusted-proxy"`
- None (insecure): `gateway.auth.mode: "none"`

#### Device Pairing
- Device identity on `connect`
- New device IDs require pairing approval
- Gateway issues device token for subsequent connects
- Local loopback can be auto-approved
- Signature payload v3 binds platform + deviceFamily

### Channel Abstraction

**Supported Channels:**
WhatsApp, Telegram, Slack, Discord, Signal, iMessage, WebChat, Matrix, Microsoft Teams, and more.

**DM Policy Options:**
- `pairing`: Unknown senders receive pairing code (default secure)
- `open`: Public inbound DMs require explicit opt-in

### Configuration via Zod Schemas

Gateway config validates:
- Agent settings
- Channel configurations
- Plugin slots (one memory plugin, one context engine)
- Auth profiles and model fallbacks

---

## Research Domain 3: Heartbeat + Cron Dual Engine

### Source Locations
- **Heartbeat:** https://docs.openclaw.ai/gateway/heartbeat
- **Cron:** https://docs.openclaw.ai/automation/cron-jobs
- **Comparison:** https://docs.openclaw.ai/automation

### Design Philosophy

| Aspect | Heartbeat | Cron |
|--------|-----------|------|
| **Role** | Continuous patrol guard | Strict calendar scheduler |
| **Timing** | Approximate (default 30min) | Exact (cron expressions) |
| **Session** | Full main-session context | Fresh (isolated) or shared |
| **Task Records** | ❌ Never created | ✅ Always created |
| **Delivery** | Inline in main session | Channel, webhook, silent |
| **Best For** | Inbox, calendar, notifications | Reports, reminders, background jobs |

### Heartbeat System

#### Configuration
```json5
{
  agents: {
    defaults: {
      heartbeat: {
        every: "30m",           // 0m to disable
        target: "last",         // none | last | channel-id
        directPolicy: "allow",   // allow | block
        lightContext: true,      // Only HEARTBEAT.md from bootstrap
        isolatedSession: true,   // Fresh session each run
        activeHours: {           // Optional time window
          start: "08:00",
          end: "24:00",
          timezone: "Asia/Kolkata"
        },
        includeReasoning: false, // Send separate Reasoning: message
        prompt: "Read HEARTBEAT.md...",
        ackMaxChars: 300         // Max chars after HEARTBEAT_OK
      }
    }
  }
}
```

#### Token Economics (Critical for 24/7 OpEx)
| Optimization | Effect |
|--------------|--------|
| `lightContext: true` | Only injects HEARTBEAT.md, significantly reduces tokens |
| `isolatedSession: true` | Fresh session = no conversation history sent |
| `activeHours` window | Skips heartbeats outside business hours |
| `HEARTBEAT_OK` silence | Dropped if ≤300 chars after strip |

#### Response Contract
- **Silence:** Reply `HEARTBEAT_OK` (at start or end of reply)
- **Alert:** Return only alert text (do NOT include HEARTBEAT_OK)
- **Strip logic:** `HEARTBEAT_OK` at start/end + ≤300 chars remaining = dropped

#### Default Prompt
```
Read HEARTBEAT.md if it exists (workspace context). Follow it strictly. 
Do not infer or repeat old tasks from prior chats. 
If nothing needs attention, reply HEARTBEAT_OK.
```

### Cron System

#### Job Persistence
- Definitions: `~/.openclaw/cron/jobs.json`
- Runtime state: `~/.openclaw/cron/jobs-state.json`
- Survives Gateway restarts

#### Schedule Types
| Kind | Flag | Example |
|------|------|---------|
| One-shot | `--at` | `2026-02-01T16:00:00Z` or `20m` |
| Interval | `--every` | `1h`, `30m` |
| Cron | `--cron` | `0 7 * * *` (7 AM daily) |

#### Execution Styles
| Style | Session | Use Case |
|-------|---------|----------|
| Main | `main` | Reminders, system events |
| Isolated | `cron:<jobId>` | Reports, background chores |
| Current | `current` | Context-aware recurring work |
| Custom | `session:custom-id` | Workflows building on history |

#### Isolated Cron Features
- **Best-effort cleanup:** Closes browser tabs/processes after completion
- **Stale ack guard:** Re-prompts if first result is interim status
- **MCP disposal:** Disposes bundled MCP runtime instances
- **Model switching:** Auto-retries with switched provider/model

#### Delivery Modes
```bash
--announce --channel telegram --to "-1001234567890"
--webhook https://example.com/hook
--none
```

#### Payload Options (Isolated Jobs)
- `--message`: Prompt text (required)
- `--model`: Override model
- `--thinking`: Thinking level
- `--light-context`: Skip workspace bootstrap
- `--tools exec,read`: Restrict tools

---

## Research Domain 4: Three-Tier Memory Architecture

### Source Location
- **Actual:** `src/memory/root-memory-files.ts` (ONLY ONE FILE)
- **Expected:** Full three-tier implementation (L1/L2/L3)

### ⚠️ Critical Discrepancy

**Research Mandate Expectation:**
```
L1 Working Memory: context window management
L2 Short-term Memory: daily notes (YYYY-MM-DD.md)
L3 Long-term Memory: SQLite FTS5 + vector embeddings + RRF
```

**Actual Implementation:**
```typescript
// src/memory/root-memory-files.ts
export const CANONICAL_ROOT_MEMORY_FILENAME = "MEMORY.md";
export const LEGACY_ROOT_MEMORY_FILENAME = "memory.md";

// Only handles:
// - Resolving canonical root memory path
// - Checking if root memory file exists
// - Skip logic for auxiliary paths
```

**Conclusion:** The three-tier memory architecture described in the research mandate does NOT exist in the current OpenClaw source. Memory is managed through:
1. **Workspace files** (MEMORY.md, daily notes)
2. **Bootstrap context** (injected into system prompt)
3. **Session transcript** (conversation history)
4. **External plugins** (likely for advanced memory like sqlite-vec)

### Actual Memory Mechanisms

#### 1. System Prompt Injection Order
```
Base prompt
    ↓
Skills prompt
    ↓
Bootstrap context (AGENTS.md, SOUL.md, USER.md, etc.)
    ↓
Per-run overrides
```

#### 2. Compaction (Conversation Summarization)
- Triggered when context window nears limit
- Emits `compaction` stream events
- Resets in-memory buffers on retry
- See: https://docs.openclaw.ai/concepts/compaction

#### 3. Session Transcript
- Process-aware, file-based write lock
- Prevents concurrent writes to session file
- Non-reentrant by default

---

## Research Domain 5: Self-Improvement Ecosystem

### Source Location
- **Skills:** `.agents/skills/` on GitHub
- **Docs:** https://docs.openclaw.ai/tools/skills

### Skills Architecture

**Skills are markdown files** (`SKILL.md`) injected into system prompt to teach the agent:
- When and how to use tools
- Behavioral constraints
- Step-by-step guidance

### Bundled Skills (from GitHub)

| Skill | Purpose |
|-------|---------|
| `openclaw-ghsa-maintainer` | GitHub Security Advisories maintenance |
| `openclaw-parallels-smoke` | Smoke testing |
| `openclaw-pr-maintainer` | PR management |
| `openclaw-qa-testing` | QA testing workflows |
| `openclaw-release-maintainer` | Release management |
| `openclaw-secret-scanning-maintainer` | Secret scanning |
| `openclaw-test-heap-leaks` | Heap leak detection |
| `openclaw-test-performance` | Performance testing |
| `optimizetests` | Test optimization |
| `security-triage` | Security issue triage |
| `tag-duplicate-prs-issues` | Duplicate detection |

### Skill Creation

Skills can be created by the agent itself:
- Write `SKILL.md` to workspace or shared folder
- Skills auto-discovered on startup
- Can include scripts, agents config, and documentation

### Self-Improvement Mechanisms

1. **Skill Autonomy:**
   - Agent can write new SKILL.md files
   - Can update existing skills based on experience
   - Skills persist across sessions

2. **Hook System for Self-Observation:**
   - `agent_end`: Inspect run metadata, self-correct
   - `before_compaction`: Observe and annotate compaction cycles
   - `after_tool_call`: Learn from tool execution results

3. **Standing Orders:**
   - Permanent operating authority in workspace files
   - Injected into every session automatically
   - Combine with cron for time-based enforcement

4. **Memory Persistence:**
   - `MEMORY.md` for curated long-term memory
   - Daily notes (`memory/YYYY-MM-DD.md`) for raw logs
   - Agent updates memory files autonomously

---

## Architecture Gaps & Discrepancies

### vs. Research Mandate Expectations

| Mandate Component | Actual Status | Notes |
|------------------|---------------|-------|
| `agents/pi-embedded-runner/run/attempt.ts` | Not found at expected path | pi-agent-core is external runtime |
| `src/memory/` with L1/L2/L3 | ❌ Only 1 file | Three-tier memory not implemented |
| `openclaw-superpowers` skills | ❌ Not found | Skills ecosystem exists differently |
| sqlite-vec RRF | ❌ Not in core | Likely external plugin |

### What Actually Exists

1. **pi-agent-core:** External runtime called via `runEmbeddedPiAgent`
2. **Plugin System:** Extensible via npm packages
3. **Skills System:** Markdown-based, agent-writable
4. **Memory:** File-based (MEMORY.md, daily notes)
5. **Hooks:** Comprehensive event lifecycle

---

## Recommended SOUL.md Design Principles

Based on research findings:

### 1. Autonomous Operation
- Use `HEARTBEAT_OK` for silent cycles
- Use `lightContext: true` to reduce token costs
- Configure `activeHours` to match human patterns
- Use isolated sessions for heavy background work

### 2. Memory Strategy (Actual Architecture)
- **Long-term:** MEMORY.md (curated, agent-updated)
- **Short-term:** Daily notes (raw logs)
- **Context:** Bootstrap files injected into system prompt
- **Session:** Full conversation history in session transcript

### 3. Self-Improvement Loop
```
Heartbeat → Self-review (agent_end hook)
    ↓
Update MEMORY.md with lessons learned
    ↓
Write new skills if repeated patterns found
    ↓
Standing orders enforce persistent behaviors
```

### 4. Tool Execution Discipline
- Use hooks for observability (`before_tool_call`, `after_tool_call`)
- Log all significant actions to daily notes
- Verify outputs before marking complete

### 5. Scheduling Strategy
- **Heartbeat:** Every 30min for routine monitoring
- **Cron:** Precise schedules for reports/reminders
- **Never block** main session with heavy jobs (use isolated)

### 6. Error Handling
- Leverage timeout mechanisms (agent runtime, LLM idle)
- Use AbortSignal for graceful cancellation
- Monitor Gateway health via `health` RPC
- Implement retry logic via cron for failed jobs

---

## Next Steps

1. **Design SOUL.md** incorporating these findings
2. **Create HEARTBEAT.md** with proactive checklist
3. **Set up Standing Orders** in AGENTS.md
4. **Configure Heartbeat** with `lightContext: true` and appropriate `activeHours`
5. **Implement Self-Improvement Loop** using hooks + MEMORY.md updates

---

## References

- Agent Loop: https://docs.openclaw.ai/concepts/agent-loop
- Architecture: https://docs.openclaw.ai/concepts/architecture
- Queue: https://docs.openclaw.ai/concepts/queue
- Heartbeat: https://docs.openclaw.ai/gateway/heartbeat
- Cron: https://docs.openclaw.ai/automation/cron-jobs
- Automation: https://docs.openclaw.ai/automation
- Skills: https://docs.openclaw.ai/tools/skills
- Source: https://github.com/openclaw/openclaw

---

*Research conducted: 2026-04-24*
*Prepared for: 100× Autonomous Agent SOUL.md design*