# Trust gate for stdio MCP servers — working summary

Status as of 2026-09-14. This documents one continuous feature built across
a single long session: closing the "Tooldex executes MCP servers before a
human ever approves or the scanner ever inspects them" gap.

## Why this exists

Original finding: Tooldex auto-discovers MCP configs (including
project-scoped ones from repos you didn't write) and immediately spawns
every stdio server to call `tools/list`, with no consent step and before
any security scan runs. A malicious `.mcp.json` in a cloned repo achieves
code execution the moment someone runs `tooldex`. Sandboxing the spawn
itself was explicitly scoped **out** — this work is the consent/approval
layer only.

## Architecture, in one paragraph

The gate lives at the lowest common point: the top of
`mcp_client.probe_server()`, before it dispatches by transport. Every
caller (`tooldex run`, `POST /api/rescan`, `GET /api/rescan/stream`,
`POST /servers/{id}/rescan`) inherits it for free — no per-endpoint checks
needed. Only `stdio` transport is gated; HTTP/SSE servers don't fork a
local process and are untouched. Trust decisions and behavior baselines
live in `~/.tooldex/trust_store.json`, keyed by a content hash of
`(command, args, transport, env key names)` — editing a server's invocation
after approval produces a new key, treated as never-approved.

## What's implemented

### Backend

- **`core/discovery/_fingerprint.py`** — shared `server_key()` hash, factored
  out of `probe_cache.py` so trust_store and probe_cache key identically.
- **`core/discovery/trust_store.py`** — the approval store. Public surface:
  `get_decision` / `set_decision` / `remove_decision` (approve/deny/revoke,
  raw — does not consider file drift), `files_changed_since_approval` (the
  pre-execution file-integrity gate, does consider drift), `get_approved_tools`
  / `record_probe_result` / `diff_tools` / `snapshot_tools` (tools/list
  metadata baseline + drift), `clear_all` (wipe everything).
- **`core/discovery/mcp_client.py`** — `probe_server()`'s stdio branch:
  1. no `"allow"` decision → `NOT_TRUSTED`, never spawns.
  2. `"allow"` but `files_changed_since_approval()` → never spawns; serves
     the last-known tool snapshot with `tools_changed=True` and an
     explanatory error string.
  3. otherwise probes for real; on success, records the result against the
     baseline (`record_probe_result`) and sets `tools_changed` if the fresh
     tools/list differs from what was baselined.
- **`core/discovery/results.py`** — added `ToolDiscoveryStatus.NOT_TRUSTED`;
  added `tools_changed: bool` to `ToolDiscoveryResult`.
- **`core/models/server.py`** — added `trust_status` (`pending`/`allowed`/
  `denied`/`changed`/`None`) and `trust_diff` (list of `{tool, change,
  before, after}`) to `MCPServer`.
- **`core/discovery/to_manifest.py`** — `_trust_status_for()` derives the
  above two fields per server for every manifest build.
- **`api/routers/servers.py`** — `POST /servers/{id}/trust` (approve/deny,
  busts the probe cache on approve so a stale cached denial doesn't linger)
  and `DELETE /servers/{id}/trust` (revoke → pending, clears stale
  tools/findings).
- **`cli.py`** — interactive prompt (3 options: Yes / Yes for all stdio
  servers / No) for any pending stdio server, run *outside* the
  stdout-redirected spinner region (a redirected prompt would hang
  invisibly). New flags `--trust-all-stdio` (CI escape hatch) and
  `--reset-trust <name>`. New commands `tooldex trust <name>` /
  `tooldex untrust <name>`.
- **`_cli_output.py`** — summary reports declined/pending counts, and a
  `tool list changed since approval` line for any drifted server.
- **`_install_check.py`** — on every `tooldex run`, compares the installed
  package's own file mtime against a recorded value in
  `~/.tooldex/install_marker.json`; a mismatch (fresh install, or a
  reinstall of the same version — pip/pipx/uv rewrite files fresh either
  way) wipes `trust_store.json`. Heuristic, not cryptographic — see
  Limitations.

### File-hash pinning (the local-script drift detector)

Tools/list metadata (name/description/schema) can be byte-identical before
and after a body-only code edit — proven empirically (an `echo` tool whose
`return text` became `return text + "123"` was invisible to metadata drift).
For any stdio command that runs a local script file, `trust_store.py` also:

- Resolves `command`/`args` entries to real files (trying cwd-relative,
  falling back to relative-to-the-config-file's-own-directory).
- Walks *down* from each entry point's own directory (not up to a guessed
  "project root") collecting every recognized-source-extension file,
  excluding vendor/VCS noise (`node_modules`, `.venv`, `.git`,
  `__pycache__`, etc.), capped at 500 files as a safety valve.
- Records `{size, mtime, hash}` per file at approval time.
- On every check: stats each tracked file first; if size+mtime are
  unchanged, trusts the recorded hash without re-reading content at all
  (cheap, scales with file count not file size); only falls back to a real
  read+hash when metadata looks different, so a bare `touch` doesn't
  false-positive.
- The interpreter binary itself (when `command` resolves to a real file,
  e.g. an absolute venv python path) is still hashed individually but its
  *directory* is never walked — a real bug caught during testing, since
  venv `bin/` dirs contain unrelated files that got swept in otherwise.

### Frontend

- **`api.js`** — `post()` extended to take a JSON body; new `del()`;
  `trustServer(id, decision)` / `revokeTrust(id)`.
- **`components/servers/TrustGateButtons.jsx`** (new) — Approve/Deny for
  pending, revoke-with-confirm for allowed, approve-link for denied, and a
  warning badge + expandable diff + "approve changes" for the changed state.
  Follows the existing anchored-popup convention (no modal primitive exists
  in this codebase).
- **`serverHelpers.jsx`** — `TrustStatusBadge`; `effectiveStatus()` no
  longer shows a misleading red "failed" badge for `not_trusted`.
- **`assets/icons.jsx`** — added `ShieldIcon`.
- **`ServerSidebarList.jsx` / `views/Servers.jsx`** — badge in the sidebar
  row, `TrustGateButtons` wired into the detail header.

### Tests

`tests/test_trust_store.py`, `tests/test_install_check.py` (new), plus
extensions to `test_mcp_client.py`, `test_cli.py`, `test_api_servers.py`.
480 tests passing as of last run. Added a global `isolated_trust_store`
autouse fixture in `conftest.py` after finding two tests that would
otherwise have silently fallen through to the real
`~/.tooldex/trust_store.json`.

## Key design decisions and why

- **Gate at `probe_server`, not `list_tools_for_all`** — `rescan_stream` in
  `rescan.py` calls `probe_server` directly, bypassing the higher-level
  wrapper entirely. Gating higher would have left that endpoint wide open.
- **Drift → serve stale + flag, never a silent re-prompt loop** — original
  version demoted a file-changed server back to "pending" and re-entered
  the interactive CLI prompt. Reworked per explicit instruction: file-hash
  mismatch now never executes, serves the last-known tool list, and is
  surfaced only as a "changed" badge/message — re-approval is a deliberate,
  separate action (`tooldex trust <name>` / UI button), not an automatic
  reprompt.
- **3-option prompt, not 4** — dropped "No, for all pending" as unnecessary
  complexity; only "Yes, for all stdio servers" batches.
- **`get_decision()` is a pure, non-mutating read** — file-integrity
  checking lives in the separate `files_changed_since_approval()`, checked
  explicitly by `probe_server`. Earlier version had `get_decision` itself
  silently reinterpret a stale "allow" as pending, which produced
  inconsistent behavior once the "serve stale + flag" rework happened.
- **Self-healing over migration** — an approval written before file-hash
  pinning existed (no `file_hashes` key) is not special-cased; the checker
  re-derives "what should be tracked" from the live config every time, so
  a pre-existing approval is correctly flagged as changed the first time
  it's checked, no version/migration bookkeeping required.

## Real bugs found while dogfooding this (in order)

1. **Metadata-only drift blind spot** — same-signature body edit invisible
   to tools/list diffing. → built file-hash pinning.
2. **File-hash path resolution failed silently on cwd mismatch** — relative
   paths only resolved against Tooldex's own process cwd; running from a
   different directory than the config file silently produced empty
   `file_hashes` (fails open). → added config-directory fallback resolution.
3. **Pre-existing approvals never got checked at all** — an "allow" written
   before file-hash pinning existed has no `file_hashes` key, which read as
   "nothing to check" and vacuously passed forever. → made the check
   re-derive live state instead of trusting only the stored dict's keys.
4. **Multi-file servers**: only the literal entry-point file was hashed;
   sibling/imported modules were invisible. Proven with a two-file server
   (`server.py` importing `tools_impl.py`) — editing the import target
   silently changed real behavior with zero detection. → added recursive
   directory-tree hashing.
5. **Interpreter-directory sweep** — first pass at #4 also walked the
   *interpreter's* own directory when `command` resolved to a real file
   path (e.g. a venv's `python3`), sweeping in unrelated files like
   `activate_this.py`. → restricted directory-walking to entry points found
   in `args` with a recognized source extension, never the bare interpreter.
6. **Full-content re-hash on every check doesn't scale** — flagged by the
   user before any code was written this time: 10 servers × up to 2000
   files each meant real cost, and it was paid on every single check
   regardless of whether anything changed. → stat-first fast path (trust a
   recorded hash when size+mtime match; only re-read+hash on a metadata
   mismatch) + lowered the cap from 2000 to 500.
7. **Unrelated finding, not fixed**: `tooldex/bench/mock_server.py` is
   broken against the installed `mcp==2.2.0` (`Server.list_tools()` was
   removed/replaced by `MCPServer.add_tool()` in mcp 2.x).
   `pyproject.toml` pins `mcp>=1.0` with no upper bound. Latent until
   someone runs the bench script.

## Explicitly deferred / not implemented

- **Sandboxing the spawn itself** (bubblewrap/Docker/etc.) — out of scope
  from the start of this feature; approval gate only.
- **Directory-mtime-gated tree walking** — ideated, not built. Would skip
  re-`listdir()`-ing a directory when its own mtime hasn't moved (only
  content-edit detection would still need per-file stat), addressing the
  remaining cost driver (directory traversal) that stat-first didn't touch.
- **Import-graph-based file discovery** — ideated, not built. Would parse
  the entry script's actual imports (Python `ast`, a JS/TS parser) and hash
  only genuinely-reachable files instead of everything with a recognized
  extension sitting in the directory tree. Solves *precision*, not
  performance; inherently per-language; still needs a "hash everything
  nearby" fallback for dynamic imports (`importlib.import_module(x)`,
  computed `require()`); circular imports are a solved problem in this
  approach (visited-set during the graph walk) but must be remembered.
- **Filesystem watching (inotify/FSEvents/etc.)** — the architecturally
  "correct" long-term answer (push notification instead of poll-on-every-
  check), judged as overkill for the realistic scale (a handful to a few
  dozen approved local-script servers per user) and a materially bigger,
  per-OS engineering lift. Also wouldn't eliminate the need for one cold
  scan per fresh `tooldex run` process start.
- **Module invocations and console-script entry points have no file to
  pin** — `python -m mypackage.server` (no literal file path in argv) and
  an installed `command="my-mcp-server"` resolved via PATH both fall back
  to tools/list metadata drift only, with the same blind spot as case #1
  above. Not solved by anything built so far.

## Known limitations, stated plainly

- Tools/list metadata drift (the non-file-hash mechanism) cannot detect a
  behavior change that preserves the tool's name/description/schema — this
  is the *only* protection for package-manager-launched servers (`npx`,
  `uvx`) and for module/console-script invocations, and it has a proven
  blind spot for exactly the "same signature, different body" case.
- File-hash pinning hashes what's in the entry point's own directory tree;
  it does not follow actual imports, so it can both over-include (unrelated
  files sitting in the same folder) and under-include (a dependency that
  lives outside that directory tree — rare, but possible with unusual
  `sys.path`/module resolution setups).
- The stat-first fast path and the reinstall-detection mtime heuristic are
  both defeatable by an adversary sophisticated enough to forge file/
  directory timestamps precisely — an explicitly accepted tradeoff for
  realistic threat models (accidental edits, ordinary supply-chain-style
  swaps), not a cryptographic guarantee.
- "Clear the cache on reinstall" wipes `trust_store.json` only — not
  `probe_cache.json`, `preferences.json`, or the LLM scan cache. Stated
  assumption from the original request, never explicitly confirmed broader.

## Open / not yet decided

The directory-mtime-gating vs. import-graph-precision discussion above was
pure ideation at the user's request — no implementation, no decision made
on which (if either) to build next.
