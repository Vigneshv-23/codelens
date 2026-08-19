import hashlib
from typing import Optional

from tree_sitter import Node, Tree

from .models import LanguageName, Symbol


DECLARATIONS: dict[LanguageName, dict[str, tuple[str, Optional[str]]]] = {
    "python": {
        "class_definition": ("class", "name"),
        "function_definition": ("function", "name"),
        "async_function_definition": ("function", "name"),
        "import_statement": ("import", None),
        "import_from_statement": ("import", None),
    },
    "javascript": {
        "class_declaration": ("class", "name"),
        "function_declaration": ("function", "name"),
        "method_definition": ("method", "name"),
        "import_statement": ("import", None),
        "export_statement": ("export", None),
    },
    "typescript": {
        "class_declaration": ("class", "name"),
        "function_declaration": ("function", "name"),
        "method_definition": ("method", "name"),
        "interface_declaration": ("interface", "name"),
        "import_statement": ("import", None),
        "export_statement": ("export", None),
    },
    "java": {
        "class_declaration": ("class", "name"),
        "method_declaration": ("method", "name"),
        "interface_declaration": ("interface", "name"),
        "import_declaration": ("import", None),
    },
}


def extract_symbols(
    tree: Tree, language: LanguageName, file_path: str
) -> list[Symbol]:
    symbols: list[Symbol] = []
    _walk(tree.root_node, language, file_path, symbols, None, False)
    return symbols


def _walk(
    node: Node,
    language: LanguageName,
    file_path: str,
    symbols: list[Symbol],
    parent_id: Optional[str],
    exported: bool,
) -> None:
    declaration = DECLARATIONS[language].get(node.type)
    name_node = None
    if declaration is None and node.type == "ERROR" and language in {"javascript", "typescript"}:
        class_node = next((child for child in node.children if child.type == "class"), None)
        identifier = next(
            (
                child
                for child in node.children
                if child.type in {"identifier", "type_identifier"}
            ),
            None,
        )
        if class_node is not None and identifier is not None:
            declaration = ("class", None)
            name_node = identifier

    current_parent_id = parent_id

    if declaration:
        kind, name_field = declaration
        if name_node is None:
            name_node = node.child_by_field_name(name_field) if name_field else None
        name = _symbol_name(node, name_node, kind)
        symbol = _make_symbol(
            name, kind, language, file_path, node, parent_id, exported
        )
        symbols.append(symbol)
        current_parent_id = symbol.symbol_id if kind in {"class", "interface"} else parent_id

    child_exported = exported or node.type == "export_statement"
    for child in node.children:
        _walk(
            child,
            language,
            file_path,
            symbols,
            current_parent_id,
            child_exported,
        )


def _symbol_name(node: Node, name_node: Optional[Node], kind: str) -> str:
    if name_node is not None:
        return name_node.text.decode("utf-8")
    if kind == "import":
        return node.text.decode("utf-8").strip().rstrip(";")
    if kind == "export":
        named = next(
            (child for child in node.children if child.type.endswith("declaration")),
            None,
        )
        return named.text.decode("utf-8").split(maxsplit=2)[0] if named else "export"
    return kind


def _make_symbol(
    name: str,
    kind: str,
    language: LanguageName,
    file_path: str,
    node: Node,
    parent_id: Optional[str],
    exported: bool,
) -> Symbol:
    start_line = node.start_point[0] + 1
    end_line = node.end_point[0] + 1
    location = f"{file_path}:{kind}:{name}:{start_line}:{node.start_point[1]}"
    symbol_id = hashlib.sha1(location.encode("utf-8")).hexdigest()[:16]
    return Symbol(
        name=name,
        kind=kind,
        language=language,
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        symbol_id=symbol_id,
        parent_id=parent_id,
        start_column=node.start_point[1],
        end_column=node.end_point[1],
        exported=exported,
    )
