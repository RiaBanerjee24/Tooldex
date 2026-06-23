# Contributing to Toolpool

Thanks for taking the time to contribute. This guide covers how to set up the project, the expected workflow, and what to include in a pull request.

---

## Contents

- [Getting started](#getting-started)
- [Development workflow](#development-workflow)
- [Coding guidelines](#coding-guidelines)
- [Testing](#testing)
- [Submitting a pull request](#submitting-a-pull-request)
- [Reporting bugs](#reporting-bugs)
- [Adding a new MCP client](#adding-a-new-mcp-client)

---

## Getting started

1. Fork the repository and clone your fork:

   ```bash
   git clone https://github.com/<your-username>/Toolpool.git
   cd Toolpool
   ```

2. Install in editable mode:

   ```bash
   pip install -e .
   toolpool --version
   ```

3. Read [`README.dev.md`](README.dev.md) for an overview of the project structure and architecture before making non-trivial changes.

---

## Development workflow

1. Create a branch off `main`:

   ```bash
   git checkout -b your-feature-name
   ```

2. Make your changes. Keep commits focused — one logical change per commit.

3. Run the unit-test suite and add tests for any new behavior (see [Testing](#testing)) before opening a PR. This is mandatory — the same suite runs in CI on every PR and must pass before a PR is considered healthy.

4. Push your branch and open a pull request against `main`.

---

## Coding guidelines

- Match the existing style of the module you're editing rather than introducing a new convention.
- Keep the sync/async boundary intact: CLI and API handlers are sync; only `core/discovery/mcp_client.py` should contain async I/O. See [`README.dev.md`](README.dev.md#async-architecture).
- New data structures should be Pydantic v2 models, consistent with `core/models/`.
- Don't add dependencies unless necessary. If you do, add them to `pyproject.toml` under `dependencies`.

---

## Testing

Toolpool has a `pytest` unit-test suite under `tests/`, covering config parsing, path resolution, discovery merging, manifest building, the parser singleton, and the API routers. **All tests must pass before a PR can be merged** — the same suite runs in CI (see [`.github/workflows/tests.yml`](.github/workflows/tests.yml)) against Python 3.10–3.12.

Install test dependencies and run the suite:

```bash
pip install -e ".[test]"
pytest
```

Run a single file or a single test while iterating:

```bash
pytest tests/test_parsers.py
pytest tests/test_parsers.py::TestParseMcpServers::test_parses_stdio_server -v
```

If you add or change behavior in `toolpool/core/` or `toolpool/api/`, add or update the corresponding test file in `tests/` as part of your PR — a PR that changes logic without matching test coverage will be asked to add it.

For manual, end-to-end checks against your own MCP config:

```bash
# Verify discovery against your local MCP config
toolpool run --no-serve

# Inspect the raw discovery payload
toolpool run --json | jq .

# Confirm the API server starts and responds
toolpool run
curl http://127.0.0.1:8282/api/health/
```

---

## Submitting a pull request

Use the [pull request template](.github/PULL_REQUEST_TEMPLATE.md) (auto-filled when you open a PR). In summary, include:

- A clear description of what changed and why.
- Any relevant issue numbers.
- The manual verification steps you ran (commands + output, where useful).
- Notes on any follow-up work that's intentionally out of scope.

Keep PRs scoped to a single concern — smaller PRs are easier to review and merge.

---

## Reporting bugs

Open a GitHub issue with:

- Toolpool version (`toolpool --version`)
- Python version and OS
- The MCP client(s) and config involved
- Steps to reproduce, expected behavior, and actual behavior
- Relevant output from `toolpool run --json` or server logs, with secrets redacted

---

## Adding a new MCP client

See [`README.dev.md` → Adding a new MCP client](README.dev.md#adding-a-new-mcp-client) for the exact steps (path resolvers, `build_plan()` registration, optional status enrichment and agent CLI fallback).
