"""
toolpool/core/parsers/merger.py

Merges root manifest entities with included file entities.
Detects and classifies conflicts.

Conflict rules:
  root vs included file  → root wins, emits ConflictWarning
  included vs included   → ConflictError, neither entity is rendered

No file I/O. No orchestration logic. Pure merge + conflict detection.
"""
from __future__ import annotations

from toolpool.core.models.agent import Agent
from toolpool.core.models.conflict import ConflictError, ConflictWarning
from toolpool.core.models.server import MCPServer

from toolpool.core.parsers.loader import FileContents

# Type alias for the merge result
MergeResult = tuple[
    dict[str, Agent],
    dict[str, MCPServer],
    list[ConflictError],
    list[ConflictWarning],
]


def _detect_included_conflicts(
    included: list[FileContents],
    entity_type: str,
) -> tuple[set[str], list[ConflictError]]:
    """
    Find ids that are claimed by more than one included file.
    Returns the set of conflicted ids and the ConflictError list.
    """
    # id → first file that claimed it
    first_seen: dict[str, str] = {}
    errored: set[str] = set()
    errors: list[ConflictError] = []

    for fc in included:
        entities = fc.agents if entity_type == "agent" else fc.servers

        for entity_id in entities:
            if entity_id in errored:
                # Already in error state — add this file to the existing error
                for e in errors:
                    if e.entity_type == entity_type and e.id == entity_id:
                        if fc.path not in e.files:
                            e.files.append(fc.path)
                continue

            if entity_id in first_seen:
                # Second file claiming same id → conflict
                errored.add(entity_id)
                errors.append(ConflictError(
                    entity_type=entity_type,
                    id=entity_id,
                    files=[first_seen[entity_id], fc.path],
                    message=(
                        f"{entity_type.capitalize()} '{entity_id}' is defined "
                        f"in multiple included files. Neither will be rendered "
                        f"until the conflict is resolved."
                    ),
                ))
            else:
                first_seen[entity_id] = fc.path

    return errored, errors


def _merge_entities(
    root_entities: dict,
    included: list[FileContents],
    errored_ids: set[str],
    root_file: str,
    entity_type: str,
    get_entities,
) -> tuple[dict, list[ConflictWarning]]:
    """
    Generic merge for either agents or servers.
    Starts with root entities (they always win).
    Adds non-conflicted included entities.
    Emits ConflictWarning when root and included share an id.
    """
    merged = dict(root_entities)
    warnings: list[ConflictWarning] = []

    for fc in included:
        entities = get_entities(fc)

        for entity_id, entity in entities.items():
            if entity_id in errored_ids:
                continue  # conflict error — skip entirely

            if entity_id in root_entities:
                # Root wins — emit warning
                warnings.append(ConflictWarning(
                    entity_type=entity_type,
                    id=entity_id,
                    winner_file=root_file,
                    loser_file=fc.path,
                    message=(
                        f"{entity_type.capitalize()} '{entity_id}' is defined "
                        f"in both the root manifest and '{fc.path}'. "
                        f"The root definition takes precedence."
                    ),
                ))
            else:
                merged[entity_id] = entity

    return merged, warnings


def merge(
    root_agents: dict[str, Agent],
    root_servers: dict[str, MCPServer],
    root_file: str,
    included: list[FileContents],
) -> MergeResult:
    """
    Merge root manifest entities with all included file entities.

    Steps:
      1. Find conflicts among included files (included vs included)
      2. Merge agents: root wins over included, skip errored ids
      3. Merge servers: same rules
      4. Return merged dicts + all conflict errors + all conflict warnings
    """
    # Step 1: detect conflicts within included files
    errored_agent_ids, agent_errors = _detect_included_conflicts(
        included, "agent"
    )
    errored_server_ids, server_errors = _detect_included_conflicts(
        included, "server"
    )

    all_errors = agent_errors + server_errors

    # Step 2: merge agents
    merged_agents, agent_warnings = _merge_entities(
        root_entities=root_agents,
        included=included,
        errored_ids=errored_agent_ids,
        root_file=root_file,
        entity_type="agent",
        get_entities=lambda fc: fc.agents,
    )

    # Step 3: merge servers
    merged_servers, server_warnings = _merge_entities(
        root_entities=root_servers,
        included=included,
        errored_ids=errored_server_ids,
        root_file=root_file,
        entity_type="server",
        get_entities=lambda fc: fc.servers,
    )

    all_warnings = agent_warnings + server_warnings

    return merged_agents, merged_servers, all_errors, all_warnings