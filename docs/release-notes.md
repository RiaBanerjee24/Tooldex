# Release Notes

## 1.0.2

**Stdio servers now require your explicit approval before Tooldex will execute them.**

Listing a stdio MCP server's tools means running its `command` — that's inherent to the protocol. Previously Tooldex did this immediately on discovery, for every server, with no consent step. A malicious or compromised config could achieve code execution the moment you pointed Tooldex at a directory. That gap is closed.

- **Approval gate** — any stdio server with no recorded decision is presented interactively on `tooldex run` (Yes / Yes for all stdio servers / No), or approved/denied from the Servers view in the UI. Decisions are cached in `~/.tooldex/trust_store.json`, pinned to that server's exact `command`/`args`/`env` — editing the invocation later is treated as a new, unapproved server. `--trust-all-stdio` and `tooldex trust <name>` / `tooldex untrust <name>` are available for non-interactive use.
- **Drift detection** — an approval doesn't trust a server forever. Every subsequent run re-checks it two ways before executing anything: the local script file(s) it runs (hashed, covering the entry point's whole directory tree — not just the one file named in the config, so a sibling module it imports is covered too) and the tool list itself (name/description/schema). Either changing means the server is **not** re-executed on the strength of the stale approval — Tooldex serves the last-known tool list instead and flags it `changed`, until you explicitly re-approve.
- **Reinstalling Tooldex clears trust decisions.** Trust data lives outside the installed package, so a deliberate uninstall/reinstall now gets a clean slate instead of silently inheriting every prior approval.
- New API: `POST`/`DELETE /api/servers/{id}/trust`. New field: `trust_status` on every server.
- HTTP/SSE servers are unaffected — they don't fork a local process, so there's nothing to gate.

See [Trust Gate](index.md#trust-gate-stdio-execution-approval) for the full write-up.

---

## 1.0.1 and earlier

Initial public releases:

- MCP autodiscovery across Claude Code, Cursor, Codex, VSCode, Copilot, Gemini (Antigravity), Agents, and Docker MCP Toolkit — no manual configuration.
- Unified UI and REST API over every discovered server's tool surface.
- Automatic YARA security scanning on every discovery/rescan (via [Cisco's mcpscanner](https://github.com/cisco-ai-defense/mcp-scanner)), plus opt-in AI (LLM-as-judge) scanning per server.
- MIT licensed.
