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

import asyncio
import logging
from pathlib import Path
from typing import Callable, Optional

from pericat.core.models import (
    MCPServer,
    Observatory,
    PericatManifest,
    PericatMetadata,
    PolicyEngine,
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
 
        # ── derived: tool list ────────────────────────────────────────────────
        computed_tools = sorted({
            tool.name
            for agent in merged_agents.values()
            for srv in agent.servers
            for tool in srv.tools
        })
 
        # ── orchestration analysis (skip conflicted agents) ───────────────────
        conflicted_agent_ids = {
            e.id for e in errors if e.entity_type == "agent"
        }
        analysable = {
            aid: a
            for aid, a in merged_agents.items()
            if aid not in conflicted_agent_ids
        }
        orch_issues = analyse(analysable)
 
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
        )
        manifest._loaded_files = loaded_paths
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