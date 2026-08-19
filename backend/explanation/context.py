"""Build bounded, graph-grounded context for symbol explanations."""

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

from storage.memory import AnalysisSession, _safe_path


@dataclass(frozen=True)
class ContextLimits:
    max_callers: int = 10
    max_callees: int = 10
    max_related: int = 10
    max_source_chars: int = 4_000
    max_total_chars: int = 24_000


DEFAULT_LIMITS = ContextLimits()


class ContextError(Exception):
    """Base class for context-building failures."""


class SymbolNotFound(ContextError):
    pass


class EmptyContext(ContextError):
    pass


@dataclass
class ExplanationContext:
    symbol: Dict[str, Any]
    source: str
    parent: Optional[Dict[str, Any]]
    relationships: List[Dict[str, Any]]
    related_sources: List[Dict[str, Any]]
    partial: bool = False
    truncated: List[str] = field(default_factory=list)
    max_total_chars: Optional[int] = None

    @property
    def relationships_used(self) -> int:
        return len(self.relationships)


def _node_sort_key(node: Dict[str, Any]) -> Tuple[str, str, str]:
    return (str(node.get("file_path") or ""), str(node.get("name") or ""), str(node.get("id") or ""))


def _edge_sort_key(edge: Dict[str, Any]) -> Tuple[str, str, str, str]:
    return (
        str(edge.get("relationship_type") or ""),
        str(edge.get("source_file") or ""),
        str(edge.get("target_file") or ""),
        str(edge.get("id") or ""),
    )


def _symbol_metadata(node: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": node.get("id"),
        "name": node.get("name"),
        "type": node.get("symbol_type"),
        "language": node.get("language"),
        "file": node.get("file_path"),
        "start_line": node.get("start_line"),
        "end_line": node.get("end_line"),
        "start_column": node.get("start_column"),
        "end_column": node.get("end_column"),
    }


def _bounded_source(source: str, limit: int) -> Tuple[str, bool]:
    if len(source) <= limit:
        return source, False
    if limit < 80:
        return source[:limit], True
    head = limit // 2
    tail = limit - head
    return source[:head] + "\n... [source truncated] ...\n" + source[-tail:], True


def _safe_source(session: AnalysisSession, node: Dict[str, Any], limit: int) -> Tuple[Optional[str], bool]:
    file_path = node.get("file_path")
    if not isinstance(file_path, str):
        return None, False
    try:
        normalized = _safe_path(file_path)
    except ValueError:
        return None, False
    source = session.sources.get(normalized)
    if source is None:
        return None, False
    return _bounded_source(source, limit)


def _relationship_payload(edge: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": edge.get("id"),
        "relationship_type": edge.get("relationship_type"),
        "source": edge.get("source"),
        "target": edge.get("target"),
        "source_file": edge.get("source_file"),
        "target_file": edge.get("target_file"),
        "detail": edge.get("detail"),
    }


def _append_unique(items: List[Dict[str, Any]], value: Dict[str, Any]) -> None:
    if value not in items:
        items.append(value)


def build_context(
    session: AnalysisSession,
    symbol_id: str,
    limits: ContextLimits = DEFAULT_LIMITS,
) -> ExplanationContext:
    nodes = session.graph.get("nodes", [])
    edges = session.graph.get("edges", [])
    nodes_by_id = {node.get("id"): node for node in nodes if node.get("id")}
    symbol = nodes_by_id.get(symbol_id)
    if symbol is None or symbol.get("node_type") != "symbol":
        raise SymbolNotFound("Symbol not found in analysis")

    selected_source, selected_truncated = _safe_source(session, symbol, limits.max_source_chars)
    if selected_source is None:
        raise SymbolNotFound("Symbol source not found")

    file_path = symbol.get("file_path")
    outgoing = [edge for edge in edges if edge.get("source") == symbol_id]
    incoming = [edge for edge in edges if edge.get("target") == symbol_id]
    outgoing.extend(
        edge for edge in edges
        if edge.get("relationship_type") == "imports"
        and edge.get("source_file") == file_path
        and edge not in outgoing
    )
    incoming.extend(
        edge for edge in edges
        if edge.get("relationship_type") == "imports"
        and edge.get("target_file") == file_path
        and edge not in incoming
    )
    callers = sorted(
        [edge for edge in incoming if edge.get("relationship_type") == "calls"],
        key=_edge_sort_key,
    )
    callees = sorted(
        [edge for edge in outgoing if edge.get("relationship_type") == "calls"],
        key=_edge_sort_key,
    )
    dependencies = sorted(
        [edge for edge in outgoing if edge.get("relationship_type") != "calls"],
        key=_edge_sort_key,
    )
    dependents = sorted(
        [edge for edge in incoming if edge.get("relationship_type") != "calls"],
        key=_edge_sort_key,
    )

    truncated: List[str] = []
    selected_groups = [
        ("callers", callers, limits.max_callers),
        ("callees", callees, limits.max_callees),
        ("related", dependencies + dependents, limits.max_related),
    ]
    selected_edges: List[Dict[str, Any]] = []
    for label, candidates, maximum in selected_groups:
        if len(candidates) > maximum:
            truncated.append(label)
        for edge in candidates[:maximum]:
            _append_unique(selected_edges, edge)

    parent = nodes_by_id.get(symbol.get("parent_id")) if symbol.get("parent_id") else None
    if parent is not None:
        parent_source, parent_truncated = _safe_source(session, parent, limits.max_source_chars)
        if parent_truncated:
            truncated.append("parent_source")
    else:
        parent_source = None

    related_nodes: List[Dict[str, Any]] = []
    for edge in selected_edges:
        for node_id in (edge.get("source"), edge.get("target")):
            node = nodes_by_id.get(node_id)
            if node and node.get("node_type") == "symbol" and node.get("id") != symbol_id:
                if node not in related_nodes:
                    related_nodes.append(node)
    if parent is not None and parent not in related_nodes:
        related_nodes.append(parent)
    related_nodes.sort(key=_node_sort_key)

    related_sources: List[Dict[str, Any]] = []
    for node in related_nodes:
        source, was_truncated = _safe_source(session, node, limits.max_source_chars)
        if source is None:
            continue
        if was_truncated:
            truncated.append("related_source")
        related_sources.append({"symbol": _symbol_metadata(node), "source": source})

    relationships = [_relationship_payload(edge) for edge in selected_edges]
    if parent is not None:
        relationships.append({
            "id": None,
            "relationship_type": "contains",
            "source": parent.get("id"),
            "target": symbol_id,
            "source_file": parent.get("file_path"),
            "target_file": symbol.get("file_path"),
            "detail": "parent symbol",
        })

    result = ExplanationContext(
        symbol=_symbol_metadata(symbol),
        source=selected_source,
        parent=_symbol_metadata(parent) if parent is not None else None,
        relationships=relationships,
        related_sources=related_sources,
        partial=bool(truncated),
        truncated=list(dict.fromkeys(truncated)),
        max_total_chars=limits.max_total_chars,
    )

    rendered_size = len(_render_context(result))
    if rendered_size > limits.max_total_chars:
        result.partial = True
        if "total_context" not in result.truncated:
            result.truncated.append("total_context")
        result.related_sources = []
        rendered_size = len(_render_context(result))
        if rendered_size > limits.max_total_chars:
            result.source, _ = _bounded_source(result.source, max(200, limits.max_total_chars // 3))
    if not result.source and not result.relationships and not result.related_sources:
        raise EmptyContext("No usable context is available for this symbol")
    return result


def _render_context(context: ExplanationContext) -> str:
    parts = ["SELECTED SYMBOL\n" + repr(context.symbol), "SOURCE\n" + context.source]
    if context.parent:
        parts.append("PARENT\n" + repr(context.parent))
    parts.append("RELATIONSHIPS\n" + repr(context.relationships))
    if context.related_sources:
        parts.append("RELATED SYMBOL SOURCES\n" + repr(context.related_sources))
    if context.truncated:
        parts.append("LIMITATIONS\nPartial context: " + ", ".join(context.truncated))
    return "\n\n".join(parts)


def render_context(context: ExplanationContext) -> str:
    rendered = _render_context(context)
    if context.max_total_chars is None or len(rendered) <= context.max_total_chars:
        return rendered
    marker = "\n\nLIMITATIONS\nPartial context: total_context"
    budget = max(0, context.max_total_chars - len(marker))
    return rendered[:budget] + marker
