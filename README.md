# Pericat — Configuration & Setup Guide

## Installation

```bash
pip install pericat
```

---

## Quick start

```bash
cd your-project
pericat run
```

Pericat searches upward from your current directory for a `pericat.yml` or `pericat.yaml` file. If you want to point at a specific file:

```bash
pericat run --config ./path/to/pericat.yml
pericat run --config ./path/to/pericat.yml --port 9000 --host 0.0.0.0
pericat discover
```

---

## Project structure

Pericat supports two layouts — single file for small projects, multi-file for larger ones. Both produce the same result.

### Single file

Everything in one `pericat.yml` at your project root:

```
your-project/
  pericat.yml
  policy.rego
```

### Multi-file

Split agents and servers across multiple files. Folder names are yours — Pericat follows whatever you declare in `include:`:

```
your-project/
  pericat.yml           ← root manifest
  agents/
    read-agent.yml
    write-agent.yml
    file-agent.yml
  servers/
    mysql-prod.yml
  policy.rego
```

---

## The root manifest (`pericat.yml`)

The root manifest is the only required file. It defines global config and optionally declares which other files to include.

```yaml
pericat: "0.1.0"

metadata:
  name: "My Agent Fleet"
  description: "Optional description"
  owner: "your-team"
  updated: "2026-04-15"

policy_engines:
  main-policy:
    engine: opa                     # opa | cedar | casbin | custom
    type: file                      # file | http | inline
    source: ./policy.rego           # path to your policy file
    description: "ABAC enforcement"
    policy_path: "agent.authz.allow" # optional, default shown

include:                            # optional — omit for single-file mode
  - ./agents/*.yml                  # glob patterns
  - ./servers/*.yml
  - ./teams/**/*.yml                # recursive glob
  - ./services/billing/pericat.yml  # explicit path for cross-service refs

# inline agents (optional — can also live in included files)
agents:
  router-agent:
    name: "RouterAgent"
    # ... see agent format below

# inline servers (optional — can also live in included files)
servers:
  mysql-prod:
    name: "MySQL Production"
    # ... see server format below

observatory:
  audit_log: ./logs/audit.log
  changes_log: ./logs/changes.txt
```

### Notes on `include:`

- Glob patterns are resolved relative to the root manifest's directory
- Included files can only contain `agents:` and `servers:` — not `policy_engines:`, `metadata:`, or `include:` (no nested includes)
- Folder names are entirely up to you — `agents/`, `my-bots/`, `services/` — Pericat doesn't care

---

## Policy engines

Defined once in the root manifest. Referenced by agents via their id.

```yaml
policy_engines:
  main-policy:               # ← this is the id agents reference
    engine: opa              # free label — "opa", "cedar", "casbin", "custom"
    type: file               # how the policy is stored
    source: ./policy.rego    # path to the file
    description: "Optional description"
    policy_path: "agent.authz.allow"  # OPA package.rule path (optional)
```

| Field | Required | Description |
|---|---|---|
| `engine` | yes | Free label for the policy engine type |
| `type` | yes | `file`, `http`, or `inline` |
| `source` | yes | File path (type=file) or URL (type=http) |
| `description` | no | Human-readable description |
| `policy_path` | no | OPA rule path, default: `agent.authz.allow` |

Pericat reads and displays policy files — it does not execute them.

---

## Servers

MCP servers defined once, referenced by multiple agents.

```yaml
servers:
  mysql-prod:                          # ← id used in agent server refs
    name: "MySQL Production"           # display name
    package: "@benborla29/mcp-server-mysql"  # npm package (optional)
    transport: stdio                   # stdio | sse | streamable-http
    command: npx                       # command to run
    args: ["-y", "@benborla29/mcp-server-mysql"]
    env:
      MYSQL_HOST: "127.0.0.1"
      MYSQL_PORT: "3306"
      MYSQL_USER: "root"
      MYSQL_DB: "your_db"
    description: "Primary MySQL database"

  filesystem-local:
    name: "Local Filesystem"
    package: "@modelcontextprotocol/server-filesystem"
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "./logs"]
    description: "Sandboxed to logs directory only"

  remote-api:
    name: "Remote API Server"
    transport: sse
    url: "https://api.example.com/mcp"  # for http/sse transport
    description: "External API via SSE"
```

| Field | Required | Description |
|---|---|---|
| `name` | yes | Display name |
| `transport` | no | Default: `stdio`. Options: `stdio`, `sse`, `streamable-http` |
| `command` | no | Command to launch the server |
| `args` | no | Arguments list |
| `env` | no | Environment variables |
| `url` | no | URL for http/sse transport |
| `package` | no | npm package name (informational) |
| `description` | no | Human-readable description |

---

## Agents

```yaml
agents:
  read-agent:                          # ← agent id
    name: "ReadAgent"                  # display name
    description: "Read-only queries"
    framework: llamaindex              # llamaindex | langchain | crewai | custom
    status: active                     # active | inactive | deprecated
    owner: "data-team"
    tags: [database, read-only]
    background: false                  # true for background workers
    policy_engine: main-policy         # ref to a policy_engines id (or null)

    identity:
      type: internal                   # internal | oauth2 | service_account | api_key
      token_lifetime: session
      client_id: null                  # for oauth2
      scopes: []

    servers:
      - ref: mysql-prod                # ref to a servers id
        tools:
          - name: mysql_query
            risk: medium               # low | medium | high | critical
            permissions:
              - operations: [SELECT]
                on: "*"               # table/resource name, or "*" for all
                access: allowed       # allowed | denied
              - operations: [INSERT, UPDATE]
                on: api_orders
                access: allowed
              - operations: [DELETE, DROP]
                on: "*"
                access: denied
                denied_by: "policy rule: no destructive ops"

    file_access:                       # for filesystem agents
      - path: "./logs/**"
        permission: read/write         # read | write | read/write | denied
        note: "Sandboxed to logs only"

    orchestration:
      can_delegate_to:                 # agent ids this agent may delegate to
        - write-agent
      receives_from:                   # marks intentional incoming delegation
        - router-agent
```

### Tool format

Tools can be declared with full permissions detail or as a shorthand:

**Full format:**
```yaml
tools:
  - name: mysql_query
    risk: high
    permissions:
      - operations: [SELECT]
        on: "*"
        access: allowed
      - operations: [DELETE]
        on: "*"
        access: denied
        denied_by: "no destructive ops"
```

**Shorthand (for simple allow/deny):**
```yaml
tools:
  - { name: read_file,    risk: low,      access: allowed }
  - { name: delete_file,  risk: critical, access: denied, denied_by: "no deletes" }
```

### Risk levels

| Level | Meaning |
|---|---|
| `low` | Read-only, no side effects |
| `medium` | Writes, but scoped and reversible |
| `high` | Broad writes or sensitive data access |
| `critical` | Destructive or irreversible operations |

### Orchestration

The `orchestration` block models A2A delegation between agents:

```yaml
orchestration:
  can_delegate_to:    # this agent may hand tasks TO these agents
    - read-agent
    - write-agent
  receives_from:      # declares intentional incoming delegation
    - router-agent    # signals: "I know router sends tasks to me"
```

Pericat analyses the full delegation graph and flags:

| Pattern | Label | Meaning |
|---|---|---|
| A → B → A | 🔴 `circular` | Unintentional loop |
| A → B → A with `receives_from` | 🟡 `bidirectional` | Intentional, but flagged |
| A → B → C → A | 🔴 `cycle` | Multi-hop loop |
| A → B only | ✅ `one-way` | Clean delegation |

---

## Multi-file: included agent/server files

Included files follow the same format as inline definitions, but only `agents:` and `servers:` are allowed:

```yaml
# agents/write-agent.yml
agents:
  write-agent:
    name: "WriteAgent"
    policy_engine: main-policy
    servers:
      - ref: mysql-prod
        tools:
          - name: mysql_query
            risk: high
            permissions:
              - operations: [SELECT]
                on: "*"
                access: allowed
              - operations: [INSERT, UPDATE]
                on: api_orders
                access: allowed
              - operations: [DELETE]
                on: "*"
                access: denied
                denied_by: "no destructive ops"
```

Multiple agents per file is fine:

```yaml
# agents/database-agents.yml
agents:
  read-agent:
    name: "ReadAgent"
    ...
  write-agent:
    name: "WriteAgent"
    ...
```

---

## Conflict rules

| Scenario | What happens |
|---|---|
| Agent id in root + included file | Root wins. UI shows ⚠ warning label on the agent |
| Agent id in two included files | Neither wins. UI shows ❌ conflict — no data rendered until resolved |
| Server id conflicts | Same rules as agents |
| Policy engine id collision | Invalid YAML — caught before Pericat loads |

---

## API endpoints

Once running, Pericat exposes:

| Endpoint | Description |
|---|---|
| `GET /api/agents` | All agents with server connections and orchestration summary |
| `GET /api/agents/{id}` | Single agent detail with resolved servers, tools, and orchestration |
| `GET /api/servers` | All servers with connected agents |
| `GET /api/servers/{id}` | Single server with full agent and tool detail |
| `GET /api/policy/matrix` | Full agent × tool permission matrix |
| `GET /api/policy/engines` | All declared policy engines |
| `GET /api/policy/engines/{id}/raw` | Raw policy file content |
| `GET /api/conflicts` | All conflict errors and warnings |
| `GET /api/orchestration` | Full delegation graph with detected issues |
| `GET /api/health` | Health check |

---

## CLI reference

```bash
# auto-discover pericat.yml from current directory upward
pericat run

# explicit config path
pericat run --config ./pericat.yml

# custom host and port
pericat run --port 9000 --host 0.0.0.0

# all options
pericat run --config <path> --port <port> --host <host>
```

---

## Hot reload

Pericat watches all loaded files — the root manifest and every included file — for changes. When any file is saved, the manifest is reloaded automatically and the UI reflects the new state within seconds. No restart needed.

---

## Validations run at startup

Pericat checks the following and prints warnings before starting:

- Agent references an unknown server id
- Agent references an unknown policy engine id
- Agent `can_delegate_to` references an unknown agent id
- Agent `receives_from` references an unknown agent id

These are warnings, not errors — Pericat starts regardless. Conflicts (duplicate ids) are surfaced in the UI at runtime.