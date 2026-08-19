import pytest

from analyzer.extract import extract_symbols
from analyzer.parser import parse


@pytest.mark.parametrize(
    ("language", "source", "expected"),
    [
        (
            "python",
            "import os\nfrom pathlib import Path\nclass Box:\n    def open(self): pass\ndef build(): pass",
            {("import", "import os"), ("import", "from pathlib import Path"), ("class", "Box"), ("function", "open"), ("function", "build")},
        ),
        (
            "javascript",
            "import value from 'value';\nexport class Box { open() {} }\nexport function build() {}",
            {("import", "import value from 'value'"), ("export", "class"), ("class", "Box"), ("method", "open"), ("export", "function"), ("function", "build")},
        ),
        (
            "typescript",
            "import value from 'value';\nexport interface Box {}\nexport class Store { open() {} }\nexport function build() {}",
            {("import", "import value from 'value'"), ("export", "interface"), ("interface", "Box"), ("export", "class"), ("class", "Store"), ("method", "open"), ("export", "function"), ("function", "build")},
        ),
        (
            "java",
            "import java.util.List;\ninterface Box {}\nclass Store { void open() {} }",
            {("import", "import java.util.List"), ("interface", "Box"), ("class", "Store"), ("method", "open")},
        ),
    ],
)
def test_extracts_expected_symbols(language, source, expected):
    symbols = extract_symbols(parse(source, language), language, f"sample.{language}")
    assert {(symbol.kind, symbol.name) for symbol in symbols} == expected


def test_nested_symbols_have_parent_class_id_and_metadata():
    source = "class Outer { method() {} }"
    symbols = extract_symbols(parse(source, "javascript"), "javascript", "sample.js")
    outer = next(symbol for symbol in symbols if symbol.name == "Outer")
    method = next(symbol for symbol in symbols if symbol.name == "method")
    assert method.parent_id == outer.symbol_id
    assert method.symbol_id
    assert method.start_line == 1
    assert method.end_line == 1


def test_empty_source_returns_no_symbols():
    assert extract_symbols(parse("", "python"), "python", "empty.py") == []


def test_malformed_source_still_extracts_usable_symbols():
    symbols = extract_symbols(
        parse("class Broken { function() {", "javascript"), "javascript", "broken.js"
    )
    assert any(symbol.kind == "class" and symbol.name == "Broken" for symbol in symbols)


def test_symbols_have_unique_ids_for_multiple_same_named_declarations():
    source = "function build() {}\nfunction build() {}"
    symbols = extract_symbols(parse(source, "javascript"), "javascript", "many.js")
    functions = [symbol for symbol in symbols if symbol.kind == "function"]
    assert len(functions) == 2
    assert len({symbol.symbol_id for symbol in functions}) == 2
