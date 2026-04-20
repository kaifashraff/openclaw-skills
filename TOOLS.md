# TOOLS.md — Infrastructure & Local Setup

This file contains the actual specifics of my environment. What cameras, SSH hosts, APIs, and systems I'm connected to.

---

## System Architecture

### Gateway
- **Service:** openclaw-gateway
- **Host:** AWS EC2 (Ubuntu)
- **Instance:** ip-172-31-43-229.eu-north-1.compute.internal
- **Auto-restart:** Watchdog deployed (SIGUSR1 every 1 minute)

### SSH Access
- AWS EC2 SSH available for gateway management
- Host: AWS instance IP (internal AWS DNS above)

### API Providers Configured
- **MiniMax-M2.7** — Primary model (LOCKED, never change)
- **Groq** — Llama 3.3 70B, Llama 3.1 8B, Mixtral 8x7B, Gemma 2 9B
- **Mistral** — Large, Medium, Small
- **Google** — Gemini 1.5 Flash, Pro, 2.0 Flash
- **Crof-AI** — GLM-4, GLM-4-Vision, DeepSeek V3.2, Gemma 4 31B
- **SambaNova** — Llama 3.1 70B, 405B
- **Cerebrus** — Cerebrus 3.0
- **Novita** — Nemotron 70B
- **52 total models** across all providers

---

## Connected Services

### Telegram
- **Bot Token:** `telegram:direct:5998285479`
- **Status:** HTTP 401 error since Apr 19 ~19:29 UTC — token may be expired
- **Channel:** Primary communication with Kaif

### Plugins Loaded
- acpx
- browser
- device-pair
- phone-control
- talk-voice
- telegram

---

## Skills Installed (82 total)

Key skills for operations:
- **clawhub** — Search and install new skills from clawhub.ai
- **github** — GitHub operations
- **weather** — Weather checks
- **healthcheck** — System health monitoring
- **node-connect** — Node connection troubleshooting
- **taskflow** — Multi-step task management
- **tmux** — Session management
- **video-frames** — Video processing

---

## Project Paths

- **Workspace:** /home/ubuntu/.openclaw/workspace
- **Laqab v2:** /home/ubuntu/.openclaw/workspace/laqab-v2
- **Memory:** /home/ubuntu/.openclaw/workspace/memory

---

## Key Files

| File | Purpose |
|------|---------|
| SOUL.md | Entity philosophy, who I am |
| IDENTITY.md | Name, mission, character |
| HEARTBEAT.md | Proactive behaviors |
| USER.md | Kaif's info and context |
| MEMORY.md | Long-term memory |
| AGENTS.md | Workspace conventions |
| TOOLS.md | This file |

---

## Cron Jobs

Active monitoring:
- Gateway watchdog (1 min interval)
- System health checks
- Research agents (background)

---

## Notes

- **Gateway memory peak:** ~1.1 GB (monitor for increases)
- **Disk usage:** ~40% (healthy)
- **Load average:** 0.48/0.25/0.23 (healthy)

---

*Last updated: 2026-04-20*
