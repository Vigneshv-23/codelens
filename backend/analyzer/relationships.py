from pathlib import Path, PurePosixPath
import hashlib
from typing import Iterable, Optional

from tree_sitter import Node, Tree

from .models import LanguageName, Relationship, Symbol


def file_id(file_path: str) -> str:
    return hashlib.sha1(f"file:{file_path}".encode("utf-8")).hexdigest()[:16]


def extract_relationships(
    tree: Tree,
    language: LanguageName,
    file_path: str,
    symbols: Iterable[Symbol],
    repository_files: Iterable[str] = (),
    repository_symbols: Iterable[Symbol] = (),
) -> list[Relationship]:
    symbols = list(symbols)
    repository_symbols = list(repository_symbols)
    relationships: list[Relationship] = []
    seen: set[tuple[object, ...]] = set()

    def add(
        relationship_type: str,
        source_id: str,
        target_id: Optional[str],
        target_file: Optional[str] = None,
        detail: Optional[str] = None,
    ) -> None:
        key = (source_id, target_id, relationship_type, file_path, target_file, detail)
        if key in seen:
            return
        seen.add(key)
        relationships.append(
            Relationship(
                source_id=source_id,
                target_id=target_id,
                relationship_type=relationship_type,
                language=language,
                source_file=file_path,
                target_file=target_file,
                detail=detail,
            )
        )

    for symbol in symbols:
        if symbol.parent_id:
            parent = next(
                (candidate for candidate in symbols if candidate.symbol_id == symbol.parent_id),
                None,
            )
            if parent and symbol.kind in {"method", "function"} and parent.kind in {"class", "interface"}:
                add("contains", parent.symbol_id, symbol.symbol_id, file_path)

    for node in _walk(tree.root_node):
        if node.type in {"import_statement", "import_from_statement", "import_declaration"}:
            module = _import_module(node, language)
            if module:
                target = _resolve_module(module, language, file_path, repository_files)
                add(
                    "imports",
                    file_id(file_path),
                    file_id(target) if target else None,
                    target,
                    module,
                )
        elif language == "javascript" and node.type == "call_expression":
            module = _require_module(node)
            if module:
                target = _resolve_module(module, language, file_path, repository_files)
                add(
                    "imports",
                    file_id(file_path),
                    file_id(target) if target else None,
                    target,
                    module,
                )
        elif node.type in {"class_definition", "class_declaration"}:
            source = _symbol_at(symbols, node, {"class"})
            if source:
                for base in _bases(node, language):
                    target = _find_symbol(base, repository_symbols, {"class", "interface"})
                    add(
                        "inherits",
                        source.symbol_id,
                        target.symbol_id if target else None,
                        target.file_path if target else None,
                        base,
                    )
                for interface in _interfaces(node, language):
                    target = _find_symbol(interface, repository_symbols, {"interface"})
                    add(
                        "implements",
                        source.symbol_id,
                        target.symbol_id if target else None,
                        target.file_path if target else None,
                        interface,
                    )

    call_symbols = _unique_symbols([*symbols, *repository_symbols])
    for node in _walk(tree.root_node):
        callee_name = _call_name(node, language)
        if not callee_name or callee_name == "require":
            continue
        caller = _caller_symbol(node, symbols)
        if not caller:
            continue
        target = _resolve_call_target(callee_name, caller, call_symbols)
        if target:
            add(
                "calls",
                caller.symbol_id,
                target.symbol_id,
                target.file_path,
                callee_name,
            )

    return relationships


def _walk(node: Node):
    yield node
    for child in node.children:
        yield from _walk(child)


def _symbol_at(symbols: list[Symbol], node: Node, kinds: set[str]) -> Optional[Symbol]:
    start_line = node.start_point[0] + 1
    start_column = node.start_point[1]
    return next(
        (
            symbol
            for symbol in symbols
            if symbol.kind in kinds
            and symbol.start_line == start_line
            and symbol.start_column == start_column
        ),
        None,
    )


def _find_symbol(name: str, symbols: list[Symbol], kinds: set[str]) -> Optional[Symbol]:
    matches = [symbol for symbol in symbols if symbol.name == name and symbol.kind in kinds]
    return matches[0] if len(matches) == 1 else None


def _unique_symbols(symbols: Iterable[Symbol]) -> list[Symbol]:
    unique: dict[str, Symbol] = {}
    for symbol in symbols:
        unique[symbol.symbol_id] = symbol
    return list(unique.values())


def _call_name(node: Node, language: LanguageName) -> Optional[str]:
    if language == "python" and node.type == "call":
        function = node.child_by_field_name("function")
        if function and function.type == "identifier":
            return _text(function)
        if function and function.type == "attribute":
            return _text(function.child_by_field_name("attribute"))
    if language in {"javascript", "typescript"} and node.type == "call_expression":
        function = node.child_by_field_name("function")
        if function and function.type == "identifier":
            return _text(function)
        if function and function.type == "member_expression":
            return _text(function.child_by_field_name("property"))
    if language == "java" and node.type == "method_invocation":
        return _text(node.child_by_field_name("name")) or None
    return None


def _caller_symbol(node: Node, symbols: list[Symbol]) -> Optional[Symbol]:
    candidates = [symbol for symbol in symbols if symbol.kind in {"function", "method"} and _contains(symbol, node)]
    return min(candidates, key=_symbol_span) if candidates else None


def _contains(symbol: Symbol, node: Node) -> bool:
    start = (symbol.start_line, symbol.start_column)
    end = (symbol.end_line, symbol.end_column)
    return start <= (node.start_point[0] + 1, node.start_point[1]) and (node.end_point[0] + 1, node.end_point[1]) <= end


def _symbol_span(symbol: Symbol) -> tuple[int, int]:
    return (symbol.end_line - symbol.start_line, symbol.end_column - symbol.start_column)


def _resolve_call_target(name: str, caller: Symbol, symbols: list[Symbol]) -> Optional[Symbol]:
    candidates = [symbol for symbol in symbols if symbol.name == name and symbol.kind in {"function", "method"}]
    if caller.parent_id:
        class_methods = [symbol for symbol in candidates if symbol.parent_id == caller.parent_id]
        if len(class_methods) == 1:
            return class_methods[0]
        if class_methods:
            return None
    return candidates[0] if len(candidates) == 1 else None


def _text(node: Optional[Node]) -> str:
    return node.text.decode("utf-8") if node else ""


def _import_module(node: Node, language: LanguageName) -> Optional[str]:
    if language in {"javascript", "typescript"}:
        source = node.child_by_field_name("source")
        return _unquote(_text(source))
    if language == "java":
        scoped = next((child for child in node.children if child.type in {"scoped_identifier", "identifier"}), None)
        return _text(scoped)
    if node.type == "import_statement":
        return next((_text(child) for child in node.children if child.type in {"dotted_name", "identifier"}), None)
    dotted = [child for child in node.children if child.type == "dotted_name"]
    return _text(dotted[0]) if dotted else None


def _require_module(node: Node) -> Optional[str]:
    function = node.child_by_field_name("function")
    if _text(function) != "require":
        return None
    arguments = node.child_by_field_name("arguments")
    if not arguments:
        return None
    string = next((child for child in arguments.children if child.type == "string"), None)
    return _unquote(_text(string))


def _unquote(value: str) -> str:
    return value[1:-1] if len(value) >= 2 and value[0] in {"'", '"', "`"} else value


def _bases(node: Node, language: LanguageName) -> list[str]:
    if language == "python":
        argument_list = next((child for child in node.children if child.type == "argument_list"), None)
        return [_text(child) for child in argument_list.children if child.type in {"identifier", "dotted_name"}] if argument_list else []
    if language == "java":
        superclass = node.child_by_field_name("superclass")
        return _type_names_list(superclass)
    heritage = next((child for child in node.children if child.type == "class_heritage"), None)
    if not heritage:
        return []
    extends = next((child for child in heritage.children if child.type == "extends_clause"), None)
    if extends:
        return _type_names_list(extends)
    children = heritage.children
    for index, child in enumerate(children):
        if child.type == "extends" and index + 1 < len(children):
            return _type_names_list(children[index + 1])
    return []


def _interfaces(node: Node, language: LanguageName) -> list[str]:
    if language == "java":
        interfaces = node.child_by_field_name("interfaces")
        return _type_names_list(interfaces)
    heritage = next((child for child in node.children if child.type == "class_heritage"), None)
    implements = next((child for child in heritage.children if child.type == "implements_clause"), None) if heritage else None
    return _type_names_list(implements)


def _type_names(node: Node) -> str:
    names = _type_names_list(node)
    return names[0] if names else ""


def _type_names_list(node: Optional[Node]) -> list[str]:
    if not node:
        return []
    if node.type in {"identifier", "type_identifier", "scoped_identifier"}:
        return [_text(node)]
    names: list[str] = []
    for child in node.children:
        if child.type in {"identifier", "type_identifier", "scoped_identifier"}:
            names.append(_text(child))
        elif child.type not in {"extends", "implements", ",", "<", ">", "{", "}"}:
            names.extend(_type_names_list(child))
    return names


def _resolve_module(
    module: str,
    language: LanguageName,
    source_file: str,
    repository_files: Iterable[str],
) -> Optional[str]:
    files = list(repository_files)
    if not module:
        return None
    source = Path(source_file)
    candidates: list[Path] = []
    if module.startswith("."):
        relative = (source.parent / module).as_posix()
        candidates.extend(_path_variants(relative, language))
    elif language == "python":
        candidates.extend(_path_variants(module.replace(".", "/"), language))
    elif language == "java":
        candidates.extend(_path_variants(module.replace(".", "/"), language))
    else:
        candidates.extend(_path_variants(module, language))
    normalized = {PurePosixPath(path).as_posix(): path for path in files}
    for candidate in candidates:
        if candidate.as_posix() in normalized:
            return normalized[candidate.as_posix()]
    return None


def _path_variants(path: str, language: LanguageName) -> list[Path]:
    path = path.removeprefix("./")
    suffixes = {
        "python": [".py", "/__init__.py"],
        "javascript": ["", ".js", ".jsx", "/index.js"],
        "typescript": ["", ".ts", ".tsx", "/index.ts"],
        "java": [".java"],
    }[language]
    return [Path(path + suffix) for suffix in suffixes]
