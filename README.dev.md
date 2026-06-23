# Toolpool — Developer Reference

Technical reference for contributors. Covers architecture, data flow, design decisions, and module responsibilities.

---

## Contents

- [Project structure](#project-structure)
- [Discovery pipeline](#discovery-pipeline)
- [Manifest singleton](#manifest-singleton)
- [Async architecture](#async-architecture)
- [Data models](#data-models)
- [API layer](#api-layer)
- [Version management](#version-management)
- [Adding a new MCP client](#adding-a-new-mcp-client)

---

## Project structure

```
toolpool/
├── __init__.py              # __version__ via importlib.metadata
├── cli.py                   # Typer CLI — run command, flags, startup
├── _cli_output.py           # print_banner(), print_summary(), result_as_json()
├── settings.py              # debug flag (controls /api/docs exposure)
│
├── api/
│   ├── app.py               # FastAPI factory, CORS, SPA mount
│   └── routers/
│       ├── health.py        # GET /api/health/, POST /api/rescan/
│       ├── servers.py       # GET /api/servers/, /api/servers/{id}/, POST /api/servers/{id}/rescan/
│       └── files.py         # GET /api/files/
│
└── core/
    ├── models/
    │   ├── manifest.py      # ToolpoolManifest, ToolpoolMetadata
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
        ├── to_manifest.py       # Discovery output → ToolpoolManifest
        ├── _docker_mcp.py       # Docker MCP profile reader (no live probe needed)
        ├── _status_claude.py    # Optional: enrich via `claude mcp list`
        ├── _status_codex.py     # Optional: enrich via `codex mcp list`
        └── _status_cursor.py    # Optional: enrich via `cursor-agent mcp list-tools`
```

---

## Discovery pipeline

Toolpool has a single data path: autodiscovery from MCP client config files.

```
MCP client config files (.json, .toml)
  → config_detector.py  (detect_all — reads all known config locations)
  → mcp_client.py       (live probe each server, async)
  → tool_discovery.py   (sync wrapper + asyncio bridge)
  → to_manifest.py      (build_manifest → ToolpoolManifest)
  → parser.py           (init_parser_from_manifest — installs singleton)
  → API routers         (get_parser().manifest)
```

### 1. Config detection (`config_detector.py`, `_paths.py`, `_readers.py`, `_parsers.py`)

`detect_all()` is the entry point. It reads config files in priority order:

1. Custom paths (`--config` flag)
2. Claude Code global (`~/.claude.json`) — special two-level format
3. Codex project (`.codex/config.toml`, walk up from cwd)
4. Codex global (`~/.codex/config.toml`)
5. Claude Code project, Cursor project/global, MCP JSON project/global (via `build_plan()`)
6. Docker MCP Toolkit profiles (via `docker mcp profile ls`)

**Qualified IDs** prevent cross-client collisions. Every server gets a key in the form `{client}:{server_id}`, e.g. `claude_code_user:browserbase` and `cursor_user:browserbase` are distinct entries and both survive. Project-scoped Claude Code servers use a three-part key: `claude_code_project:{md5_slug}:{server_id}`.

**First-sighting wins** within the same client — in-file duplicates are detected via `object_pairs_hook` in `json.loads()` and recorded in `DiscoverySource.in_file_duplicates`.

**`~/.claude.json`** has a two-level structure: user-level servers at the top, plus a `projects` dict keyed by project root path. `parse_claude_json()` separates these and marks project entries with `project_path` for qualified ID generation.

**Codex uses TOML**, not JSON. `read_codex_toml()` delegates to `parse_mcp_servers()` with `key="mcp_servers"`.

**Docker MCP Toolkit** is read via `docker mcp profile ls --format json` — no live probing needed. Each profile becomes a `DiscoverySource`.

**Live status enrichment**: if the user grants permission, toolpool shells out to `claude mcp list` / `codex mcp list` / `cursor-agent mcp list-tools` and attaches connection status strings to the relevant servers. Skipped in `--json` / `--no-serve` mode.

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
| `_parser` | `ToolpoolParser` | Wraps the active `ToolpoolManifest` |
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

### `ToolpoolManifest` (`manifest.py`)

| Field | Type | Description |
|---|---|---|
| `metadata` | `ToolpoolMetadata` | Name and optional description |
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

### `DiscoveredToolLite` (`server.py`)

Lightweight tool record from live probing: `name`, `description`, `input_schema`. No agent-specific metadata.

---

## API layer

### `app.py`

`create_app()` is a factory (not a module-level singleton) so each call returns a fresh `FastAPI` instance. The React SPA is served via `StaticFiles` from `ui/dist/`. OpenAPI docs are only exposed when `settings.debug = True`.

### Routers

**`servers.py`**: `list_servers` returns all MCP servers with `tool_count`, `source_file`, `total_servers`, `total_tools`. `get_server` looks up a single server by qualified ID. `rescan_server` re-probes a single server via `asyncio.to_thread()` and updates the in-memory manifest entry.

**`files.py`**: Returns `_discovery_sources` — the list of every config file checked, with path, client, status, server IDs found, and any parse error.

**`health.py`**: `GET /api/health/` returns `status`, `timestamp`, `uptime_seconds`. Hosts `POST /api/rescan/` with two safety mechanisms:

- **`_rescan_lock` (`asyncio.Lock`)** — returns `{"status": "already_scanning"}` immediately if a rescan is in progress; no caller waits.
- **`_silenced(fn)`** — redirects fd 1+2 to `/dev/null` during `detect_all()` and `list_tools_for_all()` to suppress subprocess noise. Safe because only one rescan runs at a time under the lock.

All `_status_*.py` subprocess calls pass `stdin=subprocess.DEVNULL` to prevent Claude Code's auth prompts from inheriting the terminal stdin and blocking for up to 15 seconds.

---

## Version management

Single source of truth: `pyproject.toml`.

```
pyproject.toml          version = "0.1.0"
    ↓ (hatchling reads at build time)
installed package metadata
    ↓ (importlib.metadata.version("toolpool") at runtime)
toolpool.__version__    "0.1.0"
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
```

Add the new client ID to `CLIENT_PRIORITY` in the desired deduplication order.

**2. Register in `build_plan()`**:

```python
("windsurf_user", windsurf_user_path),
```

**3. Add a status enrichment module** (optional) — follow the pattern of `_status_cursor.py` and add a call site in `detect_all()`.

**4. Add an agent CLI fallback** (optional) in `mcp_client.py`:

```python
_AGENT_FALLBACK_CMDS = {
    "cursor":   ["cursor-agent", "mcp", "list-tools"],
    "windsurf": ["windsurf",     "mcp", "list-tools"],
}
```

No changes needed to `_readers.py` or `_parsers.py` if the client uses the standard `{"mcpServers": {...}}` JSON format.
