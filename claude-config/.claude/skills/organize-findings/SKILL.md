---
model: claude-sonnet-5-5
effort: low
description: Sort the findings files lying loose in d:\datrix\findings into one level of area subfolders (python, typescript, clients, language, schema, seed, kernel, docker, aws, azure, component, tests, tooling, docs) by running the organize-findings script. The area comes from the file name; a local model picks it for a name that states none. Moves files only — merges, renames and deletes nothing. Use when Jon asks to "organize findings", "sort the findings into folders", "file the new findings by area", or runs /organize-findings.
---

# Organize Findings

Agents write findings into `d:\datrix\findings\` as loose files. `finding-select`,
`finding-close`, `implement-finding.ps1` and the other findings skills work the area subfolders
(`python`, `azure`, …) in turn, so a loose file is not picked up in its area's turn. This skill runs
`organize-findings.ps1`, which moves each loose `*.md` into `findings\<area>\`.

This skill only moves findings files. It reads no file's content to sort it, merges nothing, renames
nothing, deletes nothing, fixes no code, files no tasks, and dispatches no subagents.

## How to invoke

```
/organize-findings
```

## Phase 1 — Run the script

```bash
powershell -File "d:/datrix/datrix/scripts/skill/organize-findings.ps1"
```

Only `*.md` files directly in the folder move. Nothing inside a subfolder is touched, and no subfolder
is ever created inside another. The area of a file comes from its name:

1. a merged name `NNNN-<area>-<slug>.md` carries its area;
2. any other name is read by the first word of its slug when that word is an area or one of its aliases
   (`azure-...`, `ts-...`, `gate-...`);
3. a name that states no area is sent, by name only, to a local model that picks one of the areas. A name
   carrying a registered customer term is not sent. `-NoModel` sends nothing.

A move never overwrites: when `<area>\<same name>` exists, the file stays and the run fails.

Use `-DryRun` to print the moves without making them. `-Dir "<folder>"` sorts another folder.

## Phase 2 — Read the exit code

| Exit | Meaning | What you do |
|---|---|---|
| 0 | every loose file is sorted | Report. |
| 1 | the folder cannot be read, or a move failed (usually a name already in the target area) | Read the printed error. A name clash means the same file is already filed: compare the two and tell Jon, never overwrite. Fix a cause that is yours (path, permissions) and run again. |
| 2 | some files stayed (a name withheld for a customer term, or no valid model answer for it) | Phase 3. |
| 3 | a local model was needed and none answered | Run again later, or run `-NoModel` for the names that state their area and go to Phase 3 for the rest. |

When several apply, 1 wins over 3 and 3 over 2.

## Phase 3 — Files that stayed

List what is still loose:

```powershell
Get-ChildItem d:\datrix\findings -File -Filter *.md | Sort-Object Name
```

For each, read the file and pick its area by the rule `/merge-findings` uses: **the subject the finding
is about, never the package its fix lands in and never a group of subjects.** Areas, in order: `python`
(specific to the Python generator), `typescript` (specific to the TypeScript generator and its core),
`clients` (Angular, Flutter), `language` (parser, semantic analysis, DSL), `schema` (RDBMS snapshots, differ, change policy, schema converge), `seed`, `kernel`
(shared generation machinery), `docker`, `aws`, `azure`, `component`, `tests`, `tooling` (scripts,
gates, skills), `docs`. There is no catch-all area and none is added.

Move it with `Move-Item` into the existing `findings\<area>\` folder; refuse the move if the target name
exists. A file withheld for a customer term is read like any other, but its reply line names the file
by its stem and leaves the term out.

## Report to Jon

Short: files moved per area (counts), files that stayed and where you filed them, the exit code.
