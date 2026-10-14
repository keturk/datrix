"""Exercise guard-code-standards.py with real files in a real directory tree.

The hook judges the DELTA an edit makes, so every case builds the file as it exists, applies a
real Write or Edit payload, and asserts both directions: new violations block; legacy ones, fixes,
strings that merely mention the words, and files that do not parse never do.
"""
import json
import os
import subprocess
import sys

HOOK = os.path.join(r"d:\datrix\.claude\hooks", "guard-code-standards.py")
fails = []
BLOCK, ALLOW = 2, 0
REPO = r"d:\datrix\datrix-alpha"  # matches the framework-repo shape; the files live in a real temp tree below


def run(payload):
    p = subprocess.run([sys.executable, HOOK], input=json.dumps(payload), capture_output=True, text=True)
    return p.returncode, p.stderr


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: exit {got} want {want}")
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")


class Repo:
    """A directory whose path starts d:/datrix/datrix-gate-<pid>/, so the hook treats it as a framework repo."""

    def __init__(self):
        self.root = os.path.join(r"d:\datrix", f"datrix-codestd-gate-{os.getpid()}")

    def __enter__(self):
        os.makedirs(self.root)
        return self

    def __exit__(self, *exc):
        for base, dirs, files in os.walk(self.root, topdown=False):
            for name in files:
                os.remove(os.path.join(base, name))
            for name in dirs:
                os.rmdir(os.path.join(base, name))
        os.rmdir(self.root)

    def file(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path


def write(path, content):
    return run({"tool_name": "Write", "tool_input": {"file_path": path, "content": content}})[0]


def edit(path, old, new, replace_all=False):
    return run({"tool_name": "Edit", "tool_input": {"file_path": path, "old_string": old,
                                                    "new_string": new, "replace_all": replace_all}})[0]


with Repo() as repo:
    print("== mocks and fakes in tests ==")
    test = repo.file("tests/unit/test_a.py", "def test_a():\n    assert 1 == 1\n")
    check("unittest.mock import added to a test", edit(test, "def test_a", "from unittest.mock import MagicMock\n\n\ndef test_a"), BLOCK)
    check("plain `import mock`", edit(test, "def test_a", "import mock\n\n\ndef test_a"), BLOCK)
    check("`import unittest.mock as m`", edit(test, "def test_a", "import unittest.mock as m\n\n\ndef test_a"), BLOCK)
    check("SimpleNamespace import", edit(test, "def test_a", "from types import SimpleNamespace\n\n\ndef test_a"), BLOCK)
    check("the mocker fixture", edit(test, "def test_a():", "def test_a(mocker):"), BLOCK)
    check("a NEW test file with a mock", write(os.path.join(repo.root, "tests", "test_new.py"),
                                              "from unittest import mock\nfrom unittest.mock import patch\n"), BLOCK)
    check("conftest counts as test code", write(os.path.join(repo.root, "src", "conftest.py"),
                                               "from unittest.mock import Mock\n"), BLOCK)
    check("real objects in a test stay allowed", edit(test, "assert 1 == 1", "assert [1, 2] == [1, 2]"), ALLOW)
    check("pytest tmp_path/monkeypatch stay allowed",
          edit(test, "def test_a():", "def test_a(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):"), ALLOW)
    src = repo.file("src/pkg/mod.py", "X = 1\n")
    check("the same import in SOURCE is not this rule", edit(src, "X = 1", "from types import SimpleNamespace\nX = 1"), ALLOW)

    print("== silent exception handlers ==")
    mod = repo.file("src/pkg/work.py", "def f():\n    return 1\n")
    check("except: pass", edit(mod, "    return 1", "    try:\n        g()\n    except:\n        pass\n    return 1"), BLOCK)
    check("except Exception: pass", edit(mod, "    return 1", "    try:\n        g()\n    except Exception:\n        pass\n    return 1"), BLOCK)
    check("except OSError with an ellipsis body", edit(mod, "    return 1", "    try:\n        g()\n    except OSError:\n        ...\n    return 1"), BLOCK)
    check("a handler that handles stays allowed", edit(mod, "    return 1", "    try:\n        g()\n    except OSError as exc:\n        raise RuntimeError('x') from exc\n    return 1"), ALLOW)
    check("a handler that logs stays allowed", edit(mod, "    return 1", "    try:\n        g()\n    except OSError:\n        log.warning('x')\n    return 1"), ALLOW)
    check("contextlib.suppress stays allowed", edit(mod, "    return 1", "    with contextlib.suppress(FileNotFoundError):\n        g()\n    return 1"), ALLOW)

    print("== TODO comments ==")
    check("# TODO", edit(mod, "    return 1", "    # TODO: handle the other case\n    return 1"), BLOCK)
    check("# FIXME trailing", edit(mod, "    return 1", "    return 1  # FIXME later"), BLOCK)
    check("# XXX", edit(mod, "    return 1", "    # XXX hack\n    return 1"), BLOCK)
    check("a string naming TODO stays allowed", edit(mod, "    return 1", "    return 'TODO'"), ALLOW)
    check("a pattern list naming the words stays allowed",
          edit(mod, "    return 1", "    return ('TODO', 'FIXME')"), ALLOW)
    check("a docstring naming TODO stays allowed", edit(mod, "def f():", 'def f():\n    """Rejects a TODO marker."""'), ALLOW)
    check("an ordinary comment stays allowed", edit(mod, "    return 1", "    # explains why\n    return 1"), ALLOW)

    print("== type hints ==")
    typed = repo.file("src/pkg/typed.py", "def f(x: int) -> int:\n    return x\n")
    check("a new function with no return annotation",
          edit(typed, "def f(", "def g(y: int):\n    return y\n\n\ndef f("), BLOCK)
    check("a new parameter with no annotation", edit(typed, "def f(x: int)", "def f(x: int, y)"), BLOCK)
    check("self and cls need none", edit(typed, "def f(x: int) -> int:\n    return x\n",
                                         "class C:\n    def m(self, x: int) -> int:\n        return x\n\n"
                                         "    @classmethod\n    def k(cls) -> None:\n        return None\n"), ALLOW)
    check("*args/**kwargs need annotations too", edit(typed, "def f(x: int)", "def f(x: int, *rest)"), BLOCK)

    print("== Any ==")
    check("Any in a parameter", edit(typed, "def f(x: int)", "def f(x: Any)"), BLOCK)
    check("Any inside a generic return type", edit(typed, "-> int:", "-> dict[str, Any]:"), BLOCK)
    check("Any in an annotated assignment", edit(typed, "def f(", "X: list[Any] = []\n\n\ndef f("), BLOCK)
    check("typing.Any spelled with the module", edit(typed, "def f(x: int)", "def f(x: typing.Any)"), BLOCK)
    check("a mode='before' model validator may take Any",
          edit(typed, "def f(", "class M:\n    @model_validator(mode=\"before\")\n    @classmethod\n"
                                 "    def pre(cls, data: Any) -> Any:\n        return data\n\n\ndef f("), ALLOW)
    check("a mode='after' validator may not",
          edit(typed, "def f(", "class M:\n    @model_validator(mode=\"after\")\n"
                                 "    def post(self, data: Any) -> Any:\n        return data\n\n\ndef f("), BLOCK)
    check("the word Any in a string or a name stays allowed",
          edit(typed, "    return x", "    AnyThing = 'Any'\n    return x"), ALLOW)

    print("== %-style logging ==")
    check("an f-string message", edit(typed, "    return x", "    LOG.info(f\"x={x}\")\n    return x"), BLOCK)
    check("a .format() message", edit(typed, "    return x", "    logger.warning(\"x={}\".format(x))\n    return x"), BLOCK)
    check("a % expression", edit(typed, "    return x", "    self.logger.error(\"x=%s\" % x)\n    return x"), BLOCK)
    check("LOG.log with an f-string message", edit(typed, "    return x", "    LOG.log(10, f\"x={x}\")\n    return x"), BLOCK)
    check("%-style with arguments stays allowed", edit(typed, "    return x", "    LOG.info(\"x=%s\", x)\n    return x"), ALLOW)
    check("an f-string to a non-logger stays allowed", edit(typed, "    return x", "    print(f\"x={x}\")\n    return x"), ALLOW)

    print("== silent .get(key, None) ==")
    check(".get(key, None)", edit(typed, "    return x", "    y = d.get(\"k\", None)\n    return x"), BLOCK)
    check(".get(key) and .get(key, default) stay allowed",
          edit(typed, "    return x", "    y = d.get(\"k\")\n    z = d.get(\"k\", 0)\n    return x"), ALLOW)

    print("== cognitive complexity ==")
    nested = "".join(f"{'    ' * (depth + 1)}if x > {depth}:\n" for depth in range(7)) + f"{'    ' * 8}return 1\n"
    check("a new function over 15", edit(typed, "def f(", f"def deep(x: int) -> int:\n{nested}    return 0\n\n\ndef f("), BLOCK)
    legacy_deep = repo.file("src/pkg/deep.py", f"def deep(x: int) -> int:\n{nested}    return 0\n")
    check("an edit inside a function already over 15", edit(legacy_deep, "    return 0", "    return 2"), ALLOW)

    print("== flattened entities (generators only) ==")
    gen = repo.file("src/pkg/generators/emit.py", "def emit(app: App) -> list[str]:\n    return []\n")
    check("app.all_entities() in a generator",
          edit(gen, "    return []", "    return [str(e) for e in app.all_entities()]"), BLOCK)
    check("self.application.all_entities() in a generator",
          edit(gen, "    return []", "    return [str(e) for e in self.application.all_entities()]"), BLOCK)
    check("one comprehension over every service's entities",
          edit(gen, "    return []", "    return [str(e) for s in app.services.values() "
                                      "for b in s.rdbms_blocks.values() for e in b.entities.values()]"), BLOCK)
    check("service.all_entities() stays allowed",
          edit(gen, "    return []", "    return [str(e) for s in app.services.values() for e in [s]]"), ALLOW)
    check("per-service loops stay allowed",
          edit(gen, "    return []", "    out = []\n    for s in app.services.values():\n"
                                      "        out += [str(e) for e in s.all_entities()]\n    return out"), ALLOW)
    validator = repo.file("src/pkg/validators/check.py", "def check(app: App) -> int:\n    return 0\n")
    check("app.all_entities() outside a generator stays allowed",
          edit(validator, "    return 0", "    return len(list(app.all_entities()))"), ALLOW)

    print("== only the delta is judged ==")
    legacy = repo.file("src/pkg/legacy.py",
                       "def f():\n    try:\n        g()\n    except Exception:\n        pass\n    # TODO old\n    return 1\n")
    check("an unrelated edit to a file with legacy violations", edit(legacy, "return 1", "return 2"), ALLOW)
    check("fixing a legacy violation", edit(legacy, "    except Exception:\n        pass\n",
                                           "    except Exception as exc:\n        raise RuntimeError('x') from exc\n"), ALLOW)
    check("ADDING a second violation to a file that has one",
          edit(legacy, "    return 1", "    try:\n        h()\n    except Exception:\n        pass\n    return 1"), BLOCK)
    check("replace_all across two sites that both gain one",
          edit(repo.file("src/pkg/two.py", "def a():\n    return 1\n\n\ndef b():\n    return 1\n"),
               "    return 1", "    # TODO x\n    return 1", replace_all=True), BLOCK)

    print("== fails open / out of scope ==")
    check("a file that does not parse after the edit", edit(mod, "def f():", "def f(:"), ALLOW)
    broken = repo.file("src/pkg/broken.py", "def f(:\n    return 1\n")
    check("a file that ALREADY does not parse on disk, edit adds a violation",
          edit(broken, "    return 1", "    # TODO x\n    return 1"), ALLOW)
    check("a Write whose content does not parse, with a violation in it",
          write(os.path.join(repo.root, "src", "half.py"), "def f(:\n    # TODO x\n    try:\n        pass\n"), ALLOW)
    check("an Edit whose old_string is not in the file", edit(mod, "no such text", "# TODO"), ALLOW)
    check("a non-Python file", write(os.path.join(repo.root, "docs", "n.md"), "# TODO later\n"), ALLOW)
    check("generated output", write(os.path.join(repo.root, "generated", "x", "svc.py"), "try:\n    a()\nexcept:\n    pass\n"), ALLOW)
    check("a path outside the framework repos", write(r"d:\datrix\acme-shop\a.py", "# TODO\n"), ALLOW)
    check("the harness's own hooks", write(r"d:\datrix\datrix\claude-config\.claude\hooks\x.py",
                                          "try:\n    a()\nexcept OSError:\n    pass\n"), ALLOW)
    check("a brand-new clean file", write(os.path.join(repo.root, "src", "clean.py"), "def f() -> int:\n    return 1\n"), ALLOW)
    check("the NotebookEdit tool is ignored", run({"tool_name": "NotebookEdit",
                                                  "tool_input": {"file_path": mod}})[0], ALLOW)

    print("== literal-fact tests where the package carries the case runner ==")
    literal = ("\n\ndef test_port(index: dict[str, str]) -> None:\n    assert index['compose.yml'] == '8080'\n"
               "    assert 'debug' not in index\n")
    uncased = repo.file("tests/unit/test_facts.py", "def test_kept(index: dict) -> None:\n    assert index == {}\n")
    check("no case runner: a literal-fact test stays allowed", edit(uncased, "    assert index == {}\n",
                                                                     "    assert index == {}\n" + literal), ALLOW)
    repo.file("tests/test_cases.py", "def test_case(case: object) -> None:\n    case.run()\n")
    facts = repo.file("tests/unit/test_more_facts.py", "def test_kept(index: dict) -> None:\n    assert index == {}\n")
    check("a literal-fact test added beside the case runner", edit(facts, "    assert index == {}\n",
                                                                   "    assert index == {}\n" + literal), BLOCK)
    check("a NEW module holding one", write(os.path.join(repo.root, "tests", "unit", "test_new_facts.py"),
                                            literal.lstrip()), BLOCK)
    check("a test with a loop is not a literal fact", edit(facts, "    assert index == {}\n",
                                                           "    assert index == {}\n\n\ndef test_all(index: dict) -> None:\n"
                                                           "    for key in index:\n        assert key in 'ab'\n"), ALLOW)
    check("a set comparison is not a literal fact", edit(facts, "    assert index == {}\n",
                                                         "    assert index == {}\n\n\ndef test_set(index: dict) -> None:\n"
                                                         "    assert set(index) == {'a'}\n"), ALLOW)
    legacy = repo.file("tests/unit/test_legacy.py",
                       "def test_port(index: dict) -> None:\n    assert index['a'] == '8080'\n")
    check("editing a legacy literal-fact test is not adding one", edit(legacy, "'8080'", "'8081'"), ALLOW)
    code, err = run({"tool_name": "Edit", "tool_input": {"file_path": facts, "old_string": "    assert index == {}\n",
                                                         "new_string": "    assert index == {}\n" + literal}})
    check("the refusal names the test and the cases.ps1 new form",
          all(s in err for s in ("[literal-fact] def test_port", "cases.ps1 new", "`absent` case")), True)

    print("== migrated test shapes where the package carries the case runner ==")
    migrated = {
        "a diagnostic-code test": ("\n\ndef test_fires(result: object) -> None:\n"
                                   "    assert diagnostic_codes(result) == ('ENT003',)\n", "diagnostic-code"),
        "a transpiled-literal test": ("\n\ndef test_emits(transpiler: object, node: object) -> None:\n"
                                      "    emitted = transpiler.transpile_expression(node).code\n"
                                      "    assert emitted == 'amount * 2'\n", "transpiled-literal"),
        "an lsp-at-a-Position test": ("\n\ndef test_offers(document: str) -> None:\n"
                                      "    items = complete(document, Position(line=0, character=3), app=None, "
                                      "symbol_index=None)\n"
                                      "    assert [item.label for item in items] == ['String']\n", "lsp-position"),
    }
    for label, (sample, shape) in migrated.items():
        check(f"{label} added beside the case runner", edit(facts, "    assert index == {}\n",
                                                            "    assert index == {}\n" + sample), BLOCK)
        code, err = run({"tool_name": "Edit", "tool_input": {"file_path": facts, "old_string": "    assert index == {}\n",
                                                             "new_string": "    assert index == {}\n" + sample}})
        check(f"{label}: refused once, as its migrated shape, naming the annotation",
              f"({shape})" in err and "[literal-fact]" not in err and "// @" in err, True)
    check("a code-constant check is no migrated shape", edit(facts, "    assert index == {}\n",
                                                             "    assert index == {}\n\n\ndef test_const() -> None:\n"
                                                             "    assert len(error_codes.SYS001) == 6\n"), ALLOW)

    print("== schema-shaped tests where the package carries the model contract runner ==")
    # The planted package's src/ names an installed import package, so the shared venv resolves the
    # models it constructs; its tests/ holds no fixture, so no item proves a fact yet (uncovered).
    model_test = repo.file("tests/unit/test_platform.py",
                           "import pytest\nfrom pydantic import ValidationError\n\n"
                           "from datrix_codegen_docker.config.docker import DockerPlatformConfig\n\n\n"
                           "def test_kept() -> None:\n    assert DockerPlatformConfig().registry == ''\n")
    raises_bound = ("\n\ndef test_retention_positive() -> None:\n"
                    "    with pytest.raises(ValidationError):\n"
                    "        DockerPlatformConfig.model_validate({'kafka_default_retention_ms': 0})\n")
    check("no model contract runner: a schema-shaped test stays allowed",
          edit(model_test, "== ''\n", "== ''\n" + raises_bound), ALLOW)
    repo.file("src/datrix_codegen_docker/__init__.py", "")
    repo.file("tests/test_model_contracts.py", "def test_model_contract(item: object) -> None:\n    item.check()\n")
    check("a bound restated beside the model contract runner",
          edit(model_test, "== ''\n", "== ''\n" + raises_bound), BLOCK)
    check("an unknown key restated beside the runner", edit(model_test, "== ''\n", "== ''\n"
          "\n\ndef test_unknown() -> None:\n    with pytest.raises(ValidationError):\n"
          "        DockerPlatformConfig.model_validate({'registryy': 'x'})\n"), BLOCK)
    check("a default restated beside the runner", edit(model_test, "== ''\n", "== ''\n"
          "\n\ndef test_default() -> None:\n    config = DockerPlatformConfig.model_validate({})\n"
          "    assert config.kafka_default_retention_ms is None\n"), BLOCK)
    check("a test asserting a supplied value states no schema fact", edit(model_test, "== ''\n", "== ''\n"
          "\n\ndef test_supplied() -> None:\n"
          "    config = DockerPlatformConfig.model_validate({'kafka_default_retention_ms': 5})\n"
          "    assert config.kafka_default_retention_ms == 5\n"), ALLOW)
    code, err = run({"tool_name": "Edit", "tool_input": {"file_path": model_test, "old_string": "== ''\n",
                                                         "new_string": "== ''\n" + raises_bound}})
    check("the refusal names the model, the fact and the fixture remedy",
          all(s in err for s in ("[schema-shaped] def test_retention_positive", "DockerPlatformConfig",
                                 "kafka_default_retention_ms::bound_gt", "model-contracts.ps1 facts")), True)

    print("== per-row hand tests where the package carries the table runner ==")
    # The planted package registers one table from its tests/conftest.py, bound to PLANTED_TYPES;
    # the shared venv loads that session to resolve which rows a test reads.
    row_test = repo.file("tests/unit/test_types.py",
                         "from planted.types import PLANTED_TYPES\n\n\n"
                         "def test_kept() -> None:\n    assert len(PLANTED_TYPES) > 0\n")
    # An int comparison, so the case runner's literal-fact rule (planted above) does not also fire.
    row_value = ("\n\ndef test_string_annotation() -> None:\n"
                 "    assert PLANTED_TYPES['String'].arity == 1\n")
    check("no table runner: a per-row hand test stays allowed",
          edit(row_test, "> 0\n", "> 0\n" + row_value), ALLOW)
    repo.file("tests/conftest.py",
              "from datrix_testing.tables.contract import TableContract\n"
              "from datrix_testing.tables.registry import register_table\n\n\n"
              "def _rows() -> list[tuple[str, str]]:\n    return [('String', 'str')]\n\n\n"
              "def _check(row: str) -> None:\n    return None\n\n\n"
              "def _row_id(key: object) -> str | None:\n    return key if isinstance(key, str) else None\n\n\n"
              "register_table(TableContract(name='planted', tags=('table-contracts',), rows=_rows, check=_check,\n"
              "                             lookup_names=frozenset({'PLANTED_TYPES'}), key_row_id=_row_id))\n")
    repo.file("tests/test_tables.py", "def test_table(item: object) -> None:\n    item.check()\n")
    check("a row value restated beside the table runner", edit(row_test, "> 0\n", "> 0\n" + row_value), BLOCK)
    check("a row's presence restated beside the runner", edit(row_test, "> 0\n", "> 0\n"
          "\n\ndef test_string_present() -> None:\n    assert 'String' in PLANTED_TYPES\n"), BLOCK)
    check("a test over the whole table is no per-row test", edit(row_test, "> 0\n", "> 0\n"
          "\n\ndef test_every_row() -> None:\n    for key in PLANTED_TYPES:\n        assert PLANTED_TYPES[key]\n"), ALLOW)
    check("an existing per-row test edited in place is never refused",
          edit(repo.file("tests/unit/test_legacy_types.py", "from planted.types import PLANTED_TYPES\n\n\n"
                         "def test_old() -> None:\n    assert PLANTED_TYPES['String'] is not None\n"),
               "is not None", "is not None\n    assert 'String' in PLANTED_TYPES"), ALLOW)
    code, err = run({"tool_name": "Edit", "tool_input": {"file_path": row_test, "old_string": "> 0\n",
                                                         "new_string": "> 0\n" + row_value}})
    check("the refusal names the row, the item and the runner remedy",
          all(s in err for s in ("[table-row] def test_string_annotation", "PLANTED_TYPES['String']",
                                 "test_table[planted::String]", "tables.ps1 rows")), True)

    print("== the message names what was added ==")
    code, err = run({"tool_name": "Edit", "tool_input": {
        "file_path": mod, "old_string": "    return 1",
        "new_string": "    # TODO x\n    try:\n        g()\n    except:\n        pass\n    return 1"}})
    check("blocks", code, BLOCK)
    check("names the TODO, the handler and both remedies",
          all(s in err for s in ("[todo]", "[silent-except]", "except (bare): pass", "contextlib.suppress",
                                 "No placeholders/TODOs")), True)

print()
if fails:
    print(f"{len(fails)} FAILURE(S):")
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("all checks passed")
