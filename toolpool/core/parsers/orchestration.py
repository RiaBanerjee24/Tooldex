"""
toolpool/core/parsers/orchestration.py

Analyses the agent delegation graph for orchestration issues.

Detects:
  circular     — A → B → A  (two-hop loop, unintentional)
  bidirectional — A → B → A  (two-hop, intentional via receives_from)
  cycle        — A → B → C → ... → A  (multi-hop loop)

No file I/O. No merge logic. Pure graph analysis.
Input: dict of agents. Output: list of OrchestrationIssue.
"""
from __future__ import annotations

from toolpool.core.models.agent import Agent
from toolpool.core.models.conflict import OrchestrationIssue


def _build_graph(
    agents: dict[str, Agent],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """
    Build two adjacency structures from agent orchestration declarations.

    Returns:
        graph         — agent_id → set of agent_ids it can_delegate_to
        receives_from — agent_id → set of agent_ids it declared in receives_from
    """
    graph: dict[str, set[str]] = {}
    receives_from: dict[str, set[str]] = {}

    for agent_id, agent in agents.items():
        graph[agent_id] = set(agent.orchestration.can_delegate_to)
        receives_from[agent_id] = set(agent.orchestration.receives_from)

    return graph, receives_from


def _is_intentional(
    path: list[str],
    receives_from: dict[str, set[str]],
) -> bool:
    """
    A cycle is intentional if every back-edge in the path was declared
    via receives_from by the destination agent.

    For each step path[i] → path[i+1], check whether path[i+1]
    explicitly declared path[i] in its receives_from list.
    If any back-edge is undeclared, the cycle is unintentional.
    """
    for i in range(len(path) - 1):
        src = path[i]
        dst = path[i + 1]
        if src not in receives_from.get(dst, set()):
            return False
    return True


def analyse(agents: dict[str, Agent]) -> list[OrchestrationIssue]:
    """
    Run DFS on the delegation graph to find all cycles.

    For each agent as a starting node, explore outgoing delegation edges.
    When we find a path back to the start node, record an issue.

    Deduplication: cycles are stored as frozensets of their node sets
    so the same cycle isn't reported once per starting node.
    """
    if not agents:
        return []

    graph, receives_from = _build_graph(agents)
    issues: list[OrchestrationIssue] = []
    visited_cycles: set[frozenset] = set()

    def dfs(
        start: str,
        current: str,
        path: list[str],
        in_path: set[str],
    ):
        for neighbor in graph.get(current, set()):
            if neighbor == start and len(path) >= 2:
                # Found a cycle back to start
                cycle_path = path + [neighbor]
                cycle_key = frozenset(path)

                if cycle_key in visited_cycles:
                    continue
                visited_cycles.add(cycle_key)

                intentional = _is_intentional(cycle_path, receives_from)

                if len(path) == 2:
                    # Two-hop: A → B → A
                    issue_type = "bidirectional" if intentional else "circular"
                else:
                    issue_type = "cycle"

                issues.append(OrchestrationIssue(
                    type=issue_type,
                    agents=list(set(path)),
                    path=cycle_path,
                    intentional=intentional,
                ))

            elif neighbor not in in_path and neighbor in graph:
                in_path.add(neighbor)
                dfs(start, neighbor, path + [neighbor], in_path)
                in_path.discard(neighbor)

    for agent_id in graph:
        dfs(
            start=agent_id,
            current=agent_id,
            path=[agent_id],
            in_path={agent_id},
        )

    return issues