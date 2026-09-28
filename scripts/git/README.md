# Git Scripts

Git operations across all Datrix repositories.

> **Bash shell:** Examples below use PowerShell syntax. For bash, use `powershell -File "d:/datrix/datrix/scripts/git/<script>.ps1" <args>`. See [scripts/README.md](../README.md#bash-shell-invocation) for details.

## Scripts

| Script | Description |
|--------|-------------|
| `status.ps1` | Show git status for all repositories |
| `pull.ps1` | Pull latest changes for all repositories |
| `commit-and-push.ps1` | One-pass commit-and-push for all dirty repos, one commit per themed change set; messages from the first usable local model host (Ollama or vLLM), or the Claude Code CLI |

## status.ps1

Shows the git status of all repositories in the workspace.

```powershell
# Quick status (clean/has changes)
.\status.ps1

# Detailed status with changed files
.\status.ps1 -Detailed
```

### Output

```
datrix-common: clean
datrix-language: has changes
 Details:
 Branch: main
 Ahead: 2 commit(s)
 Changed files:
 M src/parser.py
 ?? new_file.py
```

## pull.ps1

Pulls latest changes from remote for all repositories.

```powershell
.\pull.ps1
```

## commit-and-push.ps1

**The single way to commit and push across all Datrix repos.**

For every repository with uncommitted changes, it splits the changes into themed change sets, generates one commit message per set, commits each set separately, and pushes the repo once — in one pass, with no intermediate `commit-messages.json` file. A thin PowerShell wrapper delegates to `scripts/library/git/commit-and-push.py`, which holds the logic (change survey and grouping, message generation, and git commit/push).

```powershell
# Auto: first usable local host, else Claude Code CLI; commit + push
.\commit-and-push.ps1

# Force a local model (errors if no local host can serve)
.\commit-and-push.ps1 -MessageSource local

# Use a specific host list, in preference order; each entry is API:URL=MODEL
.\commit-and-push.ps1 -LocalHosts openai:http://10.94.0.102:8000=nvidia/nemotron-3-super, ollama:http://10.94.0.101:11434=qwen3-coder:30b-ctx32k

# One commit per repo instead of themed sets
.\commit-and-push.ps1 -MaxCommitsPerRepo 1

# Force the Claude Code CLI
.\commit-and-push.ps1 -MessageSource claude

# Preview the generated messages without committing
.\commit-and-push.ps1 -DryRun
```

### How It Works

1. Finds the dirty repos and runs the pre-commit checks (customer-domain isolation, ignored source, PolyString case round-trips) across all of them before anything is generated or staged.
2. **Message source:**
   - Probes each configured local host in order. A host speaks either Ollama's API (`ollama:`) or the OpenAI-compatible API (`openai:`, e.g. vLLM), and is usable only if it answers its model-list query **and** serves its own model. An Ollama host's model is then loaded under its own timeout (`-LocalLoadTimeoutMs`), so a multi-minute cold load is not charged to a generate call; an OpenAI-compatible server already has its model loaded.
   - If a host fails to load or generate (an exhausted GPU, an unloadable model), it is dropped for the rest of the run and the next usable host takes over.
   - If no host is usable, or every usable host has failed → the Claude Code CLI generates the messages. It runs as a pure text call: no tools, `--safe-mode` (no workspace CLAUDE.md, hooks or skills), and its own system prompt. With `-MessageSource local` the run errors instead.
   - Reasoning models are asked to skip reasoning (Ollama `think=false`; `enable_thinking=false` through the chat template on an OpenAI-compatible server): a commit message needs none, and it multiplies generate time.
3. **Themed change sets:** each repo's dirty paths (untracked included, `.gitignore` honoured) are grouped by area. Container directories — `src/<package>`, `tests/<tier>`, `scripts`, `examples` — are stepped through, so `src/<pkg>/generators/x.py` and `tests/unit/generators/test_x.py` share the `generators` set and a feature lands in one commit with its tests. Past `-MaxCommitsPerRepo` sets, the smallest are folded into one `other changes` commit.
4. **One message per set:** the model sees only that set's diff and is told the rest is committed separately. Messages pass a quality gate (English only, no path dumps, no chat-style prose, concrete subject). A subject over 72 characters triggers one rewrite with the overrun shown to the model. If no backend produces a usable message, a model-free message states only the area and file counts — never a guessed description.
5. For each set: removes stale `.lock` files, `git add -A` over exactly the set's paths, then `git commit` restricted to those paths, so nothing else in the index rides along. Each repo is pushed once after its sets are committed.
6. Stops on the first git failure.

### Prerequisites

- **Local path:** at least one configured local host must be reachable and serve its model. The default hosts and their models, in order, are listed by `python scripts/library/git/commit-and-push.py --help`: the Dell T5820 and T7920 (RTX 3090, Ollama) and the ASUS GX10 (vLLM serving Nemotron-3-Super). The GX10 is used through vLLM, never Ollama: vLLM keeps its model resident with most of the box's unified memory, and an Ollama load beside it runs the machine out of memory.
- **Claude fallback:** the Claude Code CLI must be installed and available in PATH:

  ```bash
  npm install -g @anthropic-ai/claude-code
  ```

  Verify with: `claude --version`

### Parameters

`-MessageSource` (`auto`\|`local`\|`claude`, default `auto`), `-LocalHosts` (`API:URL=MODEL`, API `ollama` or `openai`, preference order), `-LocalTimeoutMs`, `-LocalLoadTimeoutMs`, `-LocalMaxTokens`, `-ClaudeModel`, `-ClaudeTimeoutMs`, `-MaxDiffCharsPerCommit`, `-MaxCommitsPerRepo` (default 8; 1 = one commit per repo), `-DryRun`, `-SkipCustomerDomainCheck`, `-SkipIgnoredSourceCheck`, `-SkipPolyStringCaseCheck`. See the script comment-based help for defaults.
