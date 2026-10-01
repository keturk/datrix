---
model: haiku
---

# Commit and Push

Commit and push every Datrix repo that has uncommitted changes: first a first-pass review of
the pending changes (`pre-review.ps1`), then the unified `commit-and-push.ps1` script. The
script generates a commit message per change set (a local model on any of the network's
model servers if one answers, otherwise the Claude Code CLI) and then stages, commits, and
pushes each repo in one pass. No `commit-messages.json` file is involved.

## When to Use

- User says "commit and push", "commit all", or invokes `/commit-and-push`
- User wants to commit and push changes across multiple Datrix repositories

## Repos

The repo list is **discovered, never hardcoded.** `repo_paths()` in `datrix/scripts/library/git/commit-and-push.py` walks the workspace root and takes the `datrix` showcase repo plus every `datrix-*` directory that carries a `.git` — so a newly cloned `datrix-codegen-<lang>` repo is committed and pushed from its first commit, and an archived repo moved out of the workspace drops out, with no edit to this skill or to the script.

Do not re-introduce a literal list here. A literal list once silently omitted two real repos, which meant their commits were invisible to this skill.

Workspace root: `d:\datrix` (parent of `datrix/`).

## Workflow

### Step 1: Pre-review the pending changes

Execute:

```
powershell -File "d:/datrix/datrix/scripts/git/pre-review.ps1"
```

It checks only the lines the pending changes add to Python files, on this machine, in a few
seconds: silent `.get(key, None)` fallbacks, bare `except:`, `except ...: pass`, TODO/FIXME
comments, missing type hints, and placeholder bodies.

- **Exit 0** — go to Step 2.
- **Exit 1** — definite findings are listed with `file:line`. Do NOT commit. Report the list
  to Jon and stop: fixing code is the job of the agent that wrote it, not of this skill. If
  Jon says to commit anyway (for example, a deliberate fixture), go to Step 2.
- **Exit 2** — the review could not run; report its error and stop.

### Step 2: Run the unified commit-and-push script

Execute:

```
powershell -File "d:/datrix/datrix/scripts/git/commit-and-push.ps1"
```

The script (via `scripts/library/git/commit-and-push.py`) does everything in one pass:

1. Refuses the whole run on a customer-domain term, a .gitignore rule shadowing source, or a PolyString case round-trip in the pending changes.
2. Scans every repo under `d:\datrix` with `git status --porcelain`; clean repos are skipped.
3. Picks the message source: the first local model that answers on any of the network's model servers (Ollama, vLLM or llama-server; see `library/shared/local_llm.py`), otherwise the Claude Code CLI.
4. Splits each dirty repo into themed change sets and generates one commit message per set (passed through a quality gate; deterministic fallback if the model output is unusable).
5. Cleans stale `.lock` files, then stages, commits each set, and pushes each repo once.
6. Stops on the first git failure. A `git commit` exit code of 1 means nothing to commit (not an error).

**Useful options:**
- `-MessageSource local|claude` to force a backend (default `auto`).
- `-DryRun` to print the generated messages without committing.

No `commit-messages.json` file is written or read — generation and commit/push happen together.

### Step 3: Report

After the script completes, report:
- Which repos were committed and pushed
- Any repos that had nothing to commit
- Which message source was used (the local model and machine, or Claude)
- Any errors encountered

## Message Style (for reference)

The script's prompt enforces this style; it is documented here so the output is predictable:

- **English only.** The quality gate rejects any message containing non-Latin script and regenerates it — the local multilingual model otherwise drifts into another training language mid-paragraph.
- No `chore:`/`feat:`/`fix:` conventional-commit prefix in the subject line
- First line: a clear, concrete summary of what the commit does
- Blank line after the summary, then a short prose paragraph describing what behavior,
  contract, validation, generation, or workflow changed and why it matters
- Prefer prose over bullets; never dump bare file paths (git already records changed files)
- **Never cite a design-doc or task-file number, filename, or ID in the message** — they are `.gitignored`, ambiguously numbered across two machines, and absent after a clone, so the reference is a dangling pointer. Describe the change itself, not "task 03-12" or "design 044-x" (execution-contract §7A).

## Error Handling

- If the script fails, report the error and the repo it failed on
- Do NOT retry automatically — report and wait for user decision
- If `git push` fails (e.g., auth, remote rejection), the script stops on first failure

## Anti-Patterns

- Do NOT hand-write or read a `commit-messages.json` file — that workflow is gone
- Do NOT use conventional-commit prefixes (`feat:`, `fix:`, `chore:`) in subject lines
- Do NOT write vague commit messages like "update files" or "various changes" — be specific
- **NO workarounds** — don't steer around issues, don't paper over them. **Fix the root cause, wherever it lives** (CLAUDE.md rule). This is not a binary between "workaround" and "stop": the third option — do the real work — is the default. Stopping is licensed only by a proven B1–B4 blocker with the four-part proof (`.claude/skills/_shared/execution-contract.md`).
- **NO dodging** — "out of scope", "pre-existing", "categorically behavioral", "should be tracked separately", "not my package" are **not** blockers; they are the work. A `SubagentStop` hook greps reports for this vocabulary.
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)
