# 🔭 Tooldex
> Unified MCP Server Observatory — autodiscover, inspect, and monitor Model Context Protocol tools across Claude Code, Cursor, Codex, and Docker

[![PyPI version](https://badge.fury.io/py/tooldex.svg)](https://pypi.org/project/tooldex/)
[![Downloads](https://img.shields.io/pypi/dw/tooldex)](https://pypistats.org/packages/tooldex)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)

Tooldex autodiscovers MCP servers configured across your AI clients — Claude Code, Cursor, Codex, Docker MCP Toolkit — and surfaces every exposed tool in a unified UI with a live REST API. No manual config. Run it from any project directory and it finds everything.

> ⚠️ **Tool Poisoning Attacks are real.** A malicious MCP server can expose dozens of legitimate tools and hide one bad one. Tooldex gives you full visibility into your MCP tool surface before anything executes — essential for any agentic AI environment.

![Tooldex Demo](./assets/tooldex-demo.gif)

---

## Why Tooldex?

As your agentic AI setup grows across distributed systems and multiple clients, you lose track of what MCP servers are running and what tools they expose. Tooldex fixes that:

- 🔍 **Autodiscovery** — finds every MCP server across all your AI clients
- 🛠️ **Tool Inspector** — probes each server live and lists every tool it exposes
- 🖥️ **Unified UI** — single dashboard across all your environments
- ⚡ **REST API** — query your MCP tool surface programmatically
- 🔒 **Security visibility** — spot tool poisoning attempts before they run

---
---

## Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [How discovery works](#how-discovery-works)
- [Config file locations](#config-file-locations)
- [MCP config format](#mcp-config-format)
- [CLI reference](#cli-reference)
- [JSON output](#json-output)
- [API endpoints](#api-endpoints)
- [Testing](#testing)
- [Contributing](#contributing)

---

## Requirements

- Python 3.10 or later
- At least one supported MCP client configured (Claude Code, Cursor, Codex, or Docker MCP Toolkit)

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

## Quick start

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

## How discovery works

When you run `tooldex run`, the following happens in order:

1. **Config scan** — Tooldex reads every known MCP config location for the current directory (see [Config file locations](#config-file-locations)). Each found server gets a qualified ID in the form `{client}:{server_name}` so servers from different clients never collide.

2. **Live probe** — Each discovered server is contacted concurrently. Tooldex calls `tools/list` on it and records which tools it exposes, how long it took, and any errors.

3. **Deduplication** — If the same server name appears in multiple clients (e.g., `browserbase` in both Claude Code and Cursor), both are retained as separate entries under their respective clients. Duplicate server names across clients are reported in the `duplicates` field.

4. **UI** — A local web server starts and serves the unified view.

---

## Config file locations

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

### Docker MCP Toolkit

Tooldex reads all Docker MCP profiles via `docker mcp profile ls`. No additional configuration is needed.

**Project-scoped paths** are discovered by walking up the directory tree from `cwd` until the home directory. This means running `tooldex run` from a nested subdirectory will still find a `.mcp.json` at the project root.

---

## MCP config format

All JSON-based clients use the same `mcpServers` structure. Tooldex understands both `stdio` (command-based) and `http`/`sse` (URL-based) transports.

### stdio server (runs a local process)

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/user"],
      "env": {
        "SOME_VAR": "value"
      }
    },
    "my-db-server": {
      "command": "node",
      "args": ["/path/to/my-server/index.js"],
      "env": {
        "DB_HOST": "localhost",
        "DB_PORT": "5432"
      }
    }
  }
}
```

### HTTP / SSE server (connects to a remote endpoint)

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

Codex uses TOML with an `[mcp_servers.<id>]` table per server:

```toml
[mcp_servers.filesystem]
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem", "."]

[mcp_servers.github]
type = "http"
url = "https://api.githubcopilot.com/mcp/"
```

### What Tooldex detects from these files

For each config file found, Tooldex reports:

- **`status`** — `found` / `not_found` / `empty` / `parse_error` / `read_error`
- **`server_ids`** — list of server names parsed from the file
- **`in_file_duplicates`** — server names that appeared more than once as JSON keys (the last value is kept; all prior definitions are silently dropped by the JSON parser)

For each server probed:

- **`status`** — `found` / `timeout` / `connection_failed` / `protocol_error` / `missing_command`
- **`tools`** — names, descriptions, and input schemas of every tool the server exposes
- **`duration_ms`** — probe wall time
- **`error`** — human-readable failure message when status is not `found`; includes install hints for common missing runtimes (`uvx`, `npx`, `docker`, etc.)

---

## CLI reference

```
tooldex [OPTIONS] COMMAND [ARGS]
```

### Global options

| Flag | Description |
|---|---|
| `--version`, `-V` | Print version and exit |
| `--help`, `-h` | Show help |

### `tooldex run`

Autodiscover MCP servers and start the UI.

```bash
tooldex run [OPTIONS]
```

| Flag | Default | Description |
|---|---|---|
| `--port`, `-p` | `8282` | Starting port. Increments automatically if occupied. |
| `--host` | `127.0.0.1` | Interface to bind the UI server to. |
| `--no-serve` | off | Print discovery summary and exit without starting the server. |
| `--json` | off | Print discovery result as JSON and exit. Implies `--no-serve`. Does not probe servers. |
| `--timeout` | `10.0` | Per-server probe timeout in seconds. |
| `--concurrency` | `8` | Maximum concurrent server probes. |
| `--no-probe <name>` | — | Skip probing a specific server by name. Repeatable. |
| `--config <path>` | — | Additional MCP config file to include. Repeatable. Custom configs are processed first and win on duplicate server IDs. |

All flags accept both `--flag` and `-flag` prefix.

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

# Include an extra config file
tooldex run --config ~/shared/team-servers.json

# Increase timeout for slow servers
tooldex run --timeout 30

# Use all 16 cores for probing
tooldex run --concurrency 16

# Pipe the discovery result into jq
tooldex run --json | jq '.duplicates'
```

---

## JSON output

`tooldex run --json` prints a single JSON object to stdout and exits. No servers are probed; this is fast and side-effect-free for use in scripts and CI.

```json
{
  "sources": [
    {
      "client": "claude_code_user",
      "path": "/home/user/.claude.json",
      "status": "found",
      "error": null,
      "server_ids": ["filesystem", "github"],
      "in_file_duplicates": []
    },
    {
      "client": "mcp_json_user",
      "path": "/home/user/.mcp.json",
      "status": "not_found",
      "error": null,
      "server_ids": [],
      "in_file_duplicates": []
    }
  ],
  "servers": {
    "claude_code_user:filesystem": {
      "name": "filesystem",
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/user"],
      "url": null
    }
  },
  "duplicates": [
    "\"filesystem\" in cursor_user is also configured in claude_code_user",
    "\"firecrawl-mcp\" is a duplicate key in /home/user/.mcp.json (last value kept)"
  ]
}
```

**Fields:**

| Field | Description |
|---|---|
| `sources` | Every config location checked, with status and server IDs found. |
| `servers` | Deduplicated map of all servers, keyed by `{client}:{server_id}`. |
| `duplicates` | Human-readable notes about server name collisions across clients, and duplicate JSON keys within a single file. |

**Exit codes:** `0` on success, `1` on serialisation error.

---

## API endpoints

When the server is running (default `http://127.0.0.1:8282`):

All endpoints respond with or without a trailing slash.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health/` | `status`, current `timestamp`, and `uptime_seconds` since the server started |
| `GET` | `/api/servers/` | All MCP servers with `total_servers`, `total_tools`, `scanned_at`. Per server: `tool_count`, `source_file` |
| `GET` | `/api/servers/{id}/` | Single server with full tool detail |
| `POST` | `/api/servers/{id}/rescan/` | Re-probe a single server and update its tools in place |
| `GET` | `/api/files/` | All config files that were scanned: path, client, status, server IDs found, any parse errors |
| `POST` | `/api/rescan/` | Full rediscovery — re-reads all MCP configs and re-probes every server. Returns `{"status": "already_scanning"}` if a rescan is already in progress. |

---

## Testing

Tooldex has a `pytest` unit-test suite that runs in CI on every PR:

```bash
pip install -e ".[test]"
pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md#testing) for details. For ad-hoc manual checks against your own MCP config:

```bash
# Verify discovery against your local config
tooldex run --no-serve

# Inspect the raw discovery payload
tooldex run --json | jq .

# Check a specific extra config file
tooldex run --config ./my-config.json --json

# Confirm a server is reachable with a longer timeout
tooldex run --timeout 30 --no-probe github
```

To run the package from source without installing:

```bash
git clone <repo>
cd Tooldex
pip install -e .
tooldex --version
```

---

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, the development workflow, and pull request guidelines.
