from dataclasses import asdict, dataclass
from typing import Any, Iterable, Optional

from .models import Relationship, Symbol
from .relationships import file_id


@dataclass(frozen=True)
class GraphNode:
    id: str
    name: str
    label: str
    symbol_type: str
    language: Optional[str]
    file_path: str
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    start_column: Optional[int] = None
    end_column: Optional[int] = None
    parent_id: Optional[str] = None
    exported: Optional[bool] = None
    node_type: str = "symbol"


@dataclass(frozen=True)
class GraphEdge:
    id: str
    source: str
    target: Optional[str]
    relationship_type: str
    source_file: str
    target_file: Optional[str] = None
    detail: Optional[str] = None


@dataclass(frozen=True)
class Graph:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]

    def to_dict(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "nodes": [asdict(node) for node in self.nodes],
            "edges": [asdict(edge) for edge in self.edges],
        }


def build_graph(
    symbols: Iterable[Symbol], relationships: Iterable[Relationship]
) -> Graph:
    symbols = list(symbols)
    relationships = list(relationships)
    nodes: dict[str, GraphNode] = {}

    for symbol in symbols:
        nodes.setdefault(
            symbol.symbol_id,
            GraphNode(
                id=symbol.symbol_id,
                name=symbol.name,
                label=symbol.name,
                symbol_type=symbol.kind,
                language=symbol.language,
                file_path=symbol.file_path,
                start_line=symbol.start_line,
                end_line=symbol.end_line,
                start_column=symbol.start_column,
                end_column=symbol.end_column,
                parent_id=symbol.parent_id,
                exported=symbol.exported,
            ),
        )

    edges: dict[tuple[object, ...], GraphEdge] = {}
    for relationship in relationships:
        source = relationship.source_id
        target = relationship.target_id

        if relationship.relationship_type == "imports":
            source = _ensure_file_node(nodes, relationship.source_file)
            if target is not None and relationship.target_file is not None:
                target = _ensure_file_node(nodes, relationship.target_file)

        key = (
            source,
            target,
            relationship.relationship_type,
            relationship.source_file,
            relationship.target_file,
            relationship.detail,
        )
        if key in edges:
            continue
        edge_id = _edge_id(key)
        edges[key] = GraphEdge(
            id=edge_id,
            source=source,
            target=target,
            relationship_type=relationship.relationship_type,
            source_file=relationship.source_file,
            target_file=relationship.target_file,
            detail=relationship.detail,
        )

    return Graph(
        nodes=tuple(sorted(nodes.values(), key=lambda node: (node.node_type, node.id))),
        edges=tuple(sorted(edges.values(), key=lambda edge: edge.id)),
    )


def _ensure_file_node(nodes: dict[str, GraphNode], file_path: str) -> str:
    node_id = file_id(file_path)
    nodes.setdefault(
        node_id,
        GraphNode(
            id=node_id,
            name=file_path,
            label=file_path,
            symbol_type="file",
            language=None,
            file_path=file_path,
            node_type="file",
        ),
    )
    return node_id


def _edge_id(key: tuple[object, ...]) -> str:
    import hashlib

    value = "|".join("" if item is None else str(item) for item in key)
    return hashlib.sha1(f"edge:{value}".encode("utf-8")).hexdigest()[:16]
