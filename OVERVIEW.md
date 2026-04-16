# Pericat

**The permission observatory for AI agent fleets.**

You're shipping agents. Fast. Your team is growing. Nobody knows what any agent is actually allowed to do — not the engineer who wrote it, not the security reviewer, not you. The permissions live in OPA rules, scattered YAML files, and mental models that go stale the moment someone else touches the code.

Pericat fixes that.

---

## What it is

Pericat is a local-first visibility layer for AI agent permissions. Point it at your project, run one command, and get a live UI showing exactly what every agent in your fleet can do — which MCP servers it connects to, which tools it can call, what operations are allowed or denied, and which agents can delegate to which other agents.

It reads what you already have. It doesn't enforce anything. It doesn't require you to change your stack, adopt a new policy engine, or send your config to a cloud. It just makes your permission model visible and auditable — in real time, on your machine.

Think Swagger UI, but for agent permissions.

---

## The problem it solves

Modern AI agent systems have a visibility problem that gets worse as they scale.

**MCP** solves tool connectivity — agents can reach external systems. **A2A** solves agent communication — agents can talk to each other. Neither answers the question your security team is actually asking: *what is each agent allowed to do, and who approved it?*

That answer currently lives in:
- OPA `.rego` files that only one person on the team understands
- `pericat.yml` configs that drift from reality
- Verbal agreements in Slack threads
- Nothing at all

When something goes wrong — an agent writes to a table it shouldn't, a router delegates to an agent it has no business talking to — you're debugging blind.

---

## How it works

Pericat reads your `pericat.yml` manifest (or auto-discovers it from your project root) and builds a complete picture of your agent fleet at startup. It watches for file changes and hot-reloads in real time.

### The manifest format

Docker-compose style. Familiar, readable, composable across multiple files:

```yaml
# pericat.yml — root manifest
pericat: "0.1.0"

policy_engines:
  main-policy:
    engine: opa
    type: file
    source: ./policy.rego

include:
  - ./agents/*.yml      # your folder names, your structure
  - ./servers/*.yml

agents:
  router-agent:
    name: "RouterAgent"
    orchestration:
      can_delegate_to: [read-agent, write-agent]
```

```yaml
# agents/read-agent.yml
agents:
  read-agent:
    name: "ReadAgent"
    policy_engine: main-policy
    servers:
      - ref: mysql-prod
        tools:
          - name: mysql_query
            risk: medium
            permissions:
              - operations: [SELECT]
                on: "*"
                access: allowed
    orchestration:
      receives_from: [router-agent]
```

### What Pericat computes

At parse time — not at request time — Pericat builds:

- **Permission matrix** — every agent × every tool, with effective access, risk level, and denial reasons
- **Agent tool index** — O(1) tool lookups per agent
- **Server-agents index** — O(1) lookup of which agents connect to which server
- **Orchestration graph** — who delegates to whom, with automatic detection of circular dependencies, bidirectional loops, and multi-hop cycles
- **Conflict detection** — if two files define the same agent ID, Pericat surfaces it loudly in the UI rather than silently picking one

### Multi-file support

Large fleets don't belong in one file. Pericat lets you structure your manifest however your team works:

```
pericat.yml           ← root: metadata, policy engines, includes
agents/
  read-agent.yml
  write-agent.yml
services/
  billing/
    pericat.yml       ← cross-service explicit reference
```

Folder names are yours. Pericat follows whatever structure you declare in `include:`.

### Conflict resolution

When two files define the same agent ID:

| Scenario | Behavior |
|---|---|
| Root manifest vs included file | Root wins — warning label in UI |
| Two included files | Neither wins — conflict shown in UI, no data rendered |

No silent overwrites. Ever.

### Orchestration visibility

The part nobody else is building: who talks to whom.

```yaml
orchestration:
  can_delegate_to: [read-agent, write-agent]
  receives_from: [router-agent]   # marks bidirectional as intentional
```

Pericat analyses the full delegation graph and flags:

- 🔴 **Circular** — A delegates to B, B delegates back to A (unintentional)
- 🟡 **Bidirectional** — same, but explicitly declared via `receives_from` (intentional)
- 🔴 **Cycle** — multi-hop loop across three or more agents

---

## What it is not

Pericat does not enforce permissions. OPA does that. Cerbos does that. Cedar does that. Pericat reads what your enforcement layer says should be true and makes it visible to humans. It's the layer above enforcement, not a replacement for it.

Pericat does not require a cloud account. Everything runs locally. Your manifest never leaves your machine.

Pericat does not lock you into a policy format. It reads OPA, Cedar, Casbin, or any file-based policy — it displays the source, it doesn't execute it.

---

## Who it's for

**Teams shipping AI agents to production** — where "what can this agent do?" needs a real answer, not a grep through Rego files.

**Security reviewers** — who need to sign off on agent permissions without becoming OPA experts.

**Platform engineers** — managing fleets of agents across multiple microservices, who need a single place to see the full picture.

**Solo engineers** — who worked on an agent system two weeks ago and need to remember what they decided.

---

## The stack

- **Backend** — FastAPI, Python, Pydantic v2
- **Config format** — YAML (docker-compose style)
- **Policy engines** — OPA, Cedar, Casbin, or any file-based engine (display only)
- **Protocol alignment** — MCP-native (servers and tools map directly to MCP concepts), A2A-aware (orchestration block models delegation)
- **Hot reload** — `watchfiles` — live updates on every manifest change
- **Local first** — zero cloud dependency, zero telemetry

---

## Get started

```bash
pip install pericat
cd your-project
pericat run
```

Pericat auto-discovers your `pericat.yml` by walking up from wherever you run the command. Or point it explicitly:

```bash
pericat run --config ./path/to/pericat.yml
```

That's it.

---

## Roadmap

- **Decorator support** — define agent permissions directly in Python, generate `pericat.yml` automatically
- **Change timeline** — structured history of every permission change, with git author and optional reason annotation
- **Cloud sync** — share your fleet's permission state across a team, with a hosted dashboard
- **OSSA/ADL import** — accept agent definition files from emerging standards as an alternative input format