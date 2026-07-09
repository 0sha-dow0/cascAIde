from __future__ import annotations

import posixpath
from collections.abc import Sequence
from typing import Final

from backend.domain.enums import GraphEdgeKind, GraphNodeKind
from backend.domain.errors import Err, GraphError, Ok, Result
from backend.domain.models import (
    CallSite,
    CentralityScore,
    FileContent,
    GraphEdge,
    GraphLayout,
    GraphNode,
    SurgeryPlan,
)
from backend.ports.graph_store import GraphStore, call_site_to_node_attrs
from backend.services.call_site_scanner import ImportRef, scan_imports

__all__ = ("GraphBuilder",)

_PACKAGE_ID_PREFIX: Final = "package"
_FILE_ID_PREFIX: Final = "file"
_CALL_SITE_ID_PREFIX: Final = "call_site"
_ID_SEPARATOR: Final = ":"

_RESOLVE_EXTENSIONS: Final = (".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".json")
_INDEX_STEMS: Final = tuple(f"index{ext}" for ext in _RESOLVE_EXTENSIONS)

# Node.js core modules are part of the runtime, not dependencies — keep them out
# of the dependency graph so build scripts and stdlib imports don't clutter it.
_NODE_BUILTINS: Final[frozenset[str]] = frozenset(
    {
        "assert", "async_hooks", "buffer", "child_process", "cluster", "console",
        "constants", "crypto", "dgram", "diagnostics_channel", "dns", "domain",
        "events", "fs", "http", "http2", "https", "inspector", "module", "net",
        "os", "path", "perf_hooks", "process", "punycode", "querystring",
        "readline", "repl", "stream", "string_decoder", "sys", "timers", "tls",
        "trace_events", "tty", "url", "util", "v8", "vm", "wasi",
        "worker_threads", "zlib",
    }
)


def _package_id(label: str) -> str:
    return f"{_PACKAGE_ID_PREFIX}{_ID_SEPARATOR}{label}"


def _file_id(path: str) -> str:
    return f"{_FILE_ID_PREFIX}{_ID_SEPARATOR}{path}"


def _call_site_id(index: int) -> str:
    return f"{_CALL_SITE_ID_PREFIX}{_ID_SEPARATOR}{index}"


def _call_site_key(call_site: CallSite) -> tuple[str, int, str, bool, bool, str, str]:
    return (
        call_site.file_path,
        call_site.line,
        call_site.symbol,
        call_site.is_aliased,
        call_site.alias is None,
        call_site.alias or "",
        call_site.snippet,
    )


def _edge_key(edge: GraphEdge) -> tuple[str, str, str]:
    return (edge.src, edge.dst, edge.kind.value)


def _is_relative(specifier: str) -> bool:
    return specifier.startswith(".")


def _package_name(specifier: str) -> str:
    if specifier.startswith("@"):
        parts = specifier.split("/")
        return "/".join(parts[:2]) if len(parts) >= 2 else specifier
    return specifier.split("/", 1)[0]


def _is_builtin(specifier: str) -> bool:
    return specifier.startswith("node:") or _package_name(specifier) in _NODE_BUILTINS


def _resolve_relative(
    importer_path: str, specifier: str, file_paths: frozenset[str]
) -> str | None:
    base = posixpath.dirname(importer_path)
    target = posixpath.normpath(posixpath.join(base, specifier))
    candidates = [target, *(target + ext for ext in _RESOLVE_EXTENSIONS)]
    candidates.extend(posixpath.join(target, stem) for stem in _INDEX_STEMS)
    for candidate in candidates:
        if candidate in file_paths:
            return candidate
    return None


def _import_graph(
    imports: Sequence[ImportRef], file_paths: frozenset[str], target_package: str
) -> tuple[tuple[str, ...], list[tuple[str, str]], list[tuple[str, str]]]:
    """(package_labels, file->file edges, file->package edges). Edges are path/name pairs."""
    packages: set[str] = {target_package}
    file_file: set[tuple[str, str]] = set()
    file_package: set[tuple[str, str]] = set()
    for ref in imports:
        if ref.from_path not in file_paths:
            continue
        if _is_relative(ref.specifier):
            resolved = _resolve_relative(ref.from_path, ref.specifier, file_paths)
            if resolved is not None and resolved != ref.from_path:
                file_file.add((ref.from_path, resolved))
        elif not _is_builtin(ref.specifier):
            name = _package_name(ref.specifier)
            packages.add(name)
            file_package.add((ref.from_path, name))
    labels = (target_package, *sorted(packages - {target_package}))
    return labels, sorted(file_file), sorted(file_package)


def _connected_files(
    file_file: Sequence[tuple[str, str]],
    file_package: Sequence[tuple[str, str]],
    call_sites: Sequence[CallSite],
) -> tuple[str, ...]:
    paths: set[str] = set()
    for src, dst in file_file:
        paths.add(src)
        paths.add(dst)
    for src, _ in file_package:
        paths.add(src)
    paths.update(call_site.file_path for call_site in call_sites)
    return tuple(sorted(paths))


def _nodes(
    package_labels: Sequence[str],
    file_paths: Sequence[str],
    call_sites: Sequence[CallSite],
) -> tuple[GraphNode, ...]:
    nodes: list[GraphNode] = [
        GraphNode(id=_package_id(label), kind=GraphNodeKind.PACKAGE, label=label, attrs={})
        for label in package_labels
    ]
    nodes.extend(
        GraphNode(id=_file_id(path), kind=GraphNodeKind.FILE, label=path, attrs={})
        for path in file_paths
    )
    nodes.extend(
        GraphNode(
            id=_call_site_id(index),
            kind=GraphNodeKind.CALL_SITE,
            label=call_site.symbol,
            attrs=call_site_to_node_attrs(call_site),
        )
        for index, call_site in enumerate(call_sites)
    )
    return tuple(nodes)


def _edges(
    file_file: Sequence[tuple[str, str]],
    file_package: Sequence[tuple[str, str]],
    call_sites: Sequence[CallSite],
) -> tuple[GraphEdge, ...]:
    edges: list[GraphEdge] = []
    for src_path, dst_path in file_file:
        edges.append(
            GraphEdge(src=_file_id(src_path), dst=_file_id(dst_path), kind=GraphEdgeKind.IMPORTS)
        )
    for src_path, package in file_package:
        edges.append(
            GraphEdge(src=_file_id(src_path), dst=_package_id(package), kind=GraphEdgeKind.IMPORTS)
        )
    for index, call_site in enumerate(call_sites):
        edges.append(
            GraphEdge(
                src=_file_id(call_site.file_path),
                dst=_call_site_id(index),
                kind=GraphEdgeKind.CALLS,
            )
        )
    return tuple(sorted(edges, key=_edge_key))


def _affected_files(call_sites: Sequence[CallSite]) -> tuple[str, ...]:
    return tuple(sorted({call_site.file_path for call_site in call_sites}))


def _mark_impacted(
    layout: GraphLayout,
    blast: frozenset[str],
    target_package: str,
    call_sites: Sequence[CallSite],
) -> GraphLayout:
    impacted: set[str] = set(blast)
    impacted.add(_package_id(target_package))
    for index, call_site in enumerate(call_sites):
        if _file_id(call_site.file_path) in blast:
            impacted.add(_call_site_id(index))
    nodes = tuple(
        node.model_copy(update={"impacted": node.id in impacted}) for node in layout.nodes
    )
    return GraphLayout(nodes=nodes, edges=layout.edges)


class GraphBuilder:
    def __init__(self, store: GraphStore) -> None:
        self._store = store

    def build(
        self,
        files: Sequence[FileContent],
        call_sites: Sequence[CallSite],
        target_package: str,
    ) -> Result[
        tuple[SurgeryPlan, tuple[CentralityScore, ...], GraphLayout], GraphError
    ]:
        reset_result = self._store.reset()
        if isinstance(reset_result, Err):
            return reset_result

        unique_call_sites = tuple(sorted(set(call_sites), key=_call_site_key))
        file_paths = frozenset(file.path for file in files)
        imports = scan_imports(files)
        package_labels, file_file, file_package = _import_graph(
            imports, file_paths, target_package
        )
        connected = _connected_files(file_file, file_package, unique_call_sites)
        nodes = _nodes(package_labels, connected, unique_call_sites)
        edges = _edges(file_file, file_package, unique_call_sites)

        load_result = self._store.load(nodes, edges)
        if isinstance(load_result, Err):
            return load_result

        traverse_result = self._store.traverse_call_sites(target_package)
        if isinstance(traverse_result, Err):
            return traverse_result

        centrality_result = self._store.centrality()
        if isinstance(centrality_result, Err):
            return centrality_result

        layout_result = self._store.layout()
        if isinstance(layout_result, Err):
            return layout_result

        blast_result = self._store.blast_radius(target_package)
        if isinstance(blast_result, Err):
            return blast_result

        layout = _mark_impacted(
            layout_result.value, blast_result.value, target_package, unique_call_sites
        )
        plan = SurgeryPlan(
            target_package=target_package,
            call_sites=traverse_result.value,
            affected_files=_affected_files(traverse_result.value),
        )
        return Ok((plan, centrality_result.value, layout))
