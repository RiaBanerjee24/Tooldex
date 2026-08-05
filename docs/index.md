# Tooldex

Tooldex autodiscovers MCP servers configured across your AI clients — Claude Code, Cursor, Codex, Gemini (Antigravity), Agents, Docker MCP Toolkit — and surfaces them in a unified UI. No manual config. Run it from any project directory and it finds everything.

---

## Requirements

- Python 3.10 or later
- At least one supported MCP client configured (Claude Code, Cursor, Codex, Gemini, or Docker MCP Toolkit)

---

## Installation

```bash
pip install tooldex
```

Verify:

```bash
tooldex --version
```

---

## Quick Start

```bash
cd your-project
tooldex run
```

Tooldex scans config files, probes each discovered server for its tool surface, and opens the UI. The startup banner shows where to connect:

```
  ╔══════════════════════════════════════════════════╗
  ║         tooldex  v0.1.1                         ║
  ╠══════════════════════════════════════════════════╣
  ║  Servers  12                                     ║
  ║  Tools    187                                    ║
  ╠══════════════════════════════════════════════════╣
  ║  →  http://127.0.0.1:8282                        ║
  ╚══════════════════════════════════════════════════╝
```

To see the discovery summary without starting the server:

```bash
tooldex run --no-serve
```

---

## How Discovery Works

When you run `tooldex run`, the following happens in order:

1. **Config scan** — Tooldex reads every known MCP config location for the current directory. Each found server gets a qualified ID in the form `{client}:{server_name}` so servers from different clients never collide.

2. **Live probe** — Each discovered server is contacted concurrently. Tooldex calls `tools/list` on it and records which tools it exposes, and any errors.

3. **Deduplication** — If the same server name appears in multiple clients (e.g., `browserbase` in both Claude Code and Cursor), both are retained as separate entries under their respective clients.

4. **UI** — A local web server starts and serves the unified view.

---

## Config File Locations

Tooldex checks all of the following on every run. Files that do not exist are skipped silently.

### Claude Code

| Scope | Path |
|---|---|
| Global | `~/.claude.json` |
| Project | `<project>/.claude/mcp.json` |
| Project (flat) | `<project>/.claude.json` |

### Cursor

| Scope | Path |
|---|---|
| Global | `~/.cursor/mcp.json` |
| Project | `<project>/.cursor/mcp.json` |

### Codex CLI

| Scope | Path |
|---|---|
| Global | `~/.codex/config.toml` |
| Project | `<project>/.codex/config.toml` |

### MCP JSON (shared / team configs)

| Scope | Path |
|---|---|
| Global | `~/.mcp.json` |
| Project | `<project>/.mcp.json` |
| Project (bare) | `<project>/mcp.json` |

### Agents

| Scope | Path |
|---|---|
| Global | `~/.agents/mcp.json` |
| Global | `~/.agents/.mcp.json` |
| Project | `<project>/.agents/mcp.json` |
| Project | `<project>/.agents/.mcp.json` |

### Gemini (Antigravity IDE)

| Scope | Path |
|---|---|
| Global | `~/.gemini/antigravity/mcp_config.json` |

### Docker MCP Toolkit

Tooldex reads all Docker MCP profiles via `docker mcp profile ls`. No additional configuration is needed.

Project-scoped paths are discovered by walking up the directory tree from `cwd` until the home directory. Both `mcp.json` and `.mcp.json` are checked at every level of the walk.

---

## MCP Config Format

All JSON-based clients use the same `mcpServers` structure. Tooldex understands both `stdio` (command-based) and `http`/`sse` (URL-based) transports.

**Comments are supported.** Tooldex parses JSON5, so `//` line comments and `/* block */` comments in config files are handled gracefully.

### stdio server

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/user"],
      "env": {
        "SOME_VAR": "value"
      }
    }
  }
}
```

### HTTP / SSE server

```json
{
  "mcpServers": {
    "browserbase": {
      "type": "http",
      "url": "https://mcp.browserbase.com/mcp"
    },
    "remote-api": {
      "type": "sse",
      "url": "https://api.example.com/mcp/sse"
    }
  }
}
```

### Codex (`~/.codex/config.toml`)

```toml
[mcp_servers.filesystem]
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem", "."]

[mcp_servers.github]
type = "http"
url = "https://api.githubcopilot.com/mcp/"
```

### What Tooldex Detects

For each config file found:

| Field | Description |
|---|---|
| `status` | `found` / `not_found` / `empty` / `parse_error` / `read_error` |
| `server_ids` | List of server names parsed from the file |
| `in_file_duplicates` | Server names that appeared more than once as JSON keys |

For each server probed:

| Field | Description |
|---|---|
| `status` | `found` / `timeout` / `connection_failed` / `protocol_error` / `missing_command` |
| `tools` | Names, descriptions, and input schemas of every tool the server exposes |
| `duration_ms` | Probe wall time |
| `error` | Human-readable failure message; includes install hints for missing runtimes (`uvx`, `npx`, `docker`, etc.) |

---

## CLI Reference

```
tooldex [OPTIONS] COMMAND [ARGS]
```

### Global options

| Flag | Description |
|---|---|
| `--version`, `-V` | Print version and exit |
| `--help`, `-h` | Show help |

### `tooldex run`

| Flag | Default | Description |
|---|---|---|
| `--port`, `-p` | `8282` | Starting port. Increments automatically if occupied. |
| `--host` | `127.0.0.1` | Interface to bind the UI server to. |
| `--no-serve` | off | Print discovery summary and exit without starting the server. |
| `--json` | off | Print discovery result as JSON and exit. Implies `--no-serve`. Does not probe servers. |
| `--timeout` | `10.0` | Per-server probe timeout in seconds. |
| `--concurrency` | `8` | Maximum concurrent server probes. |
| `--no-probe <name>` | — | Skip probing a specific server by name. Repeatable. |
| `--config <path>` | — | Additional MCP config file to include. Repeatable. |
| `--no-cache` | off | Bypass the probe cache and re-probe every server live. |

#### Examples

```bash
# Discover and launch UI
tooldex run

# Custom port and host
tooldex run --port 9000 --host 0.0.0.0

# Just print what was found, don't start the server
tooldex run --no-serve

# Skip slow or broken servers during probing
tooldex run --no-probe node-api-docs --no-probe local-mcp

# Pipe the discovery result into jq
tooldex run --json | jq '.duplicates'
```

---

## JSON Output

`tooldex run --json` prints a single JSON object to stdout and exits. No servers are probed.

```json
{
  "sources": [
    {
      "client": "claude_code_user",
      "path": "/home/user/.claude.json",
      "status": "found",
      "server_ids": ["filesystem", "github"],
      "in_file_duplicates": []
    }
  ],
  "servers": {
    "claude_code_user:filesystem": {
      "name": "filesystem",
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/user"]
    }
  },
  "duplicates": [
    "\"filesystem\" in cursor_user is also configured in claude_code_user"
  ]
}
```

---

## Security Scanning

Powered by [Cisco's MCP Scanner](https://github.com/cisco-ai-defense/mcp-scanner) (`mcpscanner` on PyPI) — Tooldex wraps it, it doesn't reimplement it.

### YARA scan (always on)

Runs automatically as part of every discovery and rescan, for every server. Local, free, no API key required, no configuration needed.

| Env var | Description | Default |
|---|---|---|
| `MCP_SCANNER_CONCURRENCY` | Maximum concurrent YARA scan calls. Distinct from `run`'s `--concurrency` flag, which controls tool-*probing* concurrency, not scanning. | `8` |

### AI security scan (LLM-as-judge, opt-in)

Tooldex's AI security scan is powered by Cisco AI Defense's open-source mcpscanner SDK, running entirely locally — the only network call it makes is to whichever LLM provider you configure.

An LLM reviews each tool's name, description, and input schema for malicious intent (data exfiltration, prompt injection, tool poisoning, etc.). Unlike YARA, this never runs automatically — it's triggered manually per server, from the UI ("AI security scan" button) or via `POST /api/servers/{id}/llm-scan/`.

Requires `TOOLDEX_LLM_API_KEY` at minimum. Without it, the AI security scan is simply unavailable — YARA scanning is unaffected.

| Env var | Legacy fallback | Description | Default |
|---|---|---|---|
| `TOOLDEX_LLM_API_KEY` | `MCP_SCANNER_LLM_API_KEY` | API key for your LLM provider (OpenAI, Anthropic, etc). Required to enable the AI security scan. | *(unset — scan disabled)* |
| `TOOLDEX_LLM_MODEL` | `MCP_SCANNER_LLM_MODEL` | Model to use, e.g. `gpt-4o`, `claude-3-5-sonnet-latest` | `gpt-4o` |
| `TOOLDEX_LLM_RATE_LIMIT_DELAY` | `MCP_SCANNER_LLM_RATE_LIMIT_DELAY` | Seconds to wait between LLM calls | `2.0` |
| `TOOLDEX_LLM_TEMPERATURE` | `MCP_SCANNER_LLM_TEMPERATURE` | Sampling temperature | `1.0` |
| `TOOLDEX_LLM_MAX_RETRIES` | `MCP_SCANNER_LLM_MAX_RETRIES` | Max retries on a failed LLM call | `6` |
| `TOOLDEX_LLM_BASE_URL` | `MCP_SCANNER_LLM_BASE_URL` | Custom endpoint (Azure OpenAI, self-hosted Ollama/vLLM/LocalAI, etc.) | *(unset)* |
| `TOOLDEX_LLM_API_VERSION` | `MCP_SCANNER_LLM_API_VERSION` | API version, e.g. required by Azure OpenAI | *(unset)* |
| `TOOLDEX_LLM_TIMEOUT` | `MCP_SCANNER_LLM_TIMEOUT` | Per-request LLM timeout in seconds | `30` |

Every `TOOLDEX_LLM_*` var also accepts its original mcpscanner name (`MCP_SCANNER_LLM_*`) as a fallback if the `TOOLDEX_LLM_*` one isn't set — an existing mcpscanner-native setup keeps working un-migrated. Using a legacy name prints a one-time notice on the CLI pointing at the rename.

`MCP_SCANNER_API_KEY` (Cisco's separate cloud API) and `VIRUSTOTAL_API_KEY` are **not** supported — Tooldex only uses mcpscanner's local YARA and LLM analyzers.

**Model support:** any [LiteLLM](https://docs.litellm.ai/)-compatible model string works, since the LLM analyzer runs through LiteLLM internally — there's no fixed allowlist. `TOOLDEX_LLM_MODEL` defaults to `gpt-4o` if unset.

**Caching:** results are cached per-server, per-tool at `~/.tooldex/llm_scan_cache.json`, fingerprinted by a hash of each tool's name, description, and input schema — a cache entry is invalidated automatically the moment that tool's identity changes, with no TTL otherwise.

- Clicking "AI security scan" (or its rerun icon) always forces a fresh LLM call per tool, bypassing any cache hit — but still writes the result back to the cache.
- On `tooldex run` startup, and on every page load, the last cached verdict for each server is shown immediately with zero LLM calls made.
- The clear-cache (trash) icon removes all cached entries for a server and resets its displayed state back to "not yet scanned."
- Rescanning a server (or "Rescan All") while an AI security scan is in flight on it is blocked with `409 llm_scan_running` unless forced, in which case the running scan is aborted first.

---

## API Endpoints

When the server is running (default `http://127.0.0.1:8282`). All endpoints respond with or without a trailing slash.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health/` | `status`, current `timestamp`, and `uptime_seconds` since the server started |
| `GET` | `/api/servers/` | All MCP servers with `total_servers`, `total_tools`, `scanned_at`. Per server: `tool_count`, `source_file`, `has_llm_cache`, and the `security_*` fields below |
| `GET` | `/api/servers/{id}/` | Single server with full tool detail |
| `POST` | `/api/servers/{id}/rescan/` | Re-probe a single server and update its tools in place. `force=true` aborts an in-flight AI security scan on this server first; otherwise returns `409 {"error": "llm_scan_running"}` while one is running |
| `POST` | `/api/servers/{id}/llm-scan/` | Start the AI security scan for one server as a background job. `force` (default `true`) skips the cache and forces fresh LLM calls; results are cached either way |
| `GET` | `/api/servers/{id}/llm-scan/status/` | Poll progress (`scanned`/`total`) and outcome of the AI security scan job for this server |
| `POST` | `/api/servers/{id}/llm-scan/stop/` | Signal a running AI security scan to stop |
| `POST` | `/api/servers/{id}/llm-scan/invalidate-cache/` | Clear cached AI scan results for this server and reset its displayed state to "not yet scanned" |
| `GET` | `/api/files/` | All config files that were scanned: path, client, status, server IDs found, any parse errors |
| `POST` | `/api/rescan/` | Full rediscovery — re-reads all configs and re-probes every server. Returns `{"status": "already_scanning"}` if a rescan is already running. |
| `GET` | `/api/rescan/stream/` | Same rediscovery as above, streamed as Server-Sent Events (one per server, then `done`). `force=true` aborts any in-flight AI security scans fleet-wide first; otherwise yields `{"type": "blocked", "servers": [...]}` and stops |

**Per-server security fields** (on `/api/servers/` and `/api/servers/{id}/`):

| Field | Description |
|---|---|
| `security_findings` | List of findings from the last scan: `{tool_name, severity, analyzer, threat_category, summary}` |
| `security_risk` | Worst severity across all findings — `HIGH` / `MEDIUM` / `LOW` / `INFO` / `null` |
| `security_scanned` | `true` once this server has been included in a scan run |
| `security_llm_scanned_at` | UTC ISO timestamp of the last AI security scan, if any |
| `security_llm_new_findings` | Findings from the last AI scan not present in the one before it |
| `security_llm_cache_hits` | Of the last AI scan's tools, how many were served from cache rather than a real LLM call |
| `security_llm_last_scan_total` | Total tools attempted in the last AI scan (cache hits + real calls) |
| `has_llm_cache` | Whether any cached AI scan result exists for this server (drives the clear-cache icon) |

---

## Architecture

### Project Structure

```
tooldex/
├── __init__.py              # __version__ via importlib.metadata
├── cli.py                   # Typer CLI — `run` command definition only
├── _ports.py                 # find_free_port()
├── preferences.py            # load_prefs()/save_pref() — ~/.tooldex/preferences.json
├── _spinner.py                # Spinner — "tooldexing  3s" terminal spinner
├── _cli_output.py            # print_banner(), print_summary(), result_as_json()
├── settings.py               # debug flag
│
├── api/
│   ├── app.py                # FastAPI factory, CORS, SPA mount
│   ├── redact.py              # redact_server(), friendly_path() — strips secrets from API responses
│   ├── llm_jobs.py            # LlmJudgeJob tracking/cancellation, shared by servers.py + health.py
│   └── routers/
│       ├── health.py          # GET /api/health/
│       ├── rescan.py          # POST /api/rescan/, GET /api/rescan/stream/
│       ├── servers.py         # GET /api/servers/, /api/servers/{id}/, rescan + llm-scan endpoints
│       └── files.py           # GET /api/files/
│
├── scanner/
│   ├── __init__.py          # Re-exports the public surface (scan_servers, run_llm_judge_scan, ...)
│   ├── config.py            # build_config() — TOOLDEX_LLM_* env vars, legacy MCP_SCANNER_LLM_* fallback
│   ├── yara_scan.py         # scan_servers() — automatic, always-on fleet-wide YARA scan
│   ├── llm_judge.py         # run_llm_judge_scan() (opt-in) + hydrate_llm_cache()
│   └── llm_cache.py         # Persistent per-tool AI-scan cache (~/.tooldex/llm_scan_cache.json)
│
└── core/
    ├── models/
    │   ├── manifest.py      # TooldexManifest, TooldexMetadata
    │   └── server.py        # MCPServer, DiscoveredToolLite
    │
    ├── parsers/
    │   └── parser.py        # Module-level singleton: get_parser(), init_parser_from_manifest()
    │
    └── discovery/
        ├── config_detector.py   # detect_all(), qualified IDs
        ├── _paths.py            # Platform-aware path resolvers
        ├── _readers.py          # read_json(), read_claude_json(), read_codex_toml()
        ├── _parsers.py          # Dict → MCPServer, env var substitution
        ├── results.py           # DiscoverySource, ToolDiscoveryResult
        ├── mcp_client.py        # Async prober: stdio / http / sse
        ├── tool_discovery.py    # Sync wrappers, asyncio bridge
        ├── to_manifest.py       # Discovery output → TooldexManifest, merge_security_findings()
        ├── _docker_mcp.py       # Docker MCP profile reader
        ├── _status_claude.py    # Enrich via `claude mcp list`
        ├── _status_codex.py     # Enrich via `codex mcp list`
        └── _status_cursor.py    # Enrich via `cursor-agent mcp list-tools`
```

### Discovery Pipeline

**Config detection** (`config_detector.py`) reads config files in priority order: custom `--config` paths first, then Claude Code global, Codex, Cursor, MCP JSON, and Docker MCP Toolkit profiles. Every server gets a qualified ID (`{client}:{server_id}`) so cross-client name collisions are preserved as separate entries rather than clobbered.

**Live probing** (`mcp_client.py`) is fully async. `probe_server()` routes by transport — `stdio` spawns a subprocess via the MCP SDK, `http`/`sse` connect via the respective MCP client. A `FileNotFoundError` on the server command produces a `connection_failed` result with a human-readable hint (e.g. `'uvx' is not installed — install uv: https://astral.sh/uv`). `probe_all()` runs probes concurrently under a `Semaphore` (default concurrency: 8).

**Manifest assembly** (`to_manifest.py`) attaches each `ToolDiscoveryResult` to its `MCPServer` as `discovered_tools`, `probe_status`, and `probe_error`. `probe_status` is the canonical failure signal used by the UI — it takes precedence over `connection_status`, which is a secondary signal from optional agent CLI enrichment.

### Rescan Safety

The `POST /api/rescan` endpoint uses two mechanisms to stay safe under concurrent requests:

- **`asyncio.Lock`** — if a rescan is already running, the endpoint returns `{"status": "already_scanning"}` immediately. No caller ever waits.
- **`_silenced(fn)`** — redirects fd 1 and fd 2 to `/dev/null` for the duration of `detect_all()` and `list_tools_for_all()` to suppress subprocess noise, then restores them for the structured terminal output that follows.

All subprocess calls pass `stdin=subprocess.DEVNULL` to prevent interactive permission prompts from inheriting the terminal's stdin and blocking the request.

### Security Scanning Pipeline

**YARA** (`scan_servers()` in `scanner/yara_scan.py`) runs as part of every discovery and rescan, for every server, with no opt-in required — it's the only analyzer in `active_analyzers()`. `scanner/config.py` builds the shared mcpscanner `Config` (env vars + legacy fallback) that both YARA and the LLM judge use.

**AI security scan** (`run_llm_judge_scan()` in `scanner/llm_judge.py`) is a separate, manual path invoked only via the `/api/servers/{id}/llm-scan/*` endpoints (handlers in `api/routers/servers.py`, job tracking/cancellation in `api/llm_jobs.py`), never from the automatic fleet-wide scan. Per tool, it checks `llm_cache` first (unless `force=True`), races the LLM call against a caller-supplied `cancel_event` so a stop request lands almost immediately instead of waiting out an in-flight request, and writes every real result back to the cache regardless of `force`.

Because mcpscanner's own `Scanner` swallows LLM call failures internally (logs an error, then reports the tool as having no findings), a bad or expired API key would otherwise look identical to "no vulnerabilities found." `run_llm_judge_scan()` guards against this with an upfront one-token auth check plus a log-capture handler during the real scan loop, both mapping known HTTP status codes (401/403/429/etc.) to a `ValueError` instead of a false-clean result.

**Caching** (`llm_cache.py`) is a flat JSON file at `~/.tooldex/llm_scan_cache.json`, keyed by `f"{server_id}::{tool_name}"`. Each entry stores a hash of the tool's name/description/input_schema alongside its verdict; a hash mismatch on lookup is treated as a miss. `hydrate_llm_cache()` (in `scanner/llm_judge.py`) reconstructs each server's `security_llm_*` display fields from this cache at manifest-build time — called from both `tooldex run` startup and `POST /api/rescan/` — so cached results survive a process restart with no LLM calls made. Both `hydrate_llm_cache()` and the `llm-scan` route handlers share one `merge_security_findings()` helper (in `core/discovery/to_manifest.py`) to replace a server's LLM findings and recompute its worst severity.

### Adding a New MCP Client

**1. Add path resolvers** in `_paths.py` and register in `CLIENT_PRIORITY`:

```python
def windsurf_user_path() -> Path:
    return Path.home() / ".windsurf" / "mcp.json"

def windsurf_project_path(cwd: Path) -> Optional[Path]:
    return walk_up_for(cwd, (".windsurf", "mcp.json"))
```

**2. Register in `build_plan()`**:

```python
("windsurf_project", lambda: windsurf_project_path(cwd)),
("windsurf_user",    windsurf_user_path),
```

**3. Wire up the UI** — add to `CLIENT_META` and `GROUP_ORDER` in `ui/src/components/servers/serverHelpers.jsx`, then rebuild:

```bash
cd tooldex/ui && npm run build
```

**4. Add CLI display names** in `_cli_output.py` if the raw client ID is not user-friendly.

**5. Add a status enrichment module** (optional) — follow the pattern of `_status_cursor.py` and add a call site in `detect_all()`.

**6. Add an agent CLI fallback** (optional) in `mcp_client.py`:

```python
_AGENT_FALLBACK_CMDS = {
    "cursor":   ["cursor-agent", "mcp", "list-tools"],
    "windsurf": ["windsurf",     "mcp", "list-tools"],
}
```

No changes needed to `_readers.py` or `_parsers.py` if the client uses the standard `{"mcpServers": {...}}` JSON format.

---

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](https://github.com/RiaBanerjee24/Tooldex/blob/main/CONTRIBUTING.md) on GitHub for setup instructions, the development workflow, and pull request guidelines.
