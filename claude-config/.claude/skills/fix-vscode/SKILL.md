---
description: Diagnose and fix datrix-vscode test failures, errors, and warnings from structured test results
model: sonnet
---

# Fix VS Code Client

Diagnose and fix failures, errors, and warnings in `datrix-vscode` from a structured test-results `index.json`.

**Execute the shared playbook:** read `d:\datrix\.claude\skills\_shared\fix-package-playbook.md` and follow it exactly, with the parameters and package specifics below. The playbook owns the workflow (parse → errors → failures → warnings → verify → report), the index.json schema, abort conditions, and the cross-project handoff protocol.

## How to Invoke

```
/fix-vscode D:\datrix\datrix-vscode\.test_results\test-results-YYYYMMDD-HHMMSS\index.json
```

The argument is the absolute path to an `index.json` inside a `.test_results/test-results-*/` directory.

## Parameters

- `{PACKAGE}` = `datrix-vscode`
- `{PACKAGE_PATH}` = `d:\datrix\datrix-vscode\`

## Package Specifics

- **Scope:** `datrix-vscode` — the TypeScript VS Code client for the Datrix language server, plus the build-time scripts that generate its syntax grammars and police what its `.vsix` ships. It is not a Python package: no `pyproject.toml`, not in the venv, absent from every Python scan.
- **Fix target:** TypeScript under `src/`, the Node scripts under `scripts/`, the manifest/ignore files, or test code — **never** `out/` (compiled output) and **never** a generated grammar under `syntaxes/`.
- **Prerequisite:** Node.js >= 22 on PATH (the built-in test runner's junit reporter). `npm ci` / `npm install` must have run at least once, or nothing compiles.

### The suite runs under Node, not pytest — three playbook steps differ

`test.ps1` dispatches on the suite a package carries and writes the **same** run artifacts either way, so the playbook's parse → triage → fix loop, the `index.json` schema, the cluster rules and the abort conditions all apply unchanged. What changes:

| Playbook step | For `datrix-vscode` |
|---|---|
| **Step 1** (parse) | `collect-failure-data.ps1` works unchanged. Its emitted `test_command` is the `test.ps1 -Specific` form below — **`test-single.ps1` is pytest-only and cannot run this suite**; never construct one for it by hand. |
| **Step 7** (verify) | `powershell -File "d:/datrix/datrix/scripts/test/test.ps1" datrix-vscode -Specific "src/test/<name>.test.ts"` — selection is by FILE (the source-side `.ts` name is accepted for the compiled `.js`; a name matching nothing is an error, not a smaller run). `-Keyword <expr>` narrows further, but it is Node's `--test-name-pattern`, a **regex**, not pytest's `-k` boolean expression. |
| **Step 8** (warnings) | A Node run emits no pytest warnings section: `warnings_section_present` is false and `extract-warnings.ps1` yields an empty `warnings.json`. Skip the step; do not report it as a gap. |

Step 9's regression check (`test.ps1 datrix-vscode -Fast`) is correct as written — a Node suite marks no tests slow, so `-Fast` runs the whole suite and says so on stdout.

### Reading a Node failure — the artifacts are thin by construction

Node runs each test file in a child process. When a file fails, the JUnit reporter records **one file-level case** — `error_type: testCodeFailure`, `error_message: test failed`, `source_location: unknown:0` — and the failing subtest's name and assertion diff live only in the child's stdout, which the junit reporter does not carry into `full.log`. A cluster whose `traceback_tail` says nothing beyond `[Error: test failed] { code: 'ERR_TEST_FAILURE' … }` is therefore the **expected shape of a Node failure**, not a broken or truncated run. Do not go hunting through `failures/`, `junit-*.xml` or `full.log` for detail that is not in them.

Get the real assertion text by running that file's tests to stdout, from the package root:

```bash
cd d:/datrix/datrix-vscode && npm run compile && node --enable-source-maps --test out/test/<name>.test.js
```

The failing subtests print as `not ok N - <test name>` with the assertion diff and a `location:` line; `--enable-source-maps` makes locations name the `.ts` source and its line. Compile first — Node executes the compiled `out/` file, and testing a stale build proves nothing about the current sources. Then fix the source and verify through the `test.ps1 -Specific` command above (which compiles for you) so the result lands as a proper run.

### Test-to-Source Mapping

The playbook's `tests/unit/test_{module}.py` convention does not apply. This package's map:

| Test file | Subject under test |
|---|---|
| `src/test/serverResolution.test.ts` | `src/serverResolution.ts` |
| `src/test/generateGrammars.test.ts` | `scripts/generate-grammars.mjs` |
| `src/test/checkGrammarsFresh.test.ts` | `scripts/check-grammars-fresh.mjs` |
| `src/test/fetchKeywordManifest.test.ts` | `scripts/fetch-keyword-manifest.mjs` (+ `scripts/manifest-schema.mjs`) |
| `src/test/verifyPackageContents.test.ts` | `scripts/verify-package-contents.mjs` and the real packaged archive |
| `src/test/packageJsonContract.test.ts` | `package.json` + `.vscodeignore` — a contract test over the manifest itself, not over a module |

### Key Files

| File | Purpose |
|---|---|
| `src/extension.ts` | Client activation; starts the language server |
| `src/serverResolution.ts` | Resolves the `datrix lsp` executable from the user's `PATH` **only** — no workspace- or folder-scoped setting may influence which binary starts |
| `scripts/fetch-keyword-manifest.mjs` | Reads the keyword manifest from the installed `datrix-language` through the documented `--emit` subprocess contract — the only sanctioned access path |
| `scripts/generate-grammars.mjs` | Renders `syntaxes/*.tmLanguage.json` from that manifest |
| `scripts/verify-package-contents.mjs` | Packaging gate: fails the build when an archived file names a framework package or carries an internal path |
| `package.json` → `datrix` block | Declares `testFiles` (the compiled test glob) and `build` (the npm script run before the suite) — the repo runner reads these |
| `.vscodeignore` | What is excluded from the `.vsix` |

### Cautions

1. **`syntaxes/*.tmLanguage.json` is generated.** A failing `checkGrammarsFresh` test means regenerate (`npm run generate:grammars`) — hand-editing a grammar to match an assertion is exactly the drift that test exists to catch.
2. **Keyword vocabulary has exactly one home**, and it is not this package: the grammar and `CONFIGDSL_KEYWORDS` in `datrix-language`. If a manifest or grammar failure traces to a missing/renamed keyword, that is a `datrix-language` defect — hand off per the playbook's cross-project protocol (`/fix-language`). Never hardcode a keyword literal here to turn the test green.
3. **`verifyPackageContents` / `packageJsonContract` failures are a publishing gate, not a test-expectation problem.** The `.vsix` may not name a framework package or carry an internal filesystem path, because it ships to users. Fix the offending *content* (or exclude the file via `.vscodeignore`); never widen the scanner's allowlist, relax its patterns, or exempt a path to reach green — weakening a control that guards a distributable artifact is banned outright (playbook Step 6).
4. **This package's dependency on `datrix-language` is a subprocess contract, invisible to every import scan**, and it is declared in the monorepo (`datrix/scripts/config/cross-ecosystem-dependencies.json`), never in this package's own `package.json` — a fact naming a framework package may not enter the archive. If your fix changes what this package consumes from the toolchain, that map is the seam to check.
5. **Never write into `out/`.** It is compiled output and `.gitignore`d; an edit there disappears on the next compile and proves nothing.
