from datetime import datetime, timedelta, timezone

import pytest

from explanation.context import ContextLimits, EmptyContext, SymbolNotFound, build_context
from storage.memory import AnalysisSession


def node(symbol_id, name, file_path="main.py", line=1, parent_id=None, node_type="symbol"):
    return {
        "id": symbol_id,
        "name": name,
        "symbol_type": "function" if node_type == "symbol" else "file",
        "language": "python" if node_type == "symbol" else None,
        "file_path": file_path,
        "start_line": line,
        "end_line": line + 1,
        "start_column": 0,
        "end_column": 1,
        "parent_id": parent_id,
        "node_type": node_type,
    }


def edge(edge_id, source, target, relationship_type, source_file="main.py", target_file="main.py"):
    return {
        "id": edge_id,
        "source": source,
        "target": target,
        "relationship_type": relationship_type,
        "source_file": source_file,
        "target_file": target_file,
        "detail": target,
    }


def session(nodes, edges, sources):
    return AnalysisSession(
        graph={"nodes": nodes, "edges": edges},
        sources=sources,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )


def test_context_includes_source_parent_callers_callees_and_relationships():
    nodes = [node("selected", "selected", parent_id="parent"), node("parent", "Container"), node("caller", "caller"), node("callee", "callee")]
    edges = [
        edge("call-in", "caller", "selected", "calls"),
        edge("call-out", "selected", "callee", "calls"),
        edge("inherit", "selected", "parent", "inherits"),
    ]
    result = build_context(session(nodes, edges, {"main.py": "def selected():\n    return callee()\n"}), "selected")

    assert result.symbol["name"] == "selected"
    assert "def selected" in result.source
    assert result.parent["name"] == "Container"
    assert {item["relationship_type"] for item in result.relationships} == {"calls", "inherits", "contains"}
    assert {item["source"] for item in result.relationships if item["relationship_type"] == "calls"} == {"caller", "selected"}
    assert result.relationships_used == 4
    assert {item["symbol"]["name"] for item in result.related_sources} == {"caller", "callee", "Container"}


def test_context_includes_file_level_imports_for_selected_file():
    nodes = [node("selected", "selected"), node("other", "other", "other.py")]
    edges = [edge("import", "file-main", "file-other", "imports", "main.py", "other.py")]
    result = build_context(session(nodes, edges, {"main.py": "def selected():\n    pass\n", "other.py": "def other():\n    pass\n"}), "selected")

    assert result.relationships[0]["relationship_type"] == "imports"


def test_context_limits_and_source_truncation_are_explicit():
    nodes = [node("selected", "selected")]
    edges = []
    sources = {"main.py": "x" * 400}
    for index in range(4):
        related = node("callee-" + str(index), "callee" + str(index))
        nodes.append(related)
        edges.append(edge("call-" + str(index), "selected", related["id"], "calls"))
        sources["main.py"] += "\n" + ("y" * 20)

    result = build_context(
        session(nodes, edges, sources),
        limits=ContextLimits(max_callers=1, max_callees=2, max_related=1, max_source_chars=30, max_total_chars=500),
        symbol_id="selected",
    )

    assert len(result.relationships) == 2
    assert result.partial
    assert "callees" in result.truncated
    assert "related_source" in result.truncated or "total_context" in result.truncated
    assert len(result.source) <= 100


def test_invalid_symbol_and_missing_source_are_rejected():
    current = session([node("selected", "selected")], [], {"main.py": "def selected():\n    pass\n"})
    with pytest.raises(SymbolNotFound):
        build_context(current, "missing")

    missing_source = session([node("selected", "selected")], [], {})
    with pytest.raises(SymbolNotFound):
        build_context(missing_source, "selected")


def test_file_node_and_empty_relationship_context_do_not_fake_symbols():
    file_session = session([node("file", "main.py", node_type="file")], [], {"main.py": "text"})
    with pytest.raises(SymbolNotFound):
        build_context(file_session, "file")

    unresolved = session([node("selected", "selected")], [edge("import", "file-main", None, "imports", "main.py", None)], {"main.py": "def selected():\n    pass\n"})
    result = build_context(unresolved, "selected")
    assert result.relationships[0]["target"] is None
    assert result.related_sources == []
    assert not result.partial
