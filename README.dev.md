# Tooldex — Developer Reference

Technical reference for contributors. Covers architecture, data flow, design decisions, and module responsibilities.

---

## Contents

- [Project structure](#project-structure)
- [Discovery pipeline](#discovery-pipeline)
- [Manifest singleton](#manifest-singleton)
- [Async architecture](#async-architecture)
- [Data models](#data-models)
- [API layer](#api-layer)
- [Security scanning](#security-scanning)
- [Version management](#version-management)
- [Adding a new MCP client](#adding-a-new-mcp-client)

---

## Project structure

```
tooldex/
├── __init__.py              # __version__ via importlib.metadata
├── cli.py                   # Typer CLI — `run` command definition only
├── _ports.py                 # find_free_port()
├── preferences.py            # load_prefs()/save_pref() — ~/.tooldex/preferences.json
├── _spinner.py                # Spinner — "tooldexing  3s" terminal spinner
├── _cli_output.py            # print_banner(), print_summary(), result_as_json()
├── settings.py               # debug flag (controls /api/docs exposure)
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
        ├── _paths.py            # Platform-aware path resolvers, walk_up_for()
        ├── _readers.py          # read_json(), read_claude_json(), read_codex_toml()
        ├── _parsers.py          # Dict → MCPServer, env var substitution
        ├── results.py           # DiscoverySource, ConfigDetectionResult, ToolDiscoveryResult
        ├── mcp_client.py        # Async prober: stdio / http / sse, agent CLI fallback
        ├── tool_discovery.py    # Sync wrappers, list_tools_for_all(), asyncio bridge
        ├── to_manifest.py       # Discovery output → TooldexManifest, merge_security_findings()
        ├── _docker_mcp.py       # Docker MCP profile reader (no live probe needed)
        ├── _status_claude.py    # Optional: enrich via `claude mcp list`
        ├── _status_codex.py     # Optional: enrich via `codex mcp list`
        └── _status_cursor.py    # Optional: enrich via `cursor-agent mcp list-tools`
```

---

## Discovery pipeline

Tooldex has a single data path: autodiscovery from MCP client config files.

```
MCP client config files (.json, .toml)
  → config_detector.py  (detect_all — reads all known config locations)
  → mcp_client.py       (live probe each server, async)
  → tool_discovery.py   (sync wrapper + asyncio bridge)
  → to_manifest.py      (build_manifest → TooldexManifest)
  → parser.py           (init_parser_from_manifest — installs singleton)
  → API routers         (get_parser().manifest)
```

### 1. Config detection (`config_detector.py`, `_paths.py`, `_readers.py`, `_parsers.py`)

`detect_all()` is the entry point. It reads config files in priority order:

1. Custom paths (`--config` flag)
2. Claude Code global (`~/.claude.json`) — special two-level format
3. Codex project (`.codex/config.toml`, walk up from cwd)
4. Codex global (`~/.codex/config.toml`)
5. Claude Code project, Cursor project/global, VSCode workspace/user (`.vscode/mcp.json`, `.vscode/.mcp.json`, `~/.config/Code/User/mcp.json` — all three nest servers under `"servers"` instead of `"mcpServers"`, see `CLIENT_SERVERS_KEY`), Copilot CLI global (`~/.copilot/mcp-config.json` — standard `"mcpServers"` key, unlike VSCode), MCP JSON project/global (`.mcp.json` and bare `mcp.json`), Agents (`.agents/mcp.json` and `.agents/.mcp.json`, project and global), Gemini Antigravity (`~/.gemini/antigravity/mcp_config.json`) — all via `build_plan()`
6. Docker MCP Toolkit profiles (via `docker mcp profile ls`)

**Qualified IDs** prevent cross-client collisions. Every server gets a key in the form `{client}:{server_id}`, e.g. `claude_code_user:browserbase` and `cursor_user:browserbase` are distinct entries and both survive. Project-scoped Claude Code servers use a three-part key: `claude_code_project:{md5_slug}:{server_id}`.

**First-sighting wins** within the same client — in-file duplicates are detected via `object_pairs_hook` in `json5.loads()` and recorded in `DiscoverySource.in_file_duplicates`.

**JSON5 / JSONC support** — `_readers.py` uses `json5.loads()` instead of `json.loads()`, so config files containing `//` line comments, `/* block */` comments, and trailing commas are parsed without error. This covers common formats emitted by VSCode-family editors and tools like Godot MCP.

**`serverUrl` alias** — `_spec_to_server()` in `_parsers.py` treats `serverUrl` as a fallback for `url` to support the Gemini Antigravity IDE remote server format.

**`~/.claude.json`** has a two-level structure: user-level servers at the top, plus a `projects` dict keyed by project root path. `parse_claude_json()` separates these and marks project entries with `project_path` for qualified ID generation.

**Codex uses TOML**, not JSON. `read_codex_toml()` delegates to `parse_mcp_servers()` with `key="mcp_servers"`.

**Docker MCP Toolkit** is read via `docker mcp profile ls --format json` — no live probing needed. Each profile becomes a `DiscoverySource`.

**Live status enrichment**: if the user grants permission, tooldex shells out to `claude mcp list` / `codex mcp list` / `cursor-agent mcp list-tools` and attaches connection status strings to the relevant servers. Skipped in `--json` / `--no-serve` mode.

**Env var substitution** in `_parsers.py`: `${VAR}` and `$VAR` references inside `env` and `args` fields are expanded against the process environment. Unresolved references pass through unchanged.

### 2. Live probing (`mcp_client.py`, `tool_discovery.py`)

`mcp_client.py` is fully async. `probe_server()` routes by transport:

- **stdio**: spawns a subprocess via `mcp.client.stdio.stdio_client`, merges server env with `os.environ`, runs MCP initialize + `tools/list`.
- **http**: connects via `mcp.client.streamable_http.streamable_http_client`.
- **sse**: connects via `mcp.client.sse.sse_client`.

For Cursor-sourced HTTP/SSE servers that reject the native probe, there is an automatic **agent CLI fallback**: `cursor-agent mcp list-tools <server_name>`. The fallback is extensible via `_AGENT_FALLBACK_CMDS`.

A `FileNotFoundError` on the server command returns a `connection_failed` result with a human-readable install hint (e.g. `'uvx' is not installed — install uv: https://astral.sh/uv`).

`probe_all()` runs probes concurrently under a `Semaphore` (default 8, configurable via `--concurrency`).

`tool_discovery.py` is the sync surface. `list_tools_for_all()` runs `probe_all()` on a fresh event loop. It short-circuits Docker MCP servers (pre-populated from profile snapshots) and emits synthetic `FOUND` results so downstream code stays uniform.

### 3. Manifest assembly (`to_manifest.py`)

`build_manifest()` attaches each `ToolDiscoveryResult` to its `MCPServer` as `discovered_tools`, `probe_status`, and `probe_error`. `probe_status` is the canonical failure signal used by the UI — it takes precedence over `connection_status`, which is a secondary signal from optional agent CLI enrichment.

---

## Manifest singleton

`parser.py` is now a thin module holding four module-level values and the functions to access them:

| Name | Type | Purpose |
|---|---|---|
| `_parser` | `TooldexParser` | Wraps the active `TooldexManifest` |
| `_last_scanned` | `str` (ISO-8601 UTC) | Timestamp of the last manifest install; returned in `GET /api/servers/` |
| `_startup_time` | `float` (`time.monotonic()`) | Set once at first install; drives `uptime_seconds` in `GET /api/health/` |
| `_discovery_sources` | `list[DiscoverySource]` | From the last `detect_all()`; served by `GET /api/files/` |

`init_parser_from_manifest(manifest)` installs the manifest and updates `_last_scanned` and `_startup_time` (first install only). It is called at CLI startup and after every `POST /api/rescan/`.

`get_parser().manifest` is the read path used by all API routers.

---

## Async architecture

The codebase is **sync at the surface, async only where it matters**.

The CLI and API request handlers are sync. The only async code is in `mcp_client.py` (I/O-bound: subprocess spawning, network connections).

```
sync caller (cli.py)
  → list_tools_for_all()        (tool_discovery.py, sync)
    → asyncio.run(probe_all())  (enters event loop)
      → asyncio.gather(...)     (concurrent probing)
        → probe_server()        (mcp_client.py, async)
```

FastAPI's uvicorn event loop is completely separate. API-triggered rescans use `asyncio.to_thread()` to run the blocking discovery pipeline without stalling the event loop:

- `POST /api/servers/{id}/rescan/` — `asyncio.to_thread(list_tools_for, server)`
- `POST /api/rescan/` — `asyncio.to_thread(_silenced, detect_all)` then `asyncio.to_thread(_silenced, list_tools_for_all, ...)`, guarded by `asyncio.Lock`

---

## Data models

All models are Pydantic v2 `BaseModel` subclasses.

### `TooldexManifest` (`manifest.py`)

| Field | Type | Description |
|---|---|---|
| `metadata` | `TooldexMetadata` | Name and optional description |
| `servers` | `dict[str, MCPServer]` | Keyed by qualified ID (`{client}:{server_id}`) |
| `all_tools` | `list[str]` | Sorted unique tool names across all servers |
| `server_agents_index` | `dict[str, list[dict]]` | Reserved for future agent discovery |

### `MCPServer` (`server.py`)

Holds transport config (`command`/`args`/`env` for stdio, `url` for http/sse) plus runtime fields:

| Field | Description |
|---|---|
| `discovered_tools` | `list[DiscoveredToolLite]` — populated by live probing |
| `client` | Which config source (`claude_code_user`, `cursor_project`, etc.) |
| `source_path` | Absolute path of the config file this server was read from |
| `probe_status` | `"found"` / `"connection_failed"` / `"timeout"` / etc. — canonical UI signal |
| `probe_error` | Human-readable error from the last failed probe |
| `connection_status` | Secondary signal from optional agent CLI enrichment |
| `security_findings` | `list[dict]` — findings from the last scan (`tool_name`, `severity`, `analyzer`, `threat_category`, `summary`) |
| `security_risk` | Worst severity across all findings, or `None` |
| `security_llm_scanned_at`, `security_llm_new_findings`, `security_llm_cache_hits`, `security_llm_last_scan_total` | LLM-judge-specific state — see [Security scanning](#security-scanning) |

### `DiscoveredToolLite` (`server.py`)

Lightweight tool record from live probing: `name`, `description`, `input_schema`. No agent-specific metadata.

---

## API layer

### `app.py`

`create_app()` is a factory (not a module-level singleton) so each call returns a fresh `FastAPI` instance. The React SPA is served via `StaticFiles` from `ui/dist/`. OpenAPI docs are only exposed when `settings.debug = True`.

### Routers

**`servers.py`**: `list_servers` returns all MCP servers with `tool_count`, `source_file`, `has_llm_cache`, `total_servers`, `total_tools`. `get_server` looks up a single server by qualified ID. `rescan_server` re-probes a single server via `asyncio.to_thread()` and updates the in-memory manifest entry (blocked with `409` while an LLM-judge job is running on that server, unless `force=true`). If the probe succeeds and `security_scan_enabled()` is true, it also re-runs a YARA scan scoped to just that server (`scan_servers({server_id: server})`) and merges the fresh findings in via `to_manifest.merge_security_findings(..., analyzer="YARA")` — this replaces only the YARA-sourced findings, leaving any cached LLM-judge findings on that server untouched. If the probe fails, or security scanning is disabled, `security_scanned`/`security_risk`/`security_findings` are left exactly as they were (not reset). The `llm-scan`/`llm-scan/status`/`llm-scan/stop`/`llm-scan/invalidate-cache` endpoints wrap `api/llm_jobs.py` — see [Security scanning](#security-scanning). Both `servers.py` and `api/llm_jobs.py` import `redact.py`'s `redact_server()`/`friendly_path()` to strip secrets before a payload leaves the process.

**`files.py`**: Returns `_discovery_sources` — the list of every config file checked, with path, client, status, server IDs found, and any parse error.

**`health.py`**: `GET /api/health/` returns `status`, `timestamp`, `uptime_seconds`. Nothing else — the rescan endpoints live in their own router.

**`rescan.py`**: Hosts `POST /api/rescan/` and `GET /api/rescan/stream/` (the SSE endpoint the "Rescan All" UI button actually uses) with two safety mechanisms:

- **`_rescan_lock` (`asyncio.Lock`)** — `POST /api/rescan/` returns `{"status": "already_scanning"}` immediately if a rescan is in progress; no caller waits.
- **`_silenced(fn)`** — redirects fd 1+2 to `/dev/null` during `detect_all()` and `list_tools_for_all()` to suppress subprocess noise. Safe because only one rescan runs at a time under the lock.

`rescan_stream` additionally checks `api/llm_jobs.py`'s `running_llm_job_ids()` and yields a `{"type": "blocked", ...}` event instead of scanning if any server has an LLM-judge job in flight, unless `force=true` (which aborts them first via `abort_all_llm_jobs()`).

All `_status_*.py` subprocess calls pass `stdin=subprocess.DEVNULL` to prevent Claude Code's auth prompts from inheriting the terminal stdin and blocking for up to 15 seconds.

---

## Security scanning

Powered by [Cisco's MCP Scanner](https://github.com/cisco-ai-defense/mcp-scanner) (`mcpscanner` on PyPI) via `tooldex/scanner/`.

**YARA** (`yara_scan.py`) is the only entry in `active_analyzers()` — it runs automatically as part of every discovery and rescan, for every server. `scan_servers()` builds one `mcpscanner.Scanner` per call (via `config.build_config()`) and fans out across servers under an `asyncio.Semaphore` (`MCP_SCANNER_CONCURRENCY`, default 8). Note this means every server gets connected to twice per discovery/rescan — once by `tool_discovery.py`'s own probe, once independently by mcpscanner's `Scanner` — since mcpscanner's public API (`scan_stdio_server_tools`/`scan_remote_server_tools`) always connects and lists tools itself; there's no supported way to hand it tools Tooldex already fetched (its `_analyze_tool()` internal *would* accept pre-fetched `mcp.types.Tool` objects, but it's a private, undocumented method not safe to depend on across mcpscanner versions).

`security_scan_enabled()` (`TOOLDEX_SECURITY_SCAN`, default `true`) is the single source of truth for whether the YARA pass runs at all — checked in `cli.py`'s `run()`, `rescan.py`'s `POST /api/rescan/`, and `servers.py`'s per-server `POST /api/servers/{id}/rescan/`. `run`'s `--no-security-scan` flag works by setting that env var on the process at startup rather than threading a separate flag through every call site. It's implemented in `tooldex/_env_bool.py` (a dependency-free module, deliberately outside `tooldex/scanner/`, so `cli.py` can check it before the `--json` fast path without importing the heavier `mcpscanner`-backed scanner package).

**AI security scan** (`llm_judge.py`) is opt-in and per-server only — `run_llm_judge_scan()` is never called from `scan_servers()`, only from the `/api/servers/{id}/llm-scan/*` routes via `api/llm_jobs.py`'s `LlmJudgeJob`/`run_llm_judge_job()`. Tooldex's AI security scan is powered by Cisco AI Defense's open-source mcpscanner SDK, running entirely locally — the only network call it makes is to whichever LLM provider you configure. Key behaviors:

- **Caching** (`llm_cache.py`): a flat JSON file at `~/.tooldex/llm_scan_cache.json`, keyed by `f"{server_id}::{tool_name}"`, each entry pinned to a hash of that tool's name/description/input_schema. `force=True` (the default for every UI-triggered scan) skips the cache read but still writes the result, so a forced scan stays fresh while still priming the cache for the next passive hydration.
- **Hydration**: `hydrate_llm_cache(manifest)` reconstructs `security_llm_*` fields straight from the cache at manifest-build time — called from both `cli.py`'s `run()` and `rescan.py`'s `POST /api/rescan/` — so a server judged in a previous session shows its last verdict with zero LLM calls on startup.
- **Cancellation**: `_race_cancel()` races the in-flight LLM call (or the inter-call rate-limit delay) against a caller-supplied `asyncio.Event`, so `POST /api/servers/{id}/llm-scan/stop/` lands almost immediately instead of waiting out a slow request.
- **False-clean guard**: mcpscanner's own `Scanner` swallows LLM call failures internally (logs an error, reports the tool as having no findings) — a bad or expired key would otherwise look identical to "no vulnerabilities found." `_check_llm_auth()` (a one-token ping before the tool loop) and `_CaptureLlmErrors` (a log-capture handler during each real call) both map known HTTP status codes to a `ValueError` instead of a false-clean result.
- **Merging**: both `hydrate_llm_cache()` and the `llm-scan`/`invalidate-cache` route handlers share `to_manifest.merge_security_findings()` to replace a server's LLM-analyzer findings and recompute `security_risk` — avoids three copies of the same merge/rank logic.

**Env vars**: `TOOLDEX_LLM_API_KEY` / `_MODEL` / `_RATE_LIMIT_DELAY` / `_TEMPERATURE` / `_MAX_RETRIES` / `_BASE_URL` / `_API_VERSION` / `_TIMEOUT`, each falling back to its original `MCP_SCANNER_LLM_*` name via `config._env_with_legacy_fallback()` (prints a one-time CLI notice on first fallback use). See the [README's env var table](../README.md#security-scanning) for defaults.

---

## Version management

Single source of truth: `pyproject.toml`.

```
pyproject.toml          version = "0.1.1"
    ↓ (hatchling reads at build time)
installed package metadata
    ↓ (importlib.metadata.version("tooldex") at runtime)
tooldex.__version__    "0.1.1"
    ↓
cli.py                  --version flag, startup banner
api/app.py              FastAPI app version field
```

To bump: change `version =` in `pyproject.toml` and reinstall (`pip install -e .`). Nothing else needs updating.

---

## Adding a new MCP client

**1. Add path resolvers** in `_paths.py`:

```python
def windsurf_user_path() -> Path:
    return Path.home() / ".windsurf" / "mcp.json"

def windsurf_project_path(cwd: Path) -> Optional[Path]:
    return walk_up_for(cwd, (".windsurf", "mcp.json"))
```

Add all new client IDs to `CLIENT_PRIORITY` in the desired deduplication order.

**2. Register in `build_plan()`**:

```python
("windsurf_project", lambda: windsurf_project_path(cwd)),
("windsurf_user",    windsurf_user_path),
```

**3. Wire up the UI** in `ui/src/components/servers/serverHelpers.jsx` — add entries to `CLIENT_META` and `GROUP_ORDER`:

```js
windsurf_user:    { group: "Windsurf", label: "Windsurf", scope: "global" },
windsurf_project: { group: "Windsurf", label: "Windsurf", scope: "project" },
```

**4. Add CLI display names** in `_cli_output.py` if the raw client ID is not user-friendly:

```python
_CLIENT_DISPLAY = {
    ...
    "windsurf_user":    "windsurf",
    "windsurf_project": "windsurf",
}
```

**5. Rebuild the UI** after any JSX changes:

```bash
cd tooldex/ui && npm run build
```

**6. Add a status enrichment module** (optional) — follow the pattern of `_status_cursor.py` and add a call site in `detect_all()`.

**7. Add an agent CLI fallback** (optional) in `mcp_client.py`:

```python
_AGENT_FALLBACK_CMDS = {
    "cursor":   ["cursor-agent", "mcp", "list-tools"],
    "windsurf": ["windsurf",     "mcp", "list-tools"],
}
```

No changes needed to `_readers.py` or `_parsers.py` if the client uses the standard `{"mcpServers": {...}}` JSON format. If the client uses a non-standard field name (e.g. `serverUrl` instead of `url`), add a fallback in `_spec_to_server()` in `_parsers.py`.
