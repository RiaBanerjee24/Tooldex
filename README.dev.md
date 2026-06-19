# Toolpool — Developer Reference

Technical reference for contributors. Covers architecture, data flow, design decisions, and module responsibilities.

---

## Contents

- [Project structure](#project-structure)
- [Two data paths, one manifest](#two-data-paths-one-manifest)
- [Discovery pipeline](#discovery-pipeline)
- [Parser pipeline (YAML)](#parser-pipeline-yaml)
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
├── _cli_output.py           # print_summary(), result_as_json()
├── settings.py              # debug flag (controls /api/docs exposure)
│
├── api/
│   ├── app.py               # FastAPI factory, CORS, SPA mount
│   ├── deps.py              # FastAPI dependency: get_manifest()
│   └── routers/
│       ├── health.py        # GET /api/health
│       ├── agents.py        # GET /api/agents, /api/agents/{id}
│       ├── servers.py       # GET /api/servers, /api/servers/{id}
│       ├── policy.py        # GET /api/policy/matrix, /engines, /engines/{id}/raw
│       └── analysis.py      # GET /api/conflicts, /api/orchestration
│
└── core/
    ├── models/
    │   ├── manifest.py      # ToolpoolManifest — central aggregate
    │   ├── server.py        # MCPServer, DiscoveredToolLite
    │   ├── agent.py         # Agent, AgentServerRef, AgentOrchestration
    │   ├── tool.py          # Tool, Permission, effective_access()
    │   ├── policy.py        # PolicyEngine, AgentPolicy, InlinePolicyRule
    │   └── conflict.py      # ConflictError, ConflictWarning, OrchestrationIssue
    │
    ├── parsers/             # YAML manifest pipeline
    │   ├── parser.py        # ToolpoolParser orchestrator + module singleton
    │   ├── loader.py        # File I/O, glob resolution, FileContents
    │   ├── transformers.py  # raw dict → Pydantic model (pure functions)
    │   ├── merger.py        # Conflict detection + entity merging
    │   └── orchestration.py # Delegation graph DFS + cycle classification
    │
    └── discovery/           # Autodiscovery pipeline
        ├── config_detector.py   # detect_all(), _merge(), qualified IDs
        ├── _paths.py            # Platform-aware path resolvers, walk_up_for()
        ├── _readers.py          # read_json(), read_claude_json(), read_codex_toml()
        ├── _parsers.py          # Dict → MCPServer, env var substitution
        ├── results.py           # DiscoverySource, ConfigDetectionResult, ToolDiscoveryResult
        ├── mcp_client.py        # Async prober: stdio / http / sse, fallback to agent CLI
        ├── tool_discovery.py    # Sync wrappers, list_tools_for_all(), asyncio bridge
        ├── to_manifest.py       # Discovery output → ToolpoolManifest
        ├── _docker_mcp.py       # Docker MCP profile reader (no live probe needed)
        ├── _status_claude.py    # Optional: enrich via `claude mcp list`
        ├── _status_codex.py     # Optional: enrich via `codex mcp list`
        └── _status_cursor.py    # Optional: enrich via `cursor-agent mcp list-tools`
```

---

## Two data paths, one manifest

The central design principle: **two independent pipelines produce the same `ToolpoolManifest`**, so the API layer and UI are unaware of how the data arrived.

```
YAML path:
  toolpool.yml + includes
    → loader.py (file I/O)
    → transformers.py (dict → models)
    → merger.py (conflict detection)
    → orchestration.py (graph analysis)
    → ToolpoolManifest

Discovery path:
  MCP client config files
    → config_detector.py (detect_all)
    → mcp_client.py (live probe, async)
    → tool_discovery.py (sync wrapper)
    → to_manifest.py (build_manifest)
    → ToolpoolManifest
```

Both paths terminate at `init_parser_from_manifest()` in `parser.py`, which installs the manifest into the module-level singleton. API routers call `get_parser().manifest` and receive the same object regardless of origin.

The YAML path is richer (agents, policy engines, orchestration graph, conflict detection). The discovery path currently produces servers and tools only — agents are a planned Phase 2 addition (AST scanner).

---

## Discovery pipeline

### 1. Config detection (`config_detector.py`, `_paths.py`, `_readers.py`, `_parsers.py`)

`detect_all()` is the entry point. It reads config files from known locations in priority order:

1. Custom paths (`--config` flag)
2. Claude Code global (`~/.claude.json`) — special two-level format
3. Codex project (`.codex/config.toml`, walk up from cwd)
4. Codex global (`~/.codex/config.toml`)
5. Claude Code project, Cursor project/global, MCP JSON project/global (all via `build_plan()`)
6. Docker MCP Toolkit profiles (via `docker mcp profile ls`)

**Qualified IDs** prevent cross-client collisions. Every server gets a key in the form `{client}:{server_id}`, e.g. `claude_code_user:browserbase` and `cursor_user:browserbase` are distinct entries and both survive. Project-scoped Claude Code servers use a three-part key: `claude_code_project:{md5_slug}:{server_id}`, where the slug is an MD5 hash of the project root path (avoids slashes in dict keys).

**First-sighting wins** within the same client — if the same qualified ID appears twice (e.g. duplicate JSON keys in one file), the second is silently dropped. In-file duplicates are detected by passing `object_pairs_hook` to `json.loads()` and recorded in `DiscoverySource.in_file_duplicates`.

**Cross-client name collisions** are tracked in `ConfigDetectionResult._name_to_qid` (a private `{name → qualified_id}` dict). When the same server name is first seen in one client, its qualified ID is registered. Any later client contributing the same name appends to `ConfigDetectionResult.duplicates`.

**`~/.claude.json` has a two-level structure**: user-level servers at the top, plus a `projects` dict keyed by project root path — each project entry holds its own `mcpServers` block. `parse_claude_json()` separates these, applies the cwd walk-up to include only relevant project entries, and marks them with `project_path` for later use in qualified ID generation.

**Codex uses TOML**, not JSON. `read_codex_toml()` delegates to `parse_mcp_servers()` with `key="mcp_servers"` (underscore, not camelCase).

**Docker MCP Toolkit** is read via `docker mcp profile ls --format json` which returns tool snapshots in one call — no live probing needed. Each profile becomes a `DiscoverySource` with `client="docker_mcp:{profile_name}"`.

**Live status enrichment** (steps 7–9 in `detect_all`): if the user grants permission, toolpool shells out to `claude mcp list` / `codex mcp list` / `cursor-agent mcp list-tools` and attaches the connection status strings to the relevant servers. This is optional and skipped entirely in `--json` / `--no-serve` mode.

**`_status_*.py` modules** each run a subprocess, parse the CLI output, and return a `{server_name → status_string}` dict. The detector merges those back into `result.servers` via `model_copy(update=...)`.

**Env var substitution** in `_parsers.py`: `${VAR}` and `$VAR` references inside `env` and `args` fields are expanded against the process environment using a single compiled regex. Unresolved references pass through unchanged.

### 2. Live probing (`mcp_client.py`, `tool_discovery.py`)

**`mcp_client.py`** is fully async. `probe_server()` routes by transport:

- **stdio**: spawns a subprocess via `mcp.client.stdio.stdio_client`, merges server env with `os.environ` so `PATH`/`HOME` survive, then runs the MCP initialize handshake and `tools/list`.
- **http**: connects via `mcp.client.streamable_http.streamable_http_client`.
- **sse**: connects via `mcp.client.sse.sse_client`.

For Cursor-sourced HTTP/SSE servers that reject the native probe (e.g. missing auth), there is an automatic **agent CLI fallback**: `cursor-agent mcp list-tools <server_name>`. The fallback mechanism is extensible — `_AGENT_FALLBACK_CMDS` maps client name prefixes to their CLI commands, so adding a new client fallback is one dict entry. Claude Code and Codex are pre-stubbed but commented pending CLI confirmation.

Every failure mode (timeout, missing command, protocol error, missing SDK) is caught and returned as a `ToolDiscoveryResult` with the appropriate `ToolDiscoveryStatus` enum value. `probe_server()` never raises to the caller.

`probe_all()` uses `asyncio.gather()` with a `Semaphore` to bound concurrency (default 8, configurable via `--concurrency`). Results are returned in the same order as the input server list.

**`tool_discovery.py`** is the sync surface. `list_tools_for_all()` runs the async `probe_all()` on a fresh event loop using a custom `_run()` helper that detects an already-running loop and raises a clear error rather than hanging or crashing silently. It also short-circuits Docker MCP servers (which have `discovered_tools` pre-populated from profile snapshots) and emits synthetic `FOUND` results for them so downstream code stays uniform.

### 3. Manifest assembly (`to_manifest.py`)

`build_manifest()` attaches `ToolDiscoveryResult` data to each `MCPServer` as a list of `DiscoveredToolLite`, then constructs a `ToolpoolManifest`. The `agents` dict is empty in Phase 1. The result has the same shape as a YAML-parsed manifest, so `init_parser_from_manifest()` and the API routers require no changes.

---

## Parser pipeline (YAML)

The YAML pipeline is split into strict single-responsibility modules with no cross-dependencies between them.

### `loader.py`

Pure file I/O. `read_yaml()` reads one file. `load_all_included_files()` expands glob patterns relative to the root manifest directory, loads each matched file, and enforces hard schema rules on included files: no nested `include:` keys, no `policy_engines:` or `metadata:` blocks, agents/servers must use dict format (not list). Returns a `list[FileContents]`.

### `transformers.py`

Pure conversion functions. One function per model: `parse_agent()`, `parse_server()`, `parse_tool()`, `parse_policy_engine()`, etc. Input is a raw `dict`; output is a Pydantic model. No I/O, no merge logic, no side effects.

### `merger.py`

Two-pass conflict detection and merging:

1. **Included-vs-included scan**: find IDs claimed by more than one included file → `ConflictError`. Neither entity is rendered.
2. **Root-vs-included merge**: for each remaining entity, root definition wins over included-file definition → `ConflictWarning` on collision. Entities with no conflict are merged cleanly.

The conflict classification maps directly to distinct UI indicators (❌ vs ⚠).

### `orchestration.py`

DFS over the agent delegation graph (`can_delegate_to` edges). Cycle detection uses a standard `visited`/`path` stack. Each detected cycle is classified:

- **`circular`**: two-hop loop (`A → B → A`) where the back-edge is not declared in `receives_from`.
- **`bidirectional`**: two-hop loop where `receives_from` covers every back-edge — intentional, but still flagged.
- **`cycle`**: multi-hop loop (`A → B → C → A`).

`frozenset` deduplication prevents the same cycle from being reported multiple times (once per starting node). Conflicted agents are excluded from analysis.

### `parser.py`

Orchestrates all four modules and manages the **module-level singleton**. The singleton pattern (`get_parser()` / `init_parser()`) avoids threading overhead — all API request handlers share one manifest object rather than reloading YAML per request.

`_build()` assembles the final `ToolpoolManifest` in a **single pass** over all agents after merging: it simultaneously computes `all_tools`, `agent_tool_index` (`agent_id → {tool_name → Tool}`), and `server_agents_index` (`server_id → [{id, name}]`). These precomputed indexes make the API router's O(1) lookups possible at request time.

`init_parser_from_manifest()` bypasses YAML loading entirely and installs a pre-built manifest (from the discovery path) into the singleton. The installed parser has no `config_path` — `reload()` would fail, which is intentional since discovery manifests are refreshed by re-running the command, not by file watching.

---

## Async architecture

The codebase is **sync at the surface, async only where it matters**.

The CLI, parsers, and API request handlers are all sync. The only async code is in `mcp_client.py`, which performs I/O-bound operations (subprocess spawning, network connections). This keeps the codebase simple — no `async def` leakage into unrelated layers.

The sync↔async boundary is managed by `tool_discovery._run()`:

```
sync caller (cli.py)
  → list_tools_for_all()        (tool_discovery.py, sync)
    → asyncio.run(probe_all())  (enters event loop)
      → asyncio.gather(...)     (concurrent probing)
        → probe_server()        (mcp_client.py, async)
```

`asyncio.run()` is preferred over manually creating and closing an event loop because it handles cleanup (cancelling pending tasks) correctly. The running-loop check in `_run()` handles embedded contexts (pytest-anyio, Jupyter) where `asyncio.run()` would raise.

FastAPI's own event loop (used by uvicorn) is completely separate. The sync API handlers never enter the MCP probing loop — probing happens once at startup before uvicorn is launched.

---

## Data models

All models are Pydantic v2 `BaseModel` subclasses. No SQLAlchemy, no ORM — the manifest is an in-memory object graph rebuilt on each load.

### `ToolpoolManifest` (`manifest.py`)

The central aggregate. Contains:

- `servers`, `agents`, `policy_engines` — dicts keyed by ID
- `conflict_errors`, `conflict_warnings`, `orchestration_issues` — populated by the YAML pipeline; empty for discovery-built manifests
- `agent_tool_index` — `dict[agent_id, dict[tool_name, Tool]]` for O(1) per-tool access lookup (used by the policy matrix router)
- `server_agents_index` — `dict[server_id, list[{id, name}]]` for O(1) agent-by-server lookup
- `_conflicted_*` / `_warned_*` — private `set[str]` caches for O(1) conflict-status checks

Private fields on a Pydantic model use underscore prefix and are set directly after construction (not via `__init__`) since they're not part of the schema.

### `MCPServer` (`server.py`)

Holds transport config (`command`/`args`/`env` for stdio, `url` for http/sse) plus runtime-populated fields: `discovered_tools` (from probing), `client` (which config source it came from), `source_path`, `connection_status`. The split between declaration fields and runtime fields is intentional — YAML-only manifests have empty `discovered_tools`; discovery-only manifests have empty `agent`-related fields.

### `Tool` (`tool.py`)

Agent-specific view of a tool. `effective_access()` computes a four-state summary (`allowed` / `denied` / `partial` / `unknown`) from the `permissions` list. `partial` means some operations are allowed and some denied — surfaced as a distinct colour in the permission matrix.

### `DiscoveredToolLite` (`server.py`)

Lightweight tool record produced by live probing. Distinct from `Tool` — it carries no agent-specific access metadata, just name, description, and input schema. The distinction keeps probed data neutral until it's joined to an agent context.

---

## API layer

### `app.py`

`create_app()` is a factory, not a module-level singleton, which makes it testable (each call returns a fresh `FastAPI` instance). In production, the React SPA is served by FastAPI's `StaticFiles` mount directly from `ui/dist/`. In development, Vite runs separately and proxies `/api` to FastAPI.

OpenAPI docs (`/api/docs`, `/api/redoc`) are only exposed when `settings.debug = True`.

### `deps.py`

Provides the `get_manifest()` FastAPI dependency, which calls `get_parser().manifest`. All routers receive the manifest via dependency injection rather than importing the singleton directly — this makes the dependency swappable in tests.

### Routers

All routers are read-only. No endpoint mutates the manifest. Response shapes are built inline from the manifest — no separate serialisation layer.

**`agents.py`**: `list_agents` precomputes an `orch_index` (`agent_id → [issues]`) before iterating agents, avoiding O(agents × orchestration_issues) inner-loop scanning. `get_agent` resolves server references by name using `manifest.get_server()`.

**`policy.py`**: `policy_matrix` iterates `manifest.agents × manifest.all_tools` and uses `manifest.agent_tool_access(agent_id, tool_name)` (backed by `agent_tool_index`) for O(1) per-cell lookup. Without the index, a naive scan would be O(agents × servers × tools) per request.

**`analysis.py`**: `orchestration_overview` returns the full delegation edge list plus issues. Uses `itertools.groupby` on issues sorted by type to produce per-type counts.

---

## Version management

**Single source of truth: `pyproject.toml`.**

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

`toolpool/__init__.py` uses `importlib.metadata.version()` with a `PackageNotFoundError` fallback to `"unknown"` for uninstalled dev runs. To bump the version, change `version =` in `pyproject.toml` and reinstall (`pip install -e .`). Nothing else needs updating.

---

## Adding a new MCP client

To add support for a new client (e.g. Windsurf, Zed):

**1. Add path resolvers** in `_paths.py`:

```python
def windsurf_user_path() -> Path:
    return Path.home() / ".windsurf" / "mcp.json"

def windsurf_project_path(cwd: Path) -> Optional[Path]:
    return walk_up_for(cwd, (".windsurf", "mcp.json"))
```

Add the new client IDs to `CLIENT_PRIORITY` in the desired deduplication order.

**2. Register in `build_plan()`** in `_paths.py`:

```python
("windsurf_project", lambda: windsurf_project_path(cwd)),
("windsurf_user",    windsurf_user_path),
```

**3. Add a status enrichment module** (optional) if the client has a CLI tool:

Create `_status_windsurf.py` following the pattern of `_status_cursor.py`. Add a permission prompt and call site in `detect_all()` in `config_detector.py`.

**4. Add an agent CLI fallback** (optional) in `mcp_client.py` if the client can list tools on behalf of auth-protected servers:

```python
_AGENT_FALLBACK_CMDS: dict[str, list[str]] = {
    "cursor":    ["cursor-agent", "mcp", "list-tools"],
    "windsurf":  ["windsurf",     "mcp", "list-tools"],   # ← add here
}
```

The config parser (`_readers.py`, `_parsers.py`) requires no changes if the new client uses the standard `{"mcpServers": {...}}` JSON format. Only non-standard formats (like Codex's TOML or Claude Code's two-level `~/.claude.json`) need custom readers.
