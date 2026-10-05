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
