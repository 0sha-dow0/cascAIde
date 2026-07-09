from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from typing import Final

from backend.domain.enums import GraphEdgeKind, GraphNodeKind
from backend.domain.errors import Err, GraphError, Ok, Result
from backend.domain.models import (
    CallSite,
    CentralityScore,
    GraphEdge,
    GraphLayout,
    GraphLayoutNode,
    GraphNode,
)
from backend.ports.graph_store import GraphStore, node_attrs_to_call_site

_LEVEL_X_SPACING: Final = 240.0
_INTRA_LEVEL_Y_SPACING: Final = 120.0


def _edge_sort_key(edge: GraphEdge) -> tuple[str, str, str]:
    return (edge.src, edge.dst, edge.kind.value)


def _call_site_sort_key(
    call_site: CallSite,
) -> tuple[str, int, str, bool, bool, str, str]:
    return (
        call_site.file_path,
        call_site.line,
        call_site.symbol,
        call_site.is_aliased,
        call_site.alias is None,
        call_site.alias or "",
        call_site.snippet,
    )


class FakeGraphStore(GraphStore):
    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: tuple[GraphEdge, ...] = ()

    def reset(self) -> Result[None, GraphError]:
        self._nodes = {}
        self._edges = ()
        return Ok(None)

    def load(
        self, nodes: Sequence[GraphNode], edges: Sequence[GraphEdge]
    ) -> Result[None, GraphError]:
        new_nodes: dict[str, GraphNode] = {}
        for node in nodes:
            if node.id in new_nodes:
                return Err(
                    GraphError(
                        "duplicate node id in graph load",
                        {"node_id": node.id},
                    )
                )
            new_nodes[node.id] = node
        for edge in edges:
            if edge.src not in new_nodes:
                return Err(
                    GraphError(
                        "edge references unknown source node",
                        {"src": edge.src, "dst": edge.dst},
                    )
                )
            if edge.dst not in new_nodes:
                return Err(
                    GraphError(
                        "edge references unknown destination node",
                        {"src": edge.src, "dst": edge.dst},
                    )
                )
        self._nodes = new_nodes
        self._edges = tuple(sorted(edges, key=_edge_sort_key))
        return Ok(None)

    def centrality(self) -> Result[tuple[CentralityScore, ...], GraphError]:
        package_nodes = [
            node
            for node in self._nodes.values()
            if node.kind == GraphNodeKind.PACKAGE
        ]
        if not package_nodes:
            return Ok(())
        degree = self._degree_by_node()
        denominator = len(self._nodes) - 1
        scored = [
            (
                node,
                degree[node.id] / denominator if denominator > 0 else 0.0,
            )
            for node in package_nodes
        ]
        scored.sort(key=lambda item: (-item[1], item[0].label, item[0].id))
        return Ok(
            tuple(
                CentralityScore(package=node.label, score=score)
                for node, score in scored
            )
        )

    def _root_id(self, target_package: str) -> Result[str | None, GraphError]:
        roots = [
            node
            for node in self._nodes.values()
            if node.kind == GraphNodeKind.PACKAGE and node.label == target_package
        ]
        if not roots:
            return Ok(None)
        if len(roots) > 1:
            return Err(
                GraphError(
                    "target package label matches multiple package nodes",
                    {"target_package": target_package, "matches": str(len(roots))},
                )
            )
        return Ok(roots[0].id)

    def traverse_call_sites(
        self, target_package: str
    ) -> Result[tuple[CallSite, ...], GraphError]:
        root = self._root_id(target_package)
        if isinstance(root, Err):
            return root
        if root.value is None:
            return Ok(())
        importer_ids = {
            edge.src
            for edge in self._edges
            if edge.kind == GraphEdgeKind.IMPORTS
            and edge.dst == root.value
            and self._nodes[edge.src].kind == GraphNodeKind.FILE
        }
        collected: list[CallSite] = []
        for edge in self._edges:
            if edge.kind != GraphEdgeKind.CALLS or edge.src not in importer_ids:
                continue
            node = self._nodes[edge.dst]
            if node.kind != GraphNodeKind.CALL_SITE:
                continue
            decoded = node_attrs_to_call_site(node.attrs)
            if isinstance(decoded, Err):
                return decoded
            collected.append(decoded.value)
        return Ok(tuple(sorted(set(collected), key=_call_site_sort_key)))

    def blast_radius(
        self, target_package: str
    ) -> Result[frozenset[str], GraphError]:
        root = self._root_id(target_package)
        if isinstance(root, Err):
            return root
        if root.value is None:
            return Ok(frozenset())
        reverse: dict[str, list[str]] = {node_id: [] for node_id in self._nodes}
        for edge in self._edges:
            if edge.kind == GraphEdgeKind.IMPORTS:
                reverse[edge.dst].append(edge.src)
        visited: set[str] = {root.value}
        queue: deque[str] = deque([root.value])
        impacted: set[str] = set()
        while queue:
            current_id = queue.popleft()
            for src_id in reverse[current_id]:
                if src_id not in visited:
                    visited.add(src_id)
                    queue.append(src_id)
                    if self._nodes[src_id].kind == GraphNodeKind.FILE:
                        impacted.add(src_id)
        return Ok(frozenset(impacted))

    def layout(self) -> Result[GraphLayout, GraphError]:
        if not self._nodes:
            return Ok(GraphLayout(nodes=(), edges=()))
        levels = self._bfs_levels()
        by_level: dict[int, list[str]] = {}
        for node_id, level in levels.items():
            by_level.setdefault(level, []).append(node_id)
        layout_nodes: list[GraphLayoutNode] = []
        for level in sorted(by_level):
            for index, node_id in enumerate(sorted(by_level[level])):
                node = self._nodes[node_id]
                layout_nodes.append(
                    GraphLayoutNode(
                        id=node_id,
                        x=level * _LEVEL_X_SPACING,
                        y=index * _INTRA_LEVEL_Y_SPACING,
                        kind=node.kind,
                        label=node.label,
                    )
                )
        return Ok(GraphLayout(nodes=tuple(layout_nodes), edges=self._edges))

    def _degree_by_node(self) -> dict[str, int]:
        degree = {node_id: 0 for node_id in self._nodes}
        for edge in self._edges:
            degree[edge.src] += 1
            degree[edge.dst] += 1
        return degree

    def _bfs_levels(self) -> dict[str, int]:
        sorted_ids = sorted(self._nodes)
        out_adjacency: dict[str, list[str]] = {node_id: [] for node_id in self._nodes}
        in_degree = {node_id: 0 for node_id in self._nodes}
        for edge in self._edges:
            out_adjacency[edge.src].append(edge.dst)
            in_degree[edge.dst] += 1
        for neighbors in out_adjacency.values():
            neighbors.sort()
        levels: dict[str, int] = {}
        queue: deque[str] = deque()
        for node_id in sorted_ids:
            if in_degree[node_id] == 0:
                levels[node_id] = 0
                queue.append(node_id)
        self._drain_levels(queue, out_adjacency, levels)
        for node_id in sorted_ids:
            if node_id not in levels:
                levels[node_id] = 0
                queue.append(node_id)
                self._drain_levels(queue, out_adjacency, levels)
        return levels

    @staticmethod
    def _drain_levels(
        queue: deque[str],
        out_adjacency: dict[str, list[str]],
        levels: dict[str, int],
    ) -> None:
        while queue:
            current_id = queue.popleft()
            for neighbor_id in out_adjacency[current_id]:
                if neighbor_id not in levels:
                    levels[neighbor_id] = levels[current_id] + 1
                    queue.append(neighbor_id)


__all__ = ("FakeGraphStore",)
