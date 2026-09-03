# Configuration Files

Shared configuration files used by scripts.

> **Bash shell:** Examples below use PowerShell syntax. For bash, use `powershell -File "d:/datrix/datrix/scripts/dev/<script>.ps1" <args>`. See [scripts/README.md](../README.md#bash-shell-invocation) for details.

## Files

| File / Directory | Description |
|------------------|-------------|
| `test-projects.json` | Project definitions for testing and code generation |
| `customer-term-hashes.json` | Hashed denylist of customer/project terms banned from every framework repo |
| `ignored-source-exemptions.json` | Reviewed, scoped list of `.gitignore` rules allowed to hide build output rather than source |
| `zero-environment-runtime-baseline.json` | Per-language zero-environment runtime census: reviewed exemptions (template + reason) for a language declaring the contract realized, a decrease-only `pinned_count` for one declaring it unrealized; read by `test/zero-environment-runtime-gate.ps1`, whose `-UpdateBaseline` is the only writer of counts |
| `semgrep-rules/` | Individual YAML rule files for the Semgrep anti-pattern scanner |
| `ast-grep-rules/` | Individual YAML rule files for the ast-grep structural scanner |

## test-projects.json

Defines example projects organized by category for batch testing and generation.

### Structure

```json
{
 "description": "Shared project definitions for testing and generation",
 "defaultLanguage": "python",
 "defaultPlatform": "docker",
 "projects": {
 "foundation": [...],
 "features": [...],
 "domains": [...]
 }
}
```

### Project Categories

| Category | Path | Description |
|----------|------|-------------|
| `foundation` | `examples/01-foundation/` | Foundation examples |
| `features` | `examples/02-features/` | Feature-focused examples by capability |
| `domains` | `examples/03-domains/` | Domain-specific examples (blog, ecommerce, healthcare) |
### Project Entry Format

```json
{
 "name": "foundation",
 "path": "examples/01-foundation/system.dtrx",
 "description": "Foundation examples and core syntax patterns"
}
```

### Usage

Used by:
- `dev/generate.ps1` with `-All`, `-Domains`, etc. flags
- `test/run-complete.ps1` for batch testing
- Python scripts via `library/shared/test_projects.py`

## customer-term-hashes.json

The denylist behind `test/customer-domain-isolation-gate.ps1` and the pre-commit check in
`git/commit-and-push.ps1`. Customer/project domain language — a customer name, their service
names, their cloud resource names, paths into their checkout — must never appear in a
framework repo (`datrix`, `datrix-cli`, `datrix-codegen-*`, `datrix-common`,
`datrix-extensions`, `datrix-language`).

**It stores digests, never terms.** A plaintext denylist naming the customer would itself be
the violation it polices — the banned term would sit, in the clear, in the very repo it is
banned from. Only the SHA-256 of each lowercased term is committed, so the check travels with
the checkout and enforces on every machine while the term exists in none of them.

### Structure

```json
{
 "algorithm": "sha256",
 "min_token_length": 5,
 "terms": [
 { "hash": "<sha256 of the lowercased term>", "hint": "customer project" }
 ]
}
```

`hint` is a non-identifying note for a human reading the file; it must never narrow down the
term. `min_token_length` bounds which tokens are hashed during a scan — below ~5 characters a
term collides with ordinary words.

### Registering a term

Never hand-edit a hash. Use the gate, which hashes the term and discards the plaintext:

```powershell
.\test\customer-domain-isolation-gate.ps1 -AddTerm acmecorp -Hint "customer project"
```

An empty `terms` list is legitimate (a checkout with no customer projects); both callers
report `NOT ENFORCED` rather than a silent pass. A missing or malformed file is an error.

## ignored-source-exemptions.json

The reviewed exemption list behind `test/ignored-source-gate.ps1`. That gate computes, per
framework repo, the difference between the working tree and what a `git add -A` would stage.
Every element of that difference must appear here; anything else is a source file a
`.gitignore` rule is silently deleting from every clone — a failure invisible locally (the
file is on disk, the tests pass) that only surfaces after a clone or a wheel install.

**Each entry excuses one rule over one path scope.** The rule is identified by the
`.gitignore` file and the pattern text `git check-ignore -v` itself reports, never by a line
number (which moves). The scope is load-bearing rather than decorative: an unanchored pattern
matches at any depth, so an entry for the root `build/` tree must not also excuse the same
rule swallowing a `templates/build/` directory full of source.

### Structure

```json
{
 "pinned_count": 23,
 "exemptions": [
 {
 "repos": ["*"],
 "gitignore": ".gitignore",
 "pattern": "__pycache__/",
 "path_glob": "**/__pycache__/**",
 "reason": "CPython bytecode cache, rewritten on every interpreter run."
 }
 ]
}
```

`repos` is a list of repo names, or `["*"]` for every framework repo — the wildcard is what
keeps a newly cloned `datrix-*` package covered with no edit here. `path_glob` is
segment-aware: `**/` spans whole path segments, `**` spans the remainder, `*` and `?` stay
inside one segment. `reason` is required and must say what writes the output and why it is
never published.

`pinned_count` must equal `len(exemptions)`; the gate refuses to run (exit 2) when they
disagree, so an entry cannot be added or removed without the reviewed number moving in the
same change. A missing or malformed file is an error, never an empty exemption set. An entry
that matches nothing on a given machine is reported, not failed — a coverage report or an
`npm install` tree only exists once the tool has run.

## semgrep-rules/

Individual YAML rule files for the Semgrep anti-pattern scanner (`dev/semgrep.ps1`). Each file defines one Semgrep rule that enforces a `.cursorrules` coding standard.

See [semgrep-rules/README.md](semgrep-rules/README.md) for the full rule catalog, usage examples, and instructions for adding new rules.

### Quick Usage

```powershell
# List all available rules
.\dev\semgrep.ps1 -ListRules

# Run all rules
.\dev\semgrep.ps1 -All

# Run a single rule
.\dev\semgrep.ps1 -All -Rule empty-except-pass
```

## ast-grep-rules/

Individual YAML rule files for the ast-grep structural scanner (`dev/ast-grep.ps1`). Each file defines one ast-grep rule for fast AST-shaped Python searches.

See [ast-grep-rules/README.md](ast-grep-rules/README.md) for the full rule catalog, usage examples, and notes on PowerShell quoting for ast-grep metavariables.

### Quick Usage

```powershell
# List all available rules
.\dev\ast-grep.ps1 -ListRules

# Run all saved rules
.\dev\ast-grep.ps1 -All

# Run a single saved rule
.\dev\ast-grep.ps1 -All -Rule placeholder-notimplemented-body

# Run a one-off structural pattern
.\dev\ast-grep.ps1 -All -Pattern 'raise Exception($MSG)'
```
