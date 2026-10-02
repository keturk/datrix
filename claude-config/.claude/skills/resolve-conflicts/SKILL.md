---
model: claude-sonnet-5-5
effort: medium
description: Pull one or more Datrix repos over uncommitted local work — shelve only the files the pull would overwrite, pull, reapply, and merge any overlap by hand. Unlocks path-limited stash, index-only reset, and --ours/--theirs for this invocation only.
argument-hint: "[repo ...]  (default: every repo whose pull is blocked)"
disable-model-invocation: true
---

# Resolve Pull Conflicts

Bring each named repo up to date with its upstream **without losing a single uncommitted
change**. The usual trigger is `pull.ps1` printing, for one or more repos:

```
error: Your local changes to the following files would be overwritten by merge:
        docs/architecture/config-system.md
Please commit your changes or stash them before you merge.
```

The working tree holds work from tasks you know nothing about. The only acceptable end
state per repo is: HEAD equals upstream (or a merge of it), and every local edit that
existed before you started still exists afterwards, either unchanged or merged with the
incoming change.

## What this invocation unlocks

`guard-forbidden-commands.py` normally refuses every stash, reset, restore, and path
checkout. While **Jon's `/resolve-conflicts` is the latest prompt** (it reads this from
the transcript; a follow-up prompt closes the window), it allows exactly these:

| Allowed | Use |
|---|---|
| `git stash push -m <msg> -- <paths>` | shelve **only** the files the pull would overwrite |
| `git stash apply stash@{N}` / `pop` / `drop stash@{N}` / `show` / `list` | bring them back; drop the entry only after verifying |
| `git reset [-q] [HEAD] [-- <paths>]` | unstage (index only; the tree and the branch are kept) |
| `git restore --staged <paths>` | unstage |
| `git checkout --ours\|--theirs -- <paths>` | take one side of a conflicted path, when one side is provably a superset |

Still refused even now, and never to be routed around: `reset --hard/--soft/--keep` or to
another commit, `restore` of the working tree, `checkout -- <path>`, a bare or path-less
`stash`, `stash clear`, `revert`, `clean -f`. If you believe you need one, you are about
to destroy work — stop and re-read the situation.

## Repos

Arguments name repos (`datrix-common`, `datrix-codegen-python`, …). With no arguments,
take every directory under `d:\datrix` that carries a `.git` — discovered, never a
hardcoded list — and work the ones whose pull is blocked.

## Workflow (per repo)

Run git as `git -C d:/datrix/<repo> …`. Keep repos independent: one repo's trouble never
stops the others.

### 1. Measure

```
git -C <repo> fetch
git -C <repo> rev-list --left-right --count HEAD...@{u}      # ahead  behind
git -C <repo> status --porcelain
git -C <repo> diff --name-only HEAD @{u}                     # files the pull changes
```

- **Behind 0** → nothing to pull. Report "up to date" and move on.
- **Tracked overlap** = files modified locally (staged or not) ∩ files the pull changes.
- **Untracked collisions** = untracked local files ∩ files the pull adds
  (`git diff --name-only --diff-filter=A HEAD @{u}`).
- Both empty → `git -C <repo> pull --ff-only` (or step 3's diverged form) and move on.

### 2. Clear the way — only the overlapping paths

**Tracked overlap:**

```
git -C <repo> stash push -m "resolve-conflicts <repo> <yyyymmdd-hhmmss>" -- <overlap paths>
git -C <repo> stash list          # note the stash@{N} carrying that exact message
```

Never stash more than the overlap: every other local change stays in the tree untouched.

**Untracked collisions**, per file:

- Same bytes as upstream (`git -C <repo> hash-object <path>` equals
  `git -C <repo> rev-parse @{u}:<path>`) → delete the local copy; the pull recreates it.
- Different → copy it to `d:/datrix/.tmp/resolve-conflicts/<repo>/<path>`, then delete the
  local copy. Step 4 merges it back.

### 3. Pull

- **Ahead 0** → `git -C <repo> pull --ff-only`.
- **Ahead > 0 (diverged)** → `git -C <repo> pull --no-rebase --no-edit`. If the merge of
  committed history conflicts, resolve each conflicted file as in step 4 (read both sides,
  combine with Edit), `git add` it, and finish with `git -C <repo> commit --no-edit`.
  Never push — pushing is `/commit-and-push`.

If the pull still refuses, the overlap computed in step 1 was wrong: read the error text,
recompute, and repeat step 2 for the files it names.

### 4. Reapply and merge

```
git -C <repo> stash apply stash@{N}
```

Use `apply`, not `pop`: the entry stays as a safety copy until step 5 verifies the result.

- **Applies clean** → go to step 5.
- **Conflicts** → each conflicted file now carries `<<<<<<<`/`=======`/`>>>>>>>` markers.
  For each: read the incoming change (`git -C <repo> diff HEAD@{1} HEAD -- <path>`) and
  the local change (`git -C <repo> diff stash@{N}^1 stash@{N} -- <path>`), then write the
  result with **Edit** so it carries both intents. Pick a side wholesale
  (`checkout --ours/--theirs`) only when that side provably already contains the other's
  change. Then unstage: `git -C <repo> reset -q -- <path>`.
- **Untracked files set aside in step 2** → compare each saved copy with the pulled
  file and merge the local additions in with Edit.

A conflict whose two sides are both defensible and mutually exclusive (not "both
changes", but "one or the other") is a genuine B2: name both sides and your
recommendation to Jon in one line, and keep working the other repos meanwhile.

### 5. Verify, then drop

For every path that was stashed or set aside:

```
git -C <repo> grep -n -e "^<<<<<<< " -e "^>>>>>>> " -- <paths>    # must print nothing
git -C <repo> diff --check -- <paths>
git -C <repo> diff --stat -- <paths>                                # local edits present
```

Confirm each local hunk from `git -C <repo> stash show -p stash@{N}` is present in the
working tree (or deliberately merged with the incoming change). Only then:

```
git -C <repo> stash drop stash@{N}
```

Delete `d:/datrix/.tmp/resolve-conflicts/<repo>/` once its files are merged back.

Finally confirm `git -C <repo> rev-list --left-right --count HEAD...@{u}` reports
`behind 0`, and `git -C <repo> status --porcelain` lists the same local changes as step 1.

## Report

One line per repo: the new HEAD, which paths were shelved, and how each came back
(`clean` / `merged by hand: <what was combined>`). Repos that were already up to date get
one word. A dropped local change is a failure to report plainly, never a footnote.
