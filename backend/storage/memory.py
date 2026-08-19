"""Bounded in-memory storage for analysis source sessions."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath
from secrets import token_urlsafe
from threading import Lock
from typing import Any, Dict, Optional

ANALYSIS_TTL = timedelta(hours=1)
MAX_SOURCE_FILES = 2_000
MAX_SOURCE_BYTES = 25 * 1024 * 1024
MAX_FILE_BYTES = 1 * 1024 * 1024
MAX_FILE_LINES = 1_200
SOURCE_CONTEXT_LINES = 80
SUPPORTED_LANGUAGES = {"python", "javascript", "typescript", "java"}


@dataclass
class AnalysisSession:
    graph: dict[str, list[dict[str, Any]]]
    sources: dict[str, str]
    expires_at: datetime


_sessions: dict[str, AnalysisSession] = {}
_lock = Lock()


def _purge_expired(now: Optional[datetime] = None) -> None:
    current = now or datetime.now(timezone.utc)
    for analysis_id, session in list(_sessions.items()):
        if session.expires_at <= current:
            del _sessions[analysis_id]


def _safe_path(file_path: str) -> str:
    path = PurePosixPath(file_path)
    if not file_path or path.is_absolute() or ".." in path.parts or path == PurePosixPath("."):
        raise ValueError("Invalid source path")
    return path.as_posix()


def create_session(graph: dict[str, list[dict[str, Any]]], sources: dict[str, str]) -> str:
    if len(sources) > MAX_SOURCE_FILES:
        raise ValueError("Repository contains too many source files")

    normalized_sources: dict[str, str] = {}
    total_bytes = 0
    for file_path, source in sources.items():
        normalized_path = _safe_path(file_path)
        source_bytes = len(source.encode("utf-8"))
        if source_bytes > MAX_FILE_BYTES or total_bytes + source_bytes > MAX_SOURCE_BYTES:
            raise ValueError("Repository source exceeds the session limit")
        normalized_sources[normalized_path] = source
        total_bytes += source_bytes

    with _lock:
        _purge_expired()
        analysis_id = token_urlsafe(24)
        _sessions[analysis_id] = AnalysisSession(
            graph=graph,
            sources=normalized_sources,
            expires_at=datetime.now(timezone.utc) + ANALYSIS_TTL,
        )
    return analysis_id


def get_session(analysis_id: str) -> Optional[AnalysisSession]:
    with _lock:
        _purge_expired()
        return _sessions.get(analysis_id)


def clear_sessions() -> None:
    with _lock:
        _sessions.clear()


def source_for_symbol(analysis_id: str, symbol_id: str) -> Optional[Dict[str, Any]]:
    session = get_session(analysis_id)
    if session is None:
        return None

    symbol = next(
        (node for node in session.graph.get("nodes", []) if node.get("id") == symbol_id),
        None,
    )
    if symbol is None or symbol.get("node_type") != "symbol":
        return None

    file_path = symbol.get("file_path")
    language = symbol.get("language")
    start_line = symbol.get("start_line")
    end_line = symbol.get("end_line")
    if not isinstance(file_path, str) or not isinstance(language, str) or language not in SUPPORTED_LANGUAGES:
        return None
    if not isinstance(start_line, int) or not isinstance(end_line, int):
        return None

    try:
        normalized_path = _safe_path(file_path)
    except ValueError:
        return None
    source = session.sources.get(normalized_path)
    if source is None:
        return None

    lines = source.splitlines()
    if len(lines) <= MAX_FILE_LINES:
        source_start_line = 1
        selected_source = source
    else:
        source_start_line = max(1, start_line - SOURCE_CONTEXT_LINES)
        source_end_line = min(len(lines), end_line + SOURCE_CONTEXT_LINES)
        selected_source = "\n".join(lines[source_start_line - 1:source_end_line])
        if source.endswith("\n") and source_end_line == len(lines):
            selected_source += "\n"

    return {
        "symbol": {
            "id": symbol["id"],
            "name": symbol.get("name"),
            "type": symbol.get("symbol_type"),
            "language": language,
            "file": normalized_path,
            "start_line": start_line,
            "end_line": end_line,
            "start_column": symbol.get("start_column"),
            "end_column": symbol.get("end_column"),
        },
        "source": selected_source,
        "start_line": source_start_line,
    }
