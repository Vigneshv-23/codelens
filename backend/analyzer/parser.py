from dataclasses import dataclass
from typing import Callable, Mapping

from tree_sitter import Language, Parser, Tree
import tree_sitter_java
import tree_sitter_javascript
import tree_sitter_python
import tree_sitter_typescript

from .models import LanguageName


@dataclass(frozen=True)
class Grammar:
    language: LanguageName
    tree_sitter_language: Language
    root_node_type: str


GRAMMARS: Mapping[LanguageName, Grammar] = {
    "python": Grammar("python", Language(tree_sitter_python.language()), "module"),
    "javascript": Grammar(
        "javascript", Language(tree_sitter_javascript.language()), "program"
    ),
    "typescript": Grammar(
        "typescript",
        Language(tree_sitter_typescript.language_typescript()),
        "program",
    ),
    "java": Grammar("java", Language(tree_sitter_java.language()), "program"),
}


class CodeParser:
    def __init__(self, grammar: Grammar):
        self.grammar = grammar
        self._parser = Parser()
        self._parser.language = grammar.tree_sitter_language

    def parse(self, source: str) -> Tree:
        return self._parser.parse(source.encode("utf-8"))


def parser_for(language: LanguageName) -> CodeParser:
    try:
        grammar = GRAMMARS[language]
    except KeyError as error:
        raise ValueError(f"Unsupported language: {language}") from error
    return CodeParser(grammar)


def parse(source: str, language: LanguageName) -> Tree:
    return parser_for(language).parse(source)


def supported_languages() -> tuple[LanguageName, ...]:
    return tuple(GRAMMARS)
