---
model: sonnet
---

# Commit and Push

Inspect all Datrix repos for uncommitted changes, build detailed commit messages, write `commit-messages.json`, and run the commit-and-push script.

## When to Use

- User says "commit and push", "commit all", or invokes `/commit-and-push`
- User wants to commit and push changes across multiple Datrix repositories

## Repos

The canonical repo list comes from `Get-DatrixDirectories` in `d:\datrix\datrix\scripts\common\DatrixPaths.psm1`:

```
datrix
datrix-cli
datrix-common
datrix-codegen-common
datrix-codegen-component
datrix-codegen-python
datrix-codegen-sql
datrix-codegen-typescript
datrix-language
datrix-codegen-aws
datrix-codegen-azure
datrix-codegen-docker
datrix-codegen-k8s
datrix-extensions
datrix-projects
```

Workspace root: `d:\datrix` (parent of `datrix/`).

## Workflow

### Step 1: Scan for Changes

For each repo directory that exists under `d:\datrix`:

1. Run `git -C d:\datrix\{repo} status --porcelain`
2. If output is non-empty, the repo has uncommitted changes — add it to the dirty list
3. If output is empty, skip the repo entirely

Report which repos have changes and which are clean.

### Step 2: Inspect Diffs

For each dirty repo:

1. Run `git -C d:\datrix\{repo} diff` and `git -C d:\datrix\{repo} diff --cached` to see staged and unstaged changes
2. Run `git -C d:\datrix\{repo} diff --stat` for a file-level summary
3. If diffs are large, focus on `--stat` output plus targeted reads of key changed files
4. Understand what changed and why — this drives the commit message quality

### Step 3: Build commit-messages.json

Write `d:\datrix\commit-messages.json` with:

- **Format:** A single JSON object. Keys are repo directory names (only repos with uncommitted changes). Values are detailed multi-line commit messages (use `\n` for line breaks within JSON strings).
- **Message style:**
  - No `chore:`/`feat:`/`fix:` conventional-commit prefix in the subject line
  - First line: clear summary of what the commit does
  - Blank line (`\n\n`) after the summary
  - Per-file or per-path bullet notes explaining what changed, e.g.:
    - `diff_handlers.py: entity/field/relationship handlers, forward + rollback`
    - `resilience_lib: bulkhead, circuit_breaker, retry modules`
  - Group related files under section headers when appropriate (e.g., `Generators:`, `Tests:`, `Docs:`)

**Example entry:**
```json
{
  "datrix-common": "Add transpiler context for DB session injection and lambda-body depth tracking\n\n- context.py: add known_db_service_function_sessions mapping\n- scope.py: add in_lambda_body depth counter\n\nDocs:\n- ai-agent-rules.md: replace -Tutorial flag with -TestSet in examples"
}
```

### Step 4: Run commit-and-push script

After writing the JSON file, execute:

```
powershell -File "d:/datrix/datrix/scripts/git/commit-and-push.ps1"
```

The script:
1. Reads `commit-messages.json` from the current directory (`d:\datrix`)
2. Validates all repo keys exist in the workspace
3. Cleans `.lock` files from all repos' `.git` directories
4. For each repo with a message: `git add -A`, `git commit -F {tempfile}`, `git push`
5. Exit code 1 from `git commit` means nothing to commit (not an error)

### Step 5: Report

After the script completes, report:
- Which repos were committed and pushed
- Any repos that had nothing to commit (clean working tree despite being in the JSON)
- Any errors encountered

## Error Handling

- If the commit-and-push script fails, report the error and the repo it failed on
- Do NOT retry automatically — report and wait for user decision
- If `git push` fails (e.g., auth, remote rejection), the script stops on first failure

## Anti-Patterns

- Do NOT include repos with no changes in the JSON file
- Do NOT use conventional-commit prefixes (`feat:`, `fix:`, `chore:`) in subject lines
- Do NOT write vague commit messages like "update files" or "various changes" — be specific about what changed
- Do NOT skip the diff inspection step — commit message quality depends on understanding the changes
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)
