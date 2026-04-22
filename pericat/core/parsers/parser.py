"""
pericat/core/parsers/parser.py

PericatParser — the public orchestrator.
Coordinates loading, merging, and analysis. Owns the singleton.

This file's only job:
  - Define PericatParser (load, reload, watch, validate_references)
  - Manage the module-level singleton (init_parser, get_parser)

All heavy lifting is delegated to:
  loader.py        — file I/O and glob resolution
  transformers.py  — raw dict → model conversion
  merger.py        — conflict detection and entity merging
  orchestration.py — delegation graph analysis
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

from pericat.core.models import (
    MCPServer,
    Observatory,
    PericatManifest,
    PericatMetadata,
    PolicyEngine,
    Tool,
)
from pericat.core.parsers.loader import load_all_included_files, read_yaml
from pericat.core.parsers.merger import merge
from pericat.core.parsers.orchestration import analyse
from pericat.core.parsers.transformers import (
    parse_agent,
    parse_policy_engine,
    parse_server,
)

logger = logging.getLogger("pericat.parser")


class PericatParser:

    def __init__(self, config_path: str = "./pericat.yml"):
        self.config_path = Path(config_path).resolve()
        self._manifest: Optional[PericatManifest] = None
        self._reload_callbacks: list[Callable[[PericatManifest], None]] = []

    # ── public API ────────────────────────────────────────────────────────────

    def load(self) -> PericatManifest:
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"pericat.yml not found at: {self.config_path}\n"
                f"Create a pericat.yml in your project root "
                f"or pass --config <path>"
            )
        raw = read_yaml(self.config_path)
        if not raw:
            raise ValueError("pericat.yml is empty")

        self._manifest = self._build(raw)
        logger.info(
            f"Loaded — "
            f"{len(self._manifest.agents)} agents, "
            f"{len(self._manifest.servers)} servers, "
            f"{len(self._manifest.policy_engines)} policy engines, "
            f"{len(self._manifest.all_tools)} tools, "
            f"{len(self._manifest.conflict_errors)} conflict errors, "
            f"{len(self._manifest.conflict_warnings)} conflict warnings, "
            f"{len(self._manifest.orchestration_issues)} orchestration issues"
        )
        return self._manifest

    @property
    def manifest(self) -> PericatManifest:
        if self._manifest is None:
            return self.load()
        return self._manifest

    def reload(self) -> PericatManifest:
        old = self._manifest
        try:
            new = self.load()
            for cb in self._reload_callbacks:
                try:
                    cb(new)
                except Exception as e:
                    logger.error(f"Reload callback error: {e}")
            return new
        except Exception as e:
            logger.error(f"Failed to reload pericat.yml: {e}")
            if old is not None:
                logger.warning("Keeping previous manifest")
                return old
            raise

    def on_reload(self, callback: Callable[[PericatManifest], None]):
        self._reload_callbacks.append(callback)

    async def watch(self):
        try:
            from watchfiles import awatch
        except ImportError:
            logger.warning(
                "Hot reload disabled — install watchfiles: pip install watchfiles"
            )
            return

        files_to_watch = [str(self.config_path)]
        if self._manifest and self._manifest._loaded_files:
            files_to_watch.extend(self._manifest._loaded_files)

        logger.info(f"Watching {len(files_to_watch)} file(s) for changes...")
        async for _ in awatch(*files_to_watch):
            logger.info("File change detected — reloading")
            self.reload()

    def validate_references(self) -> list[str]:
        """
        Post-load validation of cross-references.
        Returns a list of warning strings — does not raise.
        """
        manifest = self.manifest
        warnings: list[str] = []
        server_ids = set(manifest.servers.keys())
        engine_ids = set(manifest.policy_engines.keys())
        agent_ids = set(manifest.agents.keys())
        conflicted_agents = manifest.conflicted_ids("agent")

        for agent_id, agent in manifest.agents.items():
            if agent_id in conflicted_agents:
                continue

            for srv_ref in agent.servers:
                if srv_ref.ref not in server_ids:
                    warnings.append(
                        f"Agent '{agent_id}' references unknown "
                        f"server '{srv_ref.ref}'"
                    )

            if agent.policy_engine and agent.policy_engine not in engine_ids:
                warnings.append(
                    f"Agent '{agent_id}' references unknown "
                    f"policy engine '{agent.policy_engine}'"
                )

            for target in agent.orchestration.can_delegate_to:
                if target not in agent_ids:
                    warnings.append(
                        f"Agent '{agent_id}' can_delegate_to "
                        f"unknown agent '{target}'"
                    )

            for source in agent.orchestration.receives_from:
                if source not in agent_ids:
                    warnings.append(
                        f"Agent '{agent_id}' receives_from "
                        f"unknown agent '{source}'"
                    )

        return warnings

    # ── private ───────────────────────────────────────────────────────────────

    def _assert_dict_format(self, raw: dict, key: str):
        """
        Validates that a top-level key, if present, is a dict (docker-compose
        style) and not a list (old pericat format).

        Raises a clear ValueError pointing at the user's file — not at Pericat.
        """
        value = raw.get(key)
        if value is None:
            return  # key not present — fine, it's optional
        if isinstance(value, list):
            raise ValueError(
                f"\n\n  Configuration error in: {self.config_path}\n\n"
                f"  '{key}' must use the dict format (id as key), not a list.\n\n"
                f"  Old format (not supported):\n"
                f"    {key}:\n"
                f"      - id: my-{key[:-1]}\n"
                f"        ...\n\n"
                f"  New format:\n"
                f"    {key}:\n"
                f"      my-{key[:-1]}:\n"
                f"        ...\n\n"
                f"  See the migration guide: https://docs.pericat.dev/migration\n"
            )
        if not isinstance(value, dict):
            raise ValueError(
                f"\n\n  Configuration error in: {self.config_path}\n\n"
                f"  '{key}' must be a mapping (dict), "
                f"got {type(value).__name__}.\n"
            )

    def _build(self, raw: dict) -> PericatManifest:
        root_dir = self.config_path.parent

        # ── validate top-level shapes before touching them ────────────────────
        # Gives the user a clear message if they're using the old list format
        # instead of blaming Pericat internals.
        self._assert_dict_format(raw, "policy_engines")
        self._assert_dict_format(raw, "agents")
        self._assert_dict_format(raw, "servers")

        # ── global config (root only) ─────────────────────────────────────────
        metadata = PericatMetadata(**raw.get("metadata", {"name": "Pericat"}))
        observatory = Observatory(**raw.get("observatory", {}))

        policy_engines: dict[str, PolicyEngine] = {
            eid: parse_policy_engine(eid, engine_raw)
            for eid, engine_raw in raw.get("policy_engines", {}).items()
        }

        # ── root inline entities ──────────────────────────────────────────────
        root_path_str = str(self.config_path)

        root_agents = {
            aid: parse_agent(aid, agent_raw, root_path_str)
            for aid, agent_raw in raw.get("agents", {}).items()
        }

        root_servers = {
            sid: parse_server(sid, server_raw)
            for sid, server_raw in raw.get("servers", {}).items()
        }

        # ── load included files ───────────────────────────────────────────────
        include_patterns: list[str] = raw.get("include") or []
        included_files, loaded_paths = load_all_included_files(
            patterns=include_patterns,
            root_dir=root_dir,
            root_path=self.config_path,
        )

        # ── merge ─────────────────────────────────────────────────────────────
        merged_agents, merged_servers, errors, warnings = merge(
            root_agents=root_agents,
            root_servers=root_servers,
            root_file=root_path_str,
            included=included_files,
        )

        # ── orchestration analysis (skip conflicted agents) ───────────────────
        conflicted_agent_ids = {
            e.id for e in errors if e.entity_type == "agent"
        }
        conflicted_server_ids = {
            e.id for e in errors if e.entity_type == "server"
        }
        warned_agent_ids = {
            w.id for w in warnings if w.entity_type == "agent"
        }
        warned_server_ids = {
            w.id for w in warnings if w.entity_type == "server"
        }

        analysable = {
            aid: a
            for aid, a in merged_agents.items()
            if aid not in conflicted_agent_ids
        }
        orch_issues = analyse(analysable)

        # ── single pass: build all indexes + tool list ────────────────────────
        # One loop over all agents computes:
        #   - all_tools         (sorted unique tool names)
        #   - agent_tool_index  (agent_id → {tool_name → Tool})
        #   - server_agents_index (server_id → [{"id", "name"}])
        all_tools_set: set[str] = set()
        agent_tool_index: dict[str, dict[str, Tool]] = {}
        server_agents_index: dict[str, list[dict]] = {}

        for agent_id, agent in merged_agents.items():
            tool_map: dict[str, Tool] = {}
            for srv_ref in agent.servers:
                # server_agents_index
                server_agents_index.setdefault(srv_ref.ref, []).append({
                    "id": agent_id,
                    "name": agent.name,
                })
                # agent_tool_index + all_tools
                for tool in srv_ref.tools:
                    all_tools_set.add(tool.name)
                    # last-write wins if same tool name appears in
                    # multiple server refs — consistent with old behaviour
                    tool_map[tool.name] = tool
            agent_tool_index[agent_id] = tool_map

        computed_tools = sorted(all_tools_set)

        # ── assemble manifest ─────────────────────────────────────────────────
        manifest = PericatManifest(
            pericat=raw.get("pericat", "0.1.0"),
            metadata=metadata,
            policy_engines=policy_engines,
            servers=merged_servers,
            agents=merged_agents,
            include=include_patterns if include_patterns else None,
            observatory=observatory,
            conflict_errors=errors,
            conflict_warnings=warnings,
            orchestration_issues=orch_issues,
            all_tools=computed_tools,
            agent_tool_index=agent_tool_index,
            server_agents_index=server_agents_index,
        )
        manifest._loaded_files = loaded_paths
        manifest._conflicted_agent_ids = conflicted_agent_ids
        manifest._conflicted_server_ids = conflicted_server_ids
        manifest._warned_agent_ids = warned_agent_ids
        manifest._warned_server_ids = warned_server_ids
        return manifest


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_parser: Optional[PericatParser] = None


def get_parser() -> PericatParser:
    global _parser
    if _parser is None:
        raise RuntimeError(
            "PericatParser not initialized — call init_parser() at startup"
        )
    return _parser


def init_parser(config_path: str) -> PericatParser:
    global _parser
    _parser = PericatParser(config_path)
    _parser.load()
    return _parser


def init_parser_from_manifest(manifest: PericatManifest) -> PericatParser:
    """
    Install a pre-built manifest into the parser singleton.

    Used by `pericat discover`: discovery builds a manifest directly (no
    YAML involved), then hands it here so the API routers can serve it
    through the existing get_parser() → manifest pipeline.

    The returned parser has no config_path in the usual sense — `.load()`
    and `.reload()` would fail, which is intentional. Discovery-mode
    manifests aren't hot-reloaded the way YAML manifests are; re-running
    `pericat discover` is the way to refresh.
    """
    global _parser
    _parser = PericatParser.__new__(PericatParser)
    _parser.config_path = None                           # sentinel: no YAML origin
    _parser._manifest = manifest
    _parser._reload_callbacks = []
    return _parser