---
model: sonnet
---

# Commit and Push

Commit and push every Datrix repo that has uncommitted changes by running the unified
`commit-and-push.ps1` script. The script generates a commit message per dirty repo (local
Ollama model if reachable, otherwise the Claude Code CLI) and then stages, commits, and
pushes each repo in one pass. No `commit-messages.json` file is involved.

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
datrix-extensions
```

Workspace root: `d:\datrix` (parent of `datrix/`).

## Workflow

### Step 1: Run the unified commit-and-push script

Execute:

```
powershell -File "d:/datrix/datrix/scripts/git/commit-and-push.ps1"
```

The script (via `scripts/library/git/commit-and-push.py`) does everything in one pass:

1. Probes the local Ollama endpoint for reachability.
2. Picks the message source: local Ollama model if reachable, otherwise the Claude Code CLI.
3. Scans every repo under `d:\datrix` with `git status --porcelain`; clean repos are skipped.
4. For each dirty repo, generates a commit message (passed through a quality gate; deterministic fallback if the model output is unusable).
5. Cleans stale `.lock` files, then `git add -A`, `git commit -F {tempfile}`, `git push`.
6. Stops on the first git failure. A `git commit` exit code of 1 means nothing to commit (not an error).

**Useful options:**
- `-MessageSource ollama|claude` to force a backend (default `auto`).
- `-DryRun` to print the generated messages without committing.

No `commit-messages.json` file is written or read — generation and commit/push happen together.

### Step 2: Report

After the script completes, report:
- Which repos were committed and pushed
- Any repos that had nothing to commit
- Which message source was used (Ollama or Claude)
- Any errors encountered

## Message Style (for reference)

The script's prompt enforces this style; it is documented here so the output is predictable:

- No `chore:`/`feat:`/`fix:` conventional-commit prefix in the subject line
- First line: a clear, concrete summary of what the commit does
- Blank line after the summary, then a short prose paragraph describing what behavior,
  contract, validation, generation, or workflow changed and why it matters
- Prefer prose over bullets; never dump bare file paths (git already records changed files)

## Error Handling

- If the script fails, report the error and the repo it failed on
- Do NOT retry automatically — report and wait for user decision
- If `git push` fails (e.g., auth, remote rejection), the script stops on first failure

## Anti-Patterns

- Do NOT hand-write or read a `commit-messages.json` file — that workflow is gone
- Do NOT use conventional-commit prefixes (`feat:`, `fix:`, `chore:`) in subject lines
- Do NOT write vague commit messages like "update files" or "various changes" — be specific
- **NO workarounds** — don't steer around issues, don't paper over them; fix the root cause or STOP and report (CLAUDE.md rule)
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)
