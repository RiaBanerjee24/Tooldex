"""
pericat/core/parsers/loader.py

File I/O concerns only:
  - Reading YAML from disk
  - Resolving glob patterns into file paths
  - Loading a single included file into a _FileContents container
  - _FileContents: what one file contributes (agents + servers)

No merge logic. No conflict detection. No orchestration analysis.
"""
from __future__ import annotations

import glob
import logging
from pathlib import Path
from typing import Optional

import yaml

from pericat.core.models.server import MCPServer
from pericat.core.models.agent import Agent
from pericat.core.parsers.transformers import parse_agent, parse_server

logger = logging.getLogger("pericat.loader")


class FileContents:
    """
    What a single included file contributes to the merged manifest.
    Only agents and servers — included files cannot define anything else.
    """

    def __init__(self, path: str):
        self.path = path
        self.agents: dict[str, Agent] = {}
        self.servers: dict[str, MCPServer] = {}

    def parse_agents(self, raw_agents: dict):
        for agent_id, raw in raw_agents.items():
            self.agents[agent_id] = parse_agent(agent_id, raw, self.path)

    def parse_servers(self, raw_servers: dict):
        for server_id, raw in raw_servers.items():
            self.servers[server_id] = parse_server(server_id, raw)

    def __repr__(self) -> str:
        return (
            f"FileContents(path={self.path!r}, "
            f"agents={list(self.agents.keys())}, "
            f"servers={list(self.servers.keys())})"
        )


def read_yaml(path: Path) -> dict:
    """Read and parse a YAML file. Returns empty dict if file is empty."""
    with open(path) as f:
        return yaml.safe_load(f) or {}


def resolve_include_patterns(
    patterns: list[str],
    root_dir: Path,
    root_path: Path,
) -> list[Path]:
    """
    Expand a list of glob patterns (and explicit paths) relative to root_dir.
    Skips the root manifest itself.
    Returns a deduplicated, sorted list of resolved file paths.
    """
    resolved: list[Path] = []
    seen: set[Path] = set()

    for pattern in patterns:
        full_pattern = str(root_dir / pattern)
        matched = sorted(glob.glob(full_pattern, recursive=True))

        if not matched:
            logger.warning(f"Include pattern matched no files: {pattern!r}")
            continue

        for file_path in matched:
            p = Path(file_path).resolve()

            if p == root_path:
                continue  # never include the root manifest itself
            if p.suffix not in (".yml", ".yaml"):
                continue
            if not p.exists():
                logger.warning(f"Included file does not exist: {p}")
                continue
            if p in seen:
                continue  # deduplicate — two patterns may match the same file

            seen.add(p)
            resolved.append(p)

    return resolved


def load_included_file(path: Path) -> Optional[FileContents]:
    """
    Load a single included file.

    Validates:
      - File is not empty
      - File does not contain an include block (no nested includes)
      - Warns if file contains root-only keys (policy_engines, metadata, etc.)

    Returns None if the file should be skipped entirely.
    """
    try:
        raw = read_yaml(path)
    except Exception as e:
        logger.error(f"Failed to read included file {path}: {e}")
        return None

    if not raw:
        logger.warning(f"Included file is empty, skipping: {path}")
        return None

    # Hard rule: no nested includes
    if "include" in raw:
        logger.error(
            f"Included file '{path}' contains an 'include' block. "
            f"Nested includes are not supported. Skipping file."
        )
        return None

    # Soft warnings for root-only keys that will be silently ignored
    root_only_keys = ("policy_engines", "metadata", "pericat", "observatory")
    for key in root_only_keys:
        if key in raw:
            logger.warning(
                f"Included file '{path}' contains '{key}' which is a "
                f"root-only key and will be ignored."
            )

    fc = FileContents(str(path))

    if "agents" in raw:
        if isinstance(raw["agents"], list):
            logger.error(
                f"Configuration error in included file '{path}':\n"
                f"  'agents' must use the dict format (id as key), not a list.\n"
                f"  Old: agents:\n        - id: my-agent\n"
                f"  New: agents:\n        my-agent:\n"
                f"  Skipping this file."
            )
            return None
        try:
            fc.parse_agents(raw["agents"])
        except Exception as e:
            logger.error(f"Failed to parse agents in '{path}': {e}")

    if "servers" in raw:
        if isinstance(raw["servers"], list):
            logger.error(
                f"Configuration error in included file '{path}':\n"
                f"  'servers' must use the dict format (id as key), not a list.\n"
                f"  Old: servers:\n        - id: my-server\n"
                f"  New: servers:\n        my-server:\n"
                f"  Skipping this file."
            )
            return None
        try:
            fc.parse_servers(raw["servers"])
        except Exception as e:
            logger.error(f"Failed to parse servers in '{path}': {e}")

    return fc


def load_all_included_files(
    patterns: list[str],
    root_dir: Path,
    root_path: Path,
) -> tuple[list[FileContents], list[str]]:
    """
    Resolve all include patterns and load each matched file.

    Returns:
        file_contents  — list of successfully loaded FileContents
        loaded_paths   — list of file path strings (for the file watcher)
    """
    paths = resolve_include_patterns(patterns, root_dir, root_path)
    file_contents: list[FileContents] = []
    loaded_paths: list[str] = []

    for p in paths:
        loaded_paths.append(str(p))
        fc = load_included_file(p)
        if fc is not None:
            file_contents.append(fc)

    return file_contents, loaded_paths