# Pericat — Codebase Overview

Pericat is an **AI Agent Permission Observatory**: a tool for declaring, auditing, and visualising the MCP (Model Context Protocol) server permissions granted to AI agents. It has two operating modes that converge on the same FastAPI backend and React UI:

- **`pericat run`** — you write a `pericat.yml` that declares agents, MCP servers, and per-tool access rules. Pericat loads, validates, and serves that config.
- **`pericat discover`** — Pericat scans the known config files of MCP clients (Claude Desktop, Claude Code, Cursor, Windsurf, Codex CLI), probes each discovered server for its live tool list, and builds an equivalent manifest without any YAML on your part.

---

## Directory structure

```
pericat/
├── cli.py
├── _cli_output.py
├── settings.py
├── __init__.py
│
├── api/
│   ├── app.py
│   ├── deps.py
│   └── routers/
│       ├── health.py
│       ├── agents.py
│       ├── servers.py
│       ├── policy.py
│       └── analysis.py
│
├── core/
│   ├── models/
│   │   ├── manifest.py
│   │   ├── agent.py
│   │   ├── server.py
│   │   ├── tool.py
│   │   ├── policy.py
│   │   └── conflict.py
│   │
│   ├── parsers/
│   │   ├── parser.py
│   │   ├── loader.py
│   │   ├── transformers.py
│   │   ├── merger.py
│   │   └── orchestration.py
│   │
│   └── discovery/
│       ├── config_detector.py
│       ├── _paths.py
│       ├── _parsers.py
│       ├── mcp_client.py
│       ├── tool_discovery.py
│       ├── results.py
│       └── to_manifest.py
│
└── ui/
    └── src/
        ├── App.jsx
        ├── api.js
        ├── constants.js
        ├── views/
        │   ├── Dashboard.jsx
        │   ├── Agents.jsx
        │   ├── Servers.jsx
        │   └── Permissions.jsx
        ├── components/
        │   ├── Topbar.jsx
        │   └── ui.jsx
        └── hooks/
            └── useFetch.js
```

---

## Entry points

### `cli.py`
Typer application with two commands.

**`pericat run`** walks up from `cwd` to find a `pericat.yml` (or accepts `--config`), calls `init_parser()` to load and validate it, then starts the FastAPI server via uvicorn.

**`pericat discover`** runs in two phases: (1) `detect_all()` reads all known MCP-client config files; (2) `list_tools_for_all()` probes each discovered server for its tool list. Output can be a human-readable summary, raw JSON (`--json`), or the Observatory UI. When starting the server it calls `init_parser_from_manifest()` to install the discovery-built manifest into the singleton so the API routers don't need to know which mode produced the data.

### `_cli_output.py`
Display helpers for `pericat discover`. `print_summary()` renders a coloured table of config-file statuses and per-server tool lists. `result_as_json()` produces the machine-readable equivalent for CI use. Both functions are separated from `cli.py` so they can be tested independently.

### `settings.py`
Single flag: `debug = False`. Controls whether FastAPI exposes `/api/docs`, `/api/redoc`, and `/api/openapi.json`.

### `__init__.py`
Exports the `version` string (`"0.1.0"`).

---

## `api/`

### `api/app.py`
FastAPI application factory (`create_app()`). Registers all five routers under `/api`, adds CORS middleware, and mounts the pre-built React SPA from `ui/dist/`. During startup it launches an async task that calls `parser.watch()` to hot-reload the manifest on file changes.

### `api/routers/health.py` — `GET /api/health`
Returns status (`"ok"` or `"degraded"`), the pericat version, manifest metadata counts, and any cross-reference warnings detected by `parser.validate_references()`.

### `api/routers/agents.py` — `GET /api/agents`, `GET /api/agents/{id}`
`list_agents` returns all agents with their connected servers, tool counts, orchestration edges, and conflict/warning flags. Precomputes an `orch_index` (agent → issues) to avoid O(agents × issues) scanning.

`get_agent` returns a full detail record for one agent: resolved server references with their per-tool access rules, identity/policy-engine detail, and enriched orchestration (target agents resolved by name, issues list).

### `api/routers/servers.py` — `GET /api/servers`, `GET /api/servers/{id}`
`list_servers` returns all servers using the precomputed `server_agents_index` for O(1) agent-count lookup.

`get_server` returns a full detail record: transport config, every connected agent with their tool-access rules for this server, and discovered tools from autodiscovery (if any).

### `api/routers/policy.py` — `GET /api/policy/matrix`, `/engines`, `/engines/{id}/raw`
`policy_matrix` builds the agents × tools permission grid. For each agent × tool pair it emits `effective_access` (the computed access state from `Tool.effective_access()`), raw access/risk fields, and any `denied_by` note.

`list_engines` returns all declared policy engines.

`get_raw_policy` reads and returns the raw content of a `type: file` policy engine (OPA, Cedar, etc.) from disk.

### `api/routers/analysis.py` — `GET /api/conflicts`, `GET /api/orchestration`
`list_conflicts` surfaces conflict errors (two included files define the same ID) and conflict warnings (root manifest beats an included file on the same ID).

`orchestration_overview` returns the full delegation graph as an edge list plus all detected issues (circular, bidirectional, multi-hop cycle), with per-issue counts.

---

## `core/models/`

Pure Pydantic models. No file I/O, no business logic beyond computed properties.

### `manifest.py`
`PericatManifest` is the central data structure everything else reads from. Holds dicts of `Agent`, `MCPServer`, and `PolicyEngine` keyed by ID, plus precomputed indexes built at parse time:
- `agent_tool_index`: `agent_id → {tool_name → Tool}` for O(1) per-tool access lookup in the policy matrix.
- `server_agents_index`: `server_id → [{id, name}]` for O(1) "which agents use this server" lookup.
- `_conflicted_*` / `_warned_*` id sets for O(1) conflict-status checks in the API routers.

Also holds `PericatMetadata` (name/owner/updated) and `Observatory` (log file paths).

### `agent.py`
`Agent` is the primary declared entity. Key fields: `servers` (list of `AgentServerRef` — each points to an MCP server and carries the tool-access rules for that pairing), `orchestration` (`AgentOrchestration` — `can_delegate_to` and `receives_from` lists used for graph analysis), `identity` (`AgentIdentity` — auth type, token lifetime, OAuth scopes), `file_access` (filesystem paths with read/write permissions), and `policies` (inline or referenced policy rules).

### `server.py`
`MCPServer` represents an MCP server — transport type (`stdio`/`sse`/`streamable-http`), spawn command/args/env for stdio, URL for remote. `discovered_tools` (list of `DiscoveredToolLite`) is populated by autodiscovery and is empty for YAML-only manifests.

### `tool.py`
`Tool` carries the agent-specific view of a tool: `risk` level, top-level `access` flag, fine-grained `permissions` (operations × resource × allow/deny), and `denied_by` (which policy denied it). `effective_access()` computes a single summary state (`allowed`/`denied`/`partial`/`unknown`) from the permissions list.

### `policy.py`
`PolicyEngine` declares an external policy evaluator (OPA, Cedar, Casbin, etc.) with its source location. `AgentPolicy` is an inline or ref-based policy attached to a specific agent; `InlinePolicyRule` is one `tool + access + reason` triple inside it.

### `conflict.py`
`ConflictError` — two included files both define the same ID; neither is rendered.
`ConflictWarning` — root manifest and an included file share an ID; root wins.
`OrchestrationIssue` — a cycle in the delegation graph, classified as `circular` (unintentional two-hop), `bidirectional` (intentional two-hop declared via `receives_from`), or `cycle` (multi-hop).

---

## `core/parsers/`

The `pericat.yml` loading pipeline, split into four single-responsibility files plus one orchestrator.

### `parser.py`
`PericatParser` is the public orchestrator. `load()` reads YAML via `loader`, converts entities via `transformers`, merges included files via `merger`, analyses the delegation graph via `orchestration`, then assembles the final `PericatManifest` with all precomputed indexes in one pass. `watch()` uses `watchfiles` to hot-reload on disk changes.

The module also manages a **module-level singleton** (`init_parser()`, `get_parser()`). `init_parser_from_manifest()` installs a discovery-built manifest directly, bypassing YAML loading — this is how `pericat discover` feeds data to the API without any config file.

### `loader.py`
File I/O only. `read_yaml()` reads a YAML file. `resolve_include_patterns()` expands glob patterns relative to the root directory. `load_included_file()` loads one included file, enforcing hard rules (no nested includes, dict-format agents/servers). `FileContents` is the container for what one included file contributes (agents + servers only — included files cannot define policy engines or metadata).

### `transformers.py`
Pure functions: raw `dict` → Pydantic model. One function per model type (`parse_agent`, `parse_server`, `parse_tool`, `parse_policy_engine`, etc.). No file I/O, no merge logic.

### `merger.py`
Conflict detection and entity merging. Two-pass approach: first scan all included files to find IDs claimed by more than one (→ `ConflictError`); then merge each entity set, with root-manifest definitions winning over included-file definitions (→ `ConflictWarning` on collision). Root entities always survive; conflicted IDs from the included-vs-included pass are dropped entirely.

### `orchestration.py`
Pure graph analysis. `analyse()` runs DFS on the agent delegation graph (`can_delegate_to` edges) to detect cycles. Classifies each cycle using `receives_from` declarations: if every back-edge in the path was declared intentional via `receives_from`, the issue is `bidirectional`; otherwise `circular` (two-hop) or `cycle` (multi-hop). Deduplication via `frozenset` prevents reporting the same cycle once per starting node.

---

## `core/discovery/`

The autodiscovery pipeline, used by `pericat discover`. Independent of the parsers — the two pipelines share the same models and produce the same `PericatManifest` shape.

### `config_detector.py`
Public entry point: `detect_all()`. Reads config files from known MCP client locations in priority order: custom paths → Claude Code user level → Codex project → Codex user → Claude Desktop / Cursor / Windsurf. First-sighting-wins on duplicate server IDs. Returns a `ConfigDetectionResult` aggregating all sources checked and the deduplicated server inventory.

### `_paths.py`
Platform-aware path resolution for every supported MCP client. Handles macOS/Windows/Linux divergence for Claude Desktop; implements `walk_up_for()` to find project-scoped configs by walking up the directory tree (used for Cursor `.cursor/mcp.json` and Claude Code project `.claude.json`). Defines `CLIENT_PRIORITY` — the deduplication order.

### `_parsers.py`
Shape parsing and environment variable substitution. `parse_mcp_servers()` extracts the `mcpServers` (or `mcp_servers` for Codex TOML) block into `MCPServer` instances. `parse_claude_json()` handles the two-level structure of `~/.claude.json`: user-scoped servers plus project-scoped servers keyed by project root path. `resolve_env_refs()` expands `${VAR}` / `$VAR` references against the process environment.

### `mcp_client.py`
Async MCP client. `probe_server()` spawns a stdio MCP server subprocess, completes the MCP initialize handshake, calls `tools/list`, then tears down. Wrapped in a hard timeout so a hanging server never blocks Pericat. All failure modes (timeout, missing command, protocol error, import error) return a `ToolDiscoveryResult` with a descriptive status — they never raise. `probe_all()` probes many servers concurrently via a semaphore-bounded `asyncio.gather`.

### `tool_discovery.py`
Sync wrappers around the async `mcp_client`. `list_tools_for()` and `list_tools_for_all()` run the async probes on a fresh event loop so the rest of the codebase (which is sync) can call them without managing asyncio. Raises clearly if called from inside an already-running loop, directing callers to use the async API directly.

### `results.py`
Data containers for both discovery stages:
- `DiscoverySource` — what happened when Pericat checked one config file (status, servers found, parse errors).
- `ConfigDetectionResult` — aggregates all sources checked; provides `servers` (deduplicated), `duplicates` list, and summary counts.
- `DiscoveredTool` — one tool from a live `tools/list` response.
- `ToolDiscoveryResult` — outcome of probing one server (status, tools list, error, duration).

### `to_manifest.py`
Bridge from discovery output to `PericatManifest`. `build_manifest()` takes a `ConfigDetectionResult` and optional `ToolDiscoveryResult` list, attaches discovered tools to each server as `DiscoveredToolLite`, and assembles a `PericatManifest` with the same shape the YAML parser produces. In Phase 1, `agents` is always empty — agent discovery (AST scan) is pending.

---

## `ui/src/`

React SPA built with Vite. In development, Vite proxies `/api` to the FastAPI backend. In production, the built output in `ui/dist/` is served directly by FastAPI via `StaticFiles`.

### `App.jsx`
Root component. Manages the active tab (`Dashboard`, `Agents`, `Servers`, `Permissions`), fetches `health`, `agents`, and `servers` at mount (shared across views), and renders the `Topbar` plus the active view.

### `api.js`
All fetch calls in one place. Thin wrappers over `fetch` that throw on non-2xx. Endpoints: `health`, `agents`, `agent(id)`, `servers`, `server(id)`, `matrix`, `engines`, `engineRaw(id)`.

### `views/Dashboard.jsx`
Overview page. Four stat cards (agents, servers, tools, policy engines), a reference-warning banner if the health endpoint reports issues, and two side-by-side lists: agent fleet (status dot, name, tool/server counts, policy engine tag) and MCP server list (name, description, transport, agent count).

### `views/Agents.jsx`
Sidebar-detail layout. Left column: list of agents with status dot and tool/server counts. Right panel: full agent detail — identity card, policy engine card, per-server tool tables with risk/access badges and permission breakdowns, file access list.

### `views/Servers.jsx`
Sidebar-detail layout for MCP servers. Left column: server list with provenance dot (declared / discovered / not-discovered) and transport. Right panel: transport/command config, discovered tools table (from live probe), connected agents table with their tool-access rules.

### `views/Permissions.jsx`
Permission matrix: a scrollable table with tools as columns and agents as rows. Each cell shows an access symbol coloured by effective access state (allowed/denied/partial). A filter bar narrows the view to a specific access state.

### `components/Topbar.jsx`
Navigation bar with tab buttons and a health-status indicator.

### `components/ui.jsx`
Shared UI primitives used across all views: `Card`, `CardHead`, `Tag`, `Dot`, `RiskBadge`, `AccessBadge`, `StatCard`, `Spinner`, `Err`, `Empty`, `SidebarBtn`, `Wrap`. Also `classifyServerProvenance()` — derives a three-state visual badge (declared / discovered / not-discovered) from a server's `source` and `discovery_status` fields.

### `hooks/useFetch.js`
Generic data-fetching hook. Accepts a fetch function and optional dependency array; returns `{ data, loading, error }`.

### `constants.js`
`ACCESS` and `RISK` maps from string values to display properties (colour, symbol, label) used by badges throughout the UI.
