from analyzer.graph import build_graph
from analyzer.models import Relationship, Symbol
from analyzer.relationships import file_id


def symbol(name, kind, language, file_path, symbol_id, parent_id=None):
    return Symbol(
        name,
        kind,
        language,
        file_path,
        2,
        4,
        symbol_id,
        parent_id,
        3,
        8,
        True,
    )


def relationship(source_id, target_id, kind, source_file, target_file=None, detail=None):
    return Relationship(
        source_id,
        target_id,
        kind,
        "javascript",
        source_file,
        target_file,
        detail,
    )


def test_basic_nodes_and_edges():
    nodes = [symbol("App", "class", "javascript", "app.js", "app-id")]
    graph = build_graph(nodes, [relationship("app-id", "base-id", "inherits", "app.js", "base.js", "Base")])
    assert {node.id for node in graph.nodes} == {"app-id"}
    assert graph.edges[0].source == "app-id"
    assert graph.edges[0].target == "base-id"


def test_multiple_files_and_file_import_nodes():
    graph = build_graph(
        [symbol("App", "class", "javascript", "app.js", "app-id")],
        [relationship("file-app", "file-lib", "imports", "app.js", "lib.js", "./lib")],
    )
    assert {node.id for node in graph.nodes} == {"app-id", file_id("app.js"), file_id("lib.js")}
    assert graph.edges[0].source == file_id("app.js")
    assert graph.edges[0].target == file_id("lib.js")


def test_multiple_symbols_are_preserved():
    graph = build_graph(
        [symbol("one", "function", "python", "mod.py", "one"), symbol("Two", "class", "python", "mod.py", "two")],
        [],
    )
    assert [node.id for node in graph.nodes] == ["one", "two"]
    assert {node.name for node in graph.nodes} == {"one", "Two"}


def test_nested_symbol_metadata_is_preserved():
    graph = build_graph(
        [symbol("Outer", "class", "javascript", "a.js", "outer"), symbol("method", "method", "javascript", "a.js", "method", "outer")],
        [],
    )
    method = next(node for node in graph.nodes if node.id == "method")
    assert method.parent_id == "outer"
    assert method.start_line == 2
    assert method.exported is True


def test_circular_dependencies_are_retained():
    graph = build_graph(
        [],
        [
            relationship("a", "b", "imports", "a.js", "b.js", "./b"),
            relationship("b", "a", "imports", "b.js", "a.js", "./a"),
        ],
    )
    assert {(edge.source, edge.target) for edge in graph.edges} == {
        (file_id("a.js"), file_id("b.js")),
        (file_id("b.js"), file_id("a.js")),
    }


def test_disconnected_components_are_preserved():
    graph = build_graph(
        [symbol("a", "class", "java", "a.java", "a"), symbol("b", "class", "java", "b.java", "b")],
        [],
    )
    assert len(graph.nodes) == 2
    assert graph.edges == ()


def test_duplicate_relationships_are_deduplicated():
    edge = relationship("a", "b", "inherits", "a.js", "b.js", "B")
    graph = build_graph([], [edge, edge])
    assert len(graph.edges) == 1


def test_unresolved_relationship_has_no_fake_target_node():
    graph = build_graph([], [relationship(file_id("a.py"), None, "imports", "a.py", None, "missing")])
    assert len(graph.nodes) == 1
    assert graph.nodes[0].id == file_id("a.py")
    assert graph.edges[0].target is None
    assert graph.edges[0].detail == "missing"


def test_symbol_metadata_is_preserved_in_graph_node():
    original = symbol("Thing", "interface", "typescript", "thing.ts", "thing-id")
    node = build_graph([original], []).nodes[0]
    assert node.id == original.symbol_id
    assert node.label == original.name
    assert node.symbol_type == original.kind
    assert node.language == original.language
    assert node.file_path == original.file_path
    assert node.start_column == original.start_column
    assert node.end_column == original.end_column


def test_relationship_type_and_metadata_are_preserved():
    graph = build_graph([], [relationship("a", "b", "implements", "a.ts", "b.ts", "Interface")])
    edge = graph.edges[0]
    assert edge.relationship_type == "implements"
    assert edge.source_file == "a.ts"
    assert edge.target_file == "b.ts"
    assert edge.detail == "Interface"


def test_graph_serialization_is_frontend_friendly_and_deterministic():
    graph = build_graph(
        [symbol("B", "class", "python", "b.py", "b"), symbol("A", "class", "python", "a.py", "a")],
        [relationship("a", "b", "inherits", "a.py", "b.py", "B")],
    )
    payload = graph.to_dict()
    assert list(payload) == ["nodes", "edges"]
    assert payload == graph.to_dict()
    assert payload["nodes"][0]["id"] == "a"
