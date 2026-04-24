# Parallel Web Search MCP

**Date:** 2026-04-24
**Source:** Parag Agrawal's tweet (@paraga)

## What is it?
- Free web search MCP (Model Context Protocol) server
- URL: `search.parallel.ai/mcp`
- **No auth needed** - completely free

## Purpose
Provides web search capabilities for AI coding agents:
- Claude Code
- Codex CLI
- Any MCP-supported tool or agent

## Configuration

### For Claude Code:
```
add free search.parallel.ai/mcp - no auth needed
add permissions.allow for both tools
deny native web search and fetch
```

### For Codex CLI:
```
edit ~/.codex/config.toml to add:
web_search = "disabled"
add the free mcp search.parallel.ai/mcp - no auth needed
```

## Key Concepts
- MCP = Model Context Protocol (Anthropic's open standard)
- Allows AI models to connect to external tools
- Replaces native web search/fetch in AI agents

## Integration with OpenClaw

**STATUS:** Not directly compatible
- OpenClaw uses its own tool/plugin system
- MCP servers are designed for Claude Code, Codex CLI
- OpenClaw doesn't appear to have MCP client support

**POTENTIAL SOLUTIONS:**
1. Check if Parallel has REST API (not just MCP)
2. Create OpenClaw skill using Parallel's HTTP API
3. See if OpenClaw plugins can bridge MCP tools

## Action Items
- [ ] Research Parallel's API (REST vs MCP only)
- [ ] Check if OpenClaw has MCP bridge capability
- [ ] Create skill if REST API available