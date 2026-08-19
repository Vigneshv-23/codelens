from pathlib import Path, PurePosixPath

from .extract import extract_symbols
from .graph import build_graph
from .models import LanguageName, Symbol
from .parser import parse
from .relationships import extract_relationships

SUPPORTED_EXTENSIONS: dict[str, LanguageName] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
}


def analyze_repository(root: Path) -> dict[str, list[dict]]:
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    repository_files = [relative_path(root, path) for path in files]
    parsed: list[tuple[str, LanguageName, object]] = []
    symbols: list[Symbol] = []

    for path, file_path in zip(files, repository_files):
        language = SUPPORTED_EXTENSIONS[path.suffix.lower()]
        try:
            source = path.read_text(encoding="utf-8")
            tree = parse(source, language)
            file_symbols = extract_symbols(tree, language, file_path)
        except (OSError, UnicodeError, ValueError):
            continue
        parsed.append((file_path, language, tree))
        symbols.extend(file_symbols)

    relationships = []
    for file_path, language, tree in parsed:
        try:
            relationships.extend(
                extract_relationships(
                    tree,
                    language,
                    file_path,
                    [symbol for symbol in symbols if symbol.file_path == file_path],
                    repository_files,
                    symbols,
                )
            )
        except (OSError, UnicodeError, ValueError):
            continue

    return build_graph(symbols, relationships).to_dict()


def relative_path(root: Path, path: Path) -> str:
    return PurePosixPath(path.relative_to(root).as_posix()).as_posix()
