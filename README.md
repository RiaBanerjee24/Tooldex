# Pericat

**AI Agent Permission Observatory** — Swagger for your AI agents.

Write a `pericat.yml` describing your agents and their permissions. Run `pericat serve`. Open your browser.

## Install

```bash
pip install pericat-agent
```

## Usage

```bash
# 1. write your pericat.yml (see example below)
# 2. start pericat
pericat serve

# custom config path or port
pericat serve --config ./path/to/pericat.yml --port 8282
```

Open `http://localhost:8282/` — that's it.

## pericat.yml

```yaml
pericat: "0.1.0"

metadata:
  name: "My Agent System"

servers:
  - id: my-db
    name: "My Database"
    transport: stdio
    command: npx
    args: ["-y", "@benborla29/mcp-server-mysql"]

agents:
  - id: read-agent
    name: "ReadAgent"
    servers:
      - ref: my-db
        tools:
          - name: mysql_query
            risk: medium
            permissions:
              - operations: [SELECT]
                on: "*"
                access: allowed

observatory:
  audit_log: ./logs/audit.log
```

## What you see

- **Overview** — all agents, servers, and policy engines at a glance
- **Agents** — click any agent to see its full permission detail
- **Servers** — click any server to see which agents connect and what they can do
- **Access Matrix** — agent × tool grid showing allowed / denied / partial
- **Audit Log** — live stream of every tool call your agents make

## Credits 
cat face by corpus delicti from <a href="https://thenounproject.com/browse/icons/term/cat-face/" target="_blank" title="cat face Icons">Noun Project</a> (CC BY 3.0)