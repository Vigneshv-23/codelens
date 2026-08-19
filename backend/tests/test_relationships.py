import pytest

from analyzer.extract import extract_symbols
from analyzer.parser import parse
from analyzer.relationships import extract_relationships, file_id


def analyze(source, language, file_path, repository_files=(), repository_symbols=()):
    tree = parse(source, language)
    symbols = extract_symbols(tree, language, file_path)
    relationships = extract_relationships(
        tree, language, file_path, symbols, repository_files, repository_symbols
    )
    return symbols, relationships


def kinds(relationships):
    return {(relationship.relationship_type, relationship.detail) for relationship in relationships}


@pytest.mark.parametrize(
    ("language", "source", "file_path", "repository_files", "expected_detail"),
    [
        ("python", "import pkg.util", "app.py", ["pkg/util.py"], "pkg.util"),
        ("python", "from pkg.util import Thing", "app.py", ["pkg/util.py"], "pkg.util"),
        ("javascript", "import Thing from './thing.js'", "app.js", ["thing.js"], "./thing.js"),
        ("javascript", "const Thing = require('./thing')", "app.js", ["thing.js"], "./thing"),
        ("typescript", "import Thing from './thing'", "app.ts", ["thing.ts"], "./thing"),
        ("java", "import pkg.Thing;", "app/Main.java", ["pkg/Thing.java"], "pkg.Thing"),
    ],
)
def test_imports_resolve_to_repository_files(
    language, source, file_path, repository_files, expected_detail
):
    _, relationships = analyze(source, language, file_path, repository_files)
    imports = [relationship for relationship in relationships if relationship.relationship_type == "imports"]
    assert len(imports) == 1
    assert imports[0].target_file == repository_files[0]
    assert imports[0].target_id == file_id(repository_files[0])
    assert imports[0].detail == expected_detail


def test_python_inheritance_and_contains():
    source = "class Child(Base):\n    def method(self): pass"
    symbols, relationships = analyze(source, "python", "child.py")
    base = type(symbols[0])("Base", "class", "python", "base.py", 1, 1, "base-id")
    relationships = extract_relationships(
        parse(source, "python"), "python", "child.py", symbols, ["base.py"], [base]
    )
    assert ("inherits", "Base") in kinds(relationships)
    assert ("contains", None) in kinds(relationships)
    inherit = next(r for r in relationships if r.relationship_type == "inherits")
    assert inherit.target_id == "base-id"


def test_javascript_inheritance():
    source = "class Child extends Base {}"
    symbols, _ = analyze(source, "javascript", "child.js")
    base = type(symbols[0])("Base", "class", "javascript", "base.js", 1, 1, "base-id")
    relationships = extract_relationships(
        parse(source, "javascript"), "javascript", "child.js", symbols, ["base.js"], [base]
    )
    assert any(r.relationship_type == "inherits" and r.target_id == "base-id" for r in relationships)


def test_typescript_inheritance_and_implementation():
    source = "class Child extends Base implements Runnable, Closeable {}"
    symbols, _ = analyze(source, "typescript", "child.ts")
    targets = [
        type(symbols[0])("Base", "class", "typescript", "base.ts", 1, 1, "base-id"),
        type(symbols[0])("Runnable", "interface", "typescript", "run.ts", 1, 1, "run-id"),
        type(symbols[0])("Closeable", "interface", "typescript", "close.ts", 1, 1, "close-id"),
    ]
    relationships = extract_relationships(
        parse(source, "typescript"), "typescript", "child.ts", symbols, [], targets
    )
    assert {r.target_id for r in relationships if r.relationship_type == "implements"} == {"run-id", "close-id"}
    assert any(r.relationship_type == "inherits" and r.target_id == "base-id" for r in relationships)


def test_java_inheritance_and_implementation():
    source = "class Child extends Base implements Runnable, Closeable {}"
    symbols, _ = analyze(source, "java", "Child.java")
    targets = [
        type(symbols[0])("Base", "class", "java", "Base.java", 1, 1, "base-id"),
        type(symbols[0])("Runnable", "interface", "java", "Runnable.java", 1, 1, "run-id"),
        type(symbols[0])("Closeable", "interface", "java", "Closeable.java", 1, 1, "close-id"),
    ]
    relationships = extract_relationships(parse(source, "java"), "java", "Child.java", symbols, [], targets)
    assert {r.target_id for r in relationships if r.relationship_type == "implements"} == {"run-id", "close-id"}
    assert any(r.relationship_type == "inherits" and r.target_id == "base-id" for r in relationships)


def test_unresolved_import_is_preserved_without_target():
    _, relationships = analyze("import missing.module", "python", "app.py", [])
    relationship = next(r for r in relationships if r.relationship_type == "imports")
    assert relationship.target_id is None
    assert relationship.target_file is None
    assert relationship.detail == "missing.module"


def test_duplicate_names_resolve_only_when_unambiguous():
    source = "class Child extends Base {}"
    symbols, _ = analyze(source, "javascript", "child.js")
    targets = [
        type(symbols[0])("Base", "class", "javascript", "one.js", 1, 1, "one-id"),
        type(symbols[0])("Base", "class", "javascript", "two.js", 1, 1, "two-id"),
    ]
    relationships = extract_relationships(parse(source, "javascript"), "javascript", "child.js", symbols, [], targets)
    relationship = next(r for r in relationships if r.relationship_type == "inherits")
    assert relationship.target_id is None


def test_circular_imports_and_deduplication():
    source = "import './b.js'; import './b.js';"
    _, relationships = analyze(source, "javascript", "a.js", ["b.js"])
    imports = [r for r in relationships if r.relationship_type == "imports"]
    assert len(imports) == 1

    _, reverse = analyze("import './a.js';", "javascript", "b.js", ["a.js"])
    assert reverse[0].source_id == file_id("b.js")
    assert reverse[0].target_id == file_id("a.js")


def test_multiple_relationships_between_same_files_are_preserved():
    source = "import './base.js'; class Child extends Base {}"
    symbols, _ = analyze(source, "javascript", "child.js", ["base.js"])
    base = type(symbols[0])("Base", "class", "javascript", "base.js", 1, 1, "base-id")
    relationships = extract_relationships(
        parse(source, "javascript"), "javascript", "child.js", symbols, ["base.js"], [base]
    )
    assert {relationship.relationship_type for relationship in relationships} == {"imports", "inherits"}
    assert all(relationship.source_file == "child.js" for relationship in relationships)


@pytest.mark.parametrize(
    ("language", "source", "caller_name", "callee_name"),
    [
        ("python", "def a():\n    b()\ndef b():\n    pass", "a", "b"),
        ("javascript", "function a() { b(); }\nfunction b() {}", "a", "b"),
        ("typescript", "function a() { b(); }\nfunction b() {}", "a", "b"),
        ("java", "class Service { void a() { b(); } void b() {} }", "a", "b"),
    ],
)
def test_direct_calls_resolve_to_existing_symbols(language, source, caller_name, callee_name):
    symbols, relationships = analyze(source, language, "source" + (".java" if language == "java" else ".js"))
    calls = [relationship for relationship in relationships if relationship.relationship_type == "calls"]
    caller = next(symbol for symbol in symbols if symbol.name == caller_name)
    callee = next(symbol for symbol in symbols if symbol.name == callee_name)
    assert len(calls) == 1
    assert calls[0].source_id == caller.symbol_id
    assert calls[0].target_id == callee.symbol_id
    assert calls[0].detail == callee_name


@pytest.mark.parametrize(
    ("language", "source", "file_path"),
    [
        ("python", "class Service:\n    def create(self):\n        self.validate()\n    def validate(self):\n        pass", "service.py"),
        ("javascript", "class Service { create() { this.validate(); } validate() {} }", "service.js"),
        ("typescript", "class Service { create() { this.validate(); } validate() {} }", "service.ts"),
        ("java", "class Service { void create() { validate(); } void validate() {} }", "Service.java"),
    ],
)
def test_same_class_method_calls_resolve(language, source, file_path):
    symbols, relationships = analyze(source, language, file_path)
    calls = [relationship for relationship in relationships if relationship.relationship_type == "calls"]
    caller = next(symbol for symbol in symbols if symbol.name == "create")
    callee = next(symbol for symbol in symbols if symbol.name == "validate")
    assert len(calls) == 1
    assert calls[0].source_id == caller.symbol_id
    assert calls[0].target_id == callee.symbol_id


@pytest.mark.parametrize(
    ("language", "source", "file_path"),
    [
        ("python", "def a():\n    missing()", "source.py"),
        ("javascript", "function a() { missing(); }", "source.js"),
        ("typescript", "function a() { missing(); }", "source.ts"),
        ("java", "class Service { void a() { missing(); } }", "Service.java"),
    ],
)
def test_unresolved_calls_are_ignored(language, source, file_path):
    _, relationships = analyze(source, language, file_path)
    assert not [relationship for relationship in relationships if relationship.relationship_type == "calls"]


def test_require_remains_an_import_not_a_call():
    _, relationships = analyze("const Thing = require('./thing')", "javascript", "app.js", ["thing.js"])
    assert [relationship.relationship_type for relationship in relationships] == ["imports"]


def test_duplicate_function_names_are_not_resolved():
    source = "function caller() { target(); }\nfunction target() {}"
    symbols, _ = analyze(source, "javascript", "caller.js")
    duplicate = type(symbols[0])("target", "function", "javascript", "other.js", 1, 1, "other-id")
    relationships = extract_relationships(
        parse(source, "javascript"), "javascript", "caller.js", symbols, ["other.js"], [duplicate]
    )
    assert not [relationship for relationship in relationships if relationship.relationship_type == "calls"]


def test_multiple_circular_and_duplicate_calls_are_deduplicated():
    source = "function a() { b(); b(); }\nfunction b() { a(); }"
    symbols, relationships = analyze(source, "javascript", "cycle.js")
    calls = [relationship for relationship in relationships if relationship.relationship_type == "calls"]
    ids = {symbol.name: symbol.symbol_id for symbol in symbols}
    assert {(call.source_id, call.target_id) for call in calls} == {
        (ids["a"], ids["b"]),
        (ids["b"], ids["a"]),
    }
    assert len(calls) == 2
