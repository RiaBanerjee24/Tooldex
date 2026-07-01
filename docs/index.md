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

## API Endpoints

When the server is running (default `http://127.0.0.1:8282`). All endpoints respond with or without a trailing slash.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health/` | `status`, current `timestamp`, and `uptime_seconds` since the server started |
| `GET` | `/api/servers/` | All MCP servers with `total_servers`, `total_tools`, `scanned_at`. Per server: `tool_count`, `source_file` |
| `GET` | `/api/servers/{id}/` | Single server with full tool detail |
| `POST` | `/api/servers/{id}/rescan/` | Re-probe a single server and update its tools in place |
| `GET` | `/api/files/` | All config files that were scanned: path, client, status, server IDs found, any parse errors |
| `POST` | `/api/rescan/` | Full rediscovery — re-reads all configs and re-probes every server. Returns `{"status": "already_scanning"}` if a rescan is already running. |

---

## Architecture

### Project Structure

```
tooldex/
├── __init__.py              # __version__ via importlib.metadata
├── cli.py                   # Typer CLI — run command, flags, startup
├── _cli_output.py           # print_banner(), print_summary(), result_as_json()
├── settings.py              # debug flag
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
        ├── to_manifest.py       # Discovery output → TooldexManifest
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

**3. Wire up the UI** — add to `CLIENT_META` and `GROUP_ORDER` in `Servers.jsx`, then rebuild:

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
