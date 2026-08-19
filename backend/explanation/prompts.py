"""Grounded prompts for CodeLens explanations."""

from typing import Dict

from explanation.context import ExplanationContext, render_context

SYSTEM_PROMPT = """You are CodeLens, a codebase explanation assistant.

You are given information extracted from a real repository.
Use only the supplied context.
Do not invent functions, files, dependencies, relationships, or behavior.
Distinguish directly observed facts from reasonable inference.
If the supplied context is insufficient, explicitly say so.
Keep the explanation concise and developer-friendly: use no more than 120 words, prefer short paragraphs or at most 5 bullets, and do not repeat the context.
"""

ACTION_PROMPTS: Dict[str, str] = {
    "explain": "Explain what the selected symbol does, its role in the file or module, visible inputs and outputs, important dependencies, and relevant callers or callees.",
    "how_it_works": "Explain the interaction and call flow around the selected symbol using only the supplied calls, imports, contains, inherits, and implements relationships. Describe the sequence and data movement only where supported.",
    "impact": "Explain what code may be affected if the selected symbol changes. Use only supplied callers, dependents, imports, parent information, and other relationships. Do not claim an impact that the context does not support.",
}


def build_prompts(action: str, context: ExplanationContext):
    user_prompt = """{instruction}

Repository context follows. Treat it as partial when the LIMITATIONS section says so.

{context}
""".format(instruction=ACTION_PROMPTS[action], context=render_context(context))
    return SYSTEM_PROMPT, user_prompt
