"""Orchestrate bounded context construction and AI completion."""

import os
from typing import Any, Callable, Dict, Optional

from explanation.context import ContextLimits, ExplanationContext, build_context
from explanation.prompts import build_prompts
from explanation.provider import complete
from storage.memory import AnalysisSession


ACTIONS = {"explain", "how_it_works", "impact"}


def _limit(name: str, default: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(1, min(value, maximum))


def configured_limits() -> ContextLimits:
    return ContextLimits(
        max_callers=_limit("AI_MAX_CALLERS", 10, 50),
        max_callees=_limit("AI_MAX_CALLEES", 10, 50),
        max_related=_limit("AI_MAX_RELATED", 10, 50),
        max_source_chars=_limit("AI_MAX_SOURCE_CHARS", 4_000, 20_000),
        max_total_chars=_limit("AI_MAX_CONTEXT_CHARS", 24_000, 100_000),
    )


def explain_symbol(
    session: AnalysisSession,
    symbol_id: str,
    action: str,
    provider: Optional[Callable[[str, str], str]] = None,
    limits: Optional[ContextLimits] = None,
) -> Dict[str, Any]:
    if action not in ACTIONS:
        raise ValueError("Unsupported explanation action")
    context = build_context(session, symbol_id, limits or configured_limits())
    system_prompt, user_prompt = build_prompts(action, context)
    answer = (provider or complete)(system_prompt, user_prompt)
    return {
        "answer": answer,
        "context": {
            "symbol": context.symbol,
            "file": context.symbol.get("file"),
            "relationships_used": context.relationships_used,
            "partial": context.partial,
            "truncated": context.truncated,
        },
    }
