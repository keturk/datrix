"""CLAUDE.md's skill lists must match the skills' actual `disable-model-invocation`.

THE INCIDENT: CLAUDE.md's read-when-needed table carried `| submit | /codegen-review |`,
but codegen-review is `disable-model-invocation: true`. So every agent that finished a
task dutifully tried to invoke it, got a hard tool error, and filed a false
`BLOCKED - B3 USER_FORBADE` on an otherwise complete piece of work. The instruction and
the harness disagreed, and the agent paid for it every single time.

This is a producer/consumer seam like any other: CLAUDE.md declares which skills an agent
may invoke, the skill frontmatter decides it. Nothing compared the two sets, so they
drifted. This file is that comparison, and it fails the moment either side moves --
including the quiet direction, where Jon flips a skill's frontmatter and the doc silently
starts lying in the other direction.

Run: python .claude/hooks/test-skill-invocability.py
"""
import os
import re
import sys

CLAUDE_MD = r"d:\datrix\.claude\CLAUDE.md"
SKILLS_DIR = r"d:\datrix\.claude\skills"

INVOCABLE_HEADING = "**You can invoke these:**"
JON_ONLY_HEADING = "**Jon types these — you cannot:**"

SKILL_REF_RE = re.compile(r"`/([a-z0-9-]+)(?:\{([a-z0-9,-]+)\})?`")
DISABLED_RE = re.compile(r"^disable-model-invocation:\s*true\s*$", re.MULTILINE)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}\n      got:  {sorted(got) if isinstance(got, set) else got!r}"
                     f"\n      want: {sorted(want) if isinstance(want, set) else want!r}")
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")


def skill_names_in(block):
    """`/fix-tests` -> {fix-tests}; `/fix-codegen-{aws,azure}` -> {fix-codegen-aws, ...}."""
    names = set()
    for stem, expansion in SKILL_REF_RE.findall(block):
        if expansion:
            names.update(f"{stem}{part}" for part in expansion.split(","))
        else:
            names.add(stem)
    return names


def paragraph_after(text, heading):
    """The heading and everything up to the next blank line followed by a new block."""
    start = text.find(heading)
    if start < 0:
        return ""
    end = text.find("\n\n", start)
    return text[start : end if end > 0 else len(text)]


def skill_file(name):
    """Skill dirs are inconsistent about SKILL.md vs skill.md — accept either."""
    for filename in ("SKILL.md", "skill.md"):
        path = os.path.join(SKILLS_DIR, name, filename)
        if os.path.isfile(path):
            return path
    return ""


def disabled_skills():
    """Every skill on disk whose frontmatter forbids model invocation."""
    found = set()
    for name in os.listdir(SKILLS_DIR):
        path = skill_file(name)
        if not path:
            continue
        with open(path, encoding="utf-8", errors="ignore") as handle:
            if DISABLED_RE.search(handle.read(4096)):
                found.add(name)
    return found


with open(CLAUDE_MD, encoding="utf-8") as handle:
    claude_md = handle.read()

declared_invocable = skill_names_in(paragraph_after(claude_md, INVOCABLE_HEADING))
declared_jon_only = skill_names_in(paragraph_after(claude_md, JON_ONLY_HEADING))
disabled = disabled_skills()

print("== the lists are present and non-vacuous ==")
check("CLAUDE.md declares an invocable list", bool(declared_invocable), True)
check("CLAUDE.md declares a Jon-only list", bool(declared_jon_only), True)
check("some skill on disk is actually disabled (the check can fail)", bool(disabled), True)

print("== THE INCIDENT: never tell an agent to invoke a disabled skill ==")
check("no disabled skill in the invocable list", declared_invocable & disabled, set())

print("== and never claim a skill is reserved when it is not ==")
check("every Jon-only entry is really disabled", declared_jon_only - disabled, set())

print("== the two lists agree with disk, in both directions ==")
check("no disabled skill is missing from the Jon-only list",
      disabled - declared_jon_only - declared_invocable, set())
check("the lists do not overlap", declared_invocable & declared_jon_only, set())

print("== every named skill exists ==")
for name in sorted(declared_invocable | declared_jon_only):
    if not skill_file(name):
        fails.append(f"CLAUDE.md names /{name}, which has no SKILL.md on disk")
print(f"  {'PASS' if not any('has no SKILL.md' in f for f in fails) else 'FAIL'}  "
      f"all {len(declared_invocable | declared_jon_only)} named skills exist")

print()
if fails:
    print(f"{len(fails)} FAILURE(S):")
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("all checks passed")
