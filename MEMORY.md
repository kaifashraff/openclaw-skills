# MEMORY.md — Long-Term Memory

## System Setup
- **Gateway:** openclaw-gateway, running on AWS (Ubuntu)
- **Identity:** JARVIS (J.A.I.S. — Jarvis Autonomous Intelligence System)
- **Owner:** Kaif Ashraf, Ahmedabad
- **Plugins loaded:** acpx, browser, device-pair, phone-control, talk-voice, telegram
- **Model:** minimax-portal/MiniMax-M2.7 (LOCKED — never change)
- **53 models** configured across Groq, Mistral, Google, Crof-AI, SambaNova, Cerebrus, Novita
- **6 agents** created: digital-marketer, performance-marketer, deep-research, openclaw-manager, youtube-creator, social-media-manager

## Tech Landscape (Key Context)
- **RAM/DRAM shortage** — Global shortage likely through 2027-2030; affects AI hardware pricing & availability
- **Palantir** — Culture-war adjacent rhetoric, ideological positioning (ICE contracts, "defender of the West")
- **Uber** — "Assetmaxxing" era, fleet optimization push
- **OpenAI** — Lost Sora head (Bill Peebles) and VP of AI for Science — notable departures
- **Military AI** — Northrop Grumman Talon IQ can hot-swap AI models mid-flight (real-time payload flexibility)
- **Influence ops** — AI-generated influencer farms (cheap avatars, coordinated messaging) lowering bar for state-level manipulation

## Config Status
- ✅ All 53 models configured successfully (providers fixed)
- ✅ Gateway watchdog deployed (auto-restart every 1 minute)
- ✅ Cron jobs active for monitoring

## Lessons & Decisions
- Gateway restarts cleanly via SIGUSR1 — safe to restart without downtime concerns
- Telegram falls back to IPv4 on ETIMEDOUT — recoverable network quirk, not an alert
- `punycode` module deprecated in Node.js — cosmetic warning, not critical
- Research agent markers in daily-research.md must use unique timestamps (not static strings)

## Health Baseline
- Memory: ~57% used (normal under cron load)
- Disk: 40% used
- Load: 0.48/0.25/0.23 (healthy)
- Gateway memory peak: ~1.1 GB (higher than previous runs — monitor)

## New Research (2026-04-19 evening — additions after 19:03)
- **Vercel breach** — internal systems confirmed breached, no customer data impact reported yet
- **Notion leak** — email addresses of all public page editors exposed via data exposure bug
- **Bromine chokepoint** — Middle East bromine supply chain at risk; could halt memory chip production
- **Humanoid robots** — Honor robot won Beijing half-marathon in 50:26 (autonomous), beating human world record 57:31; massive jump from 2:40 last year
- **Chiral phonons** — new computing pathway discovered (atomic vibrations directly transfer motion to electrons)
- **AI apps for PC** — wave of AI-native desktop apps emerging; PC becoming AI platform battleground
- **Ars Technica / petawatt laser** — inside a shot day at America's most powerful laser facility
- **Northrop Grumman Talon IQ** — hot-swaps AI models mid-flight in testbed aircraft; real-time payload flexibility for autonomous combat
- **Google Gemini "less awkward"** — Google publicly acknowledged tuning Gemini to fix weird/off-putting personality issues
- **DeepMind AlphaFold** — now predicts proteome-scale protein dynamics; major drug discovery step
- **"Intelligence on tap killed the expert"** — viral thread: AI eroding expert value; AI-fluent experts become more valuable
- **Europe jet fuel shortage** — ~6 weeks of jet fuel left (BBC/HN); geopolitical downstream effect
- **ChatGPT 5.4 Pro adaptive thinking** — users suspect standard mode nerfed vs thinking mode to save compute
- **Blue Origin New Glenn failure** — 3rd launch placed satellite in wrong orbit; first major failure of Bezos' heavy-launch system
- **AI models flunk basic science test** — current models still struggle with multi-step causal reasoning

## New Research (2026-04-19 evening — additions after 19:13)
- **Uber's $3.4B AI budget crisis** — Despite massive AI spending, Uber's CTO says AI push hitting budget/execution walls. Brutal cost of AI at scale even for giants.

## Persistent Issues
- `allowInsecureAuth=true` — still active, security flag not resolved
- Config errors: mistral, cerebrus, silicon, novita, sambanova have invalid `api` type values — run `openclaw doctor --fix`
- `crof-ai` provider: HTTP 401 Invalid Token (expired/revoked API key) — fallback to MiniMax-M2.7 working fine, no user impact
- **RSS feeds stale/404** — sciencedaily, technologyreview, nature.com returning older cached content or 404s (Sunday evening quiet cycle, not a config issue)

---
*Last updated: 2026-04-19 19:23*
