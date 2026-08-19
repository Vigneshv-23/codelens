import pytest

from analyzer.parser import parse, parser_for, supported_languages


SAMPLES = {
    "javascript": "import value from './value.js'; const answer = 42;",
    "typescript": "interface User { name: string } const user: User = { name: 'Ada' };",
    "python": "from math import sqrt\nanswer = sqrt(4)",
    "java": "import java.util.List; class Answer { int value = 42; }",
}


@pytest.mark.parametrize("language", supported_languages())
def test_parser_loads_and_parses_each_supported_language(language):
    tree = parse(SAMPLES[language], language)

    assert tree.root_node.type == parser_for(language).grammar.root_node_type
    assert not tree.root_node.has_error


def test_parser_rejects_unknown_language():
    with pytest.raises(ValueError, match="Unsupported language"):
        parser_for("ruby")
