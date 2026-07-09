from backend.adapters.fake.fake_graph_store import FakeGraphStore
from backend.domain.enums import GraphEdgeKind
from backend.domain.errors import Ok
from backend.domain.models import FileContent
from backend.services.call_site_scanner import scan_call_sites, scan_imports
from backend.services.graph_builder import GraphBuilder


def _f(path: str, text: str) -> FileContent:
    return FileContent(path=path, text=text)


# server -> routes/products -> services/inventory -> axios (aliased);
# server -> express; util is a true orphan (imports nothing, imported by nobody).
_FILES = (
    _f("src/server.js", "const express = require('express');\nconst p = require('./routes/products');\n"),
    _f("src/routes/products.js", "const inv = require('../services/inventory');\n"),
    _f("src/services/inventory.js", "const http = require('axios');\nasync function q(){ return http.get('/x'); }\n"),
    _f("src/util.js", "module.exports = 1;\n"),
)


def _build() -> tuple[object, FakeGraphStore]:
    store = FakeGraphStore()
    call_sites = scan_call_sites(_FILES, "axios")
    assert isinstance(call_sites, Ok)
    return GraphBuilder(store).build(_FILES, call_sites.value, "axios"), store


def test_scan_imports_extracts_all_specifiers() -> None:
    pairs = {(ref.from_path, ref.specifier) for ref in scan_imports(_FILES)}
    assert ("src/server.js", "express") in pairs
    assert ("src/server.js", "./routes/products") in pairs
    assert ("src/routes/products.js", "../services/inventory") in pairs
    assert ("src/services/inventory.js", "axios") in pairs


def test_build_is_a_module_graph_without_orphans_or_false_edges() -> None:
    result, _ = _build()
    assert isinstance(result, Ok)
    layout = result.value[2]
    node_ids = {node.id for node in layout.nodes}
    # Packages: only the ones actually imported (axios + express), no orphans.
    assert "package:axios" in node_ids
    assert "package:express" in node_ids
    # util.js imports nothing and is imported by nobody -> dropped.
    assert "file:src/util.js" not in node_ids
    # No false "everything depends on axios" fan-in.
    assert all(edge.kind != GraphEdgeKind.DEPENDS_ON for edge in layout.edges)
    imports = {
        (edge.src, edge.dst)
        for edge in layout.edges
        if edge.kind == GraphEdgeKind.IMPORTS
    }
    assert ("file:src/server.js", "file:src/routes/products.js") in imports  # file->file
    assert ("file:src/routes/products.js", "file:src/services/inventory.js") in imports
    assert ("file:src/server.js", "package:express") in imports  # file->package
    assert ("file:src/services/inventory.js", "package:axios") in imports


def test_blast_radius_is_the_transitive_importer_set() -> None:
    _, store = _build()
    blast = store.blast_radius("axios")
    assert isinstance(blast, Ok)
    assert blast.value == frozenset(
        {
            "file:src/services/inventory.js",
            "file:src/routes/products.js",
            "file:src/server.js",
        }
    )


def test_node_builtins_and_their_orphan_scripts_are_excluded() -> None:
    files = (
        _f("build.js", "const { exec } = require('child_process');\n"),
        _f("src/app.js", "const axios = require('axios');\nconst fs = require('node:fs');\naxios.get('/');\n"),
    )
    store = FakeGraphStore()
    call_sites = scan_call_sites(files, "axios")
    assert isinstance(call_sites, Ok)
    result = GraphBuilder(store).build(files, call_sites.value, "axios")
    assert isinstance(result, Ok)
    ids = {node.id for node in result.value[2].nodes}
    assert "package:child_process" not in ids  # Node core module, not a dependency
    assert "package:fs" not in ids  # node:-prefixed builtin
    assert "file:build.js" not in ids  # orphan once child_process is excluded
    assert "package:axios" in ids
    assert "file:src/app.js" in ids


def test_layout_marks_impacted_nodes() -> None:
    result, _ = _build()
    assert isinstance(result, Ok)
    impacted = {node.id for node in result.value[2].nodes if node.impacted}
    assert "package:axios" in impacted
    assert "file:src/services/inventory.js" in impacted
    assert "file:src/server.js" in impacted  # transitive importer
    assert "package:express" not in impacted  # not in axios's blast radius
