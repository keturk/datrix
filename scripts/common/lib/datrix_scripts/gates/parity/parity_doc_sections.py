"""Cut one gate's section out of a gate family's document, for ``parity_cases_cli accept`` of a proposal
that replaces the gate.

A gate is documented twice in its family folder, as a ``##`` section of ``quick-reference.md`` (how to run
it) and of ``README.md`` (what it does); both go when the gate goes. The cut is pure text work, so it
lives here, apart from the CLI module that pulls in the case-authoring packages.
"""

from __future__ import annotations

import re
from typing import Final

SECTION_RULE: Final[str] = "---"
_HEADING_PREFIX: Final[str] = "## "


class ToolError(ValueError):
    """A command is refused; nothing has been written."""


def without_section(text: str, heading: str, document: str) -> str:
    """*text* (a family's *document*) without the one section whose ``##`` line is *heading*.

    Raises:
        ToolError: The document has no section, or more than one, under that heading.
    """
    lines = text.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if line.rstrip() == heading]
    if len(starts) != 1:
        raise ToolError(f"the {document} holds {len(starts)} section(s) headed {heading}; exactly one is removed")
    start = starts[0]
    end = next((index for index in range(start + 1, len(lines)) if lines[index].startswith(_HEADING_PREFIX)), len(lines))
    if end < len(lines):
        # A later section follows: cut through the rule that separates this section from it.
        rule = next((index for index in range(end - 1, start, -1) if lines[index].strip() == SECTION_RULE), end - 1)
        kept = lines[:start] + lines[rule + 1 :]
    else:
        # The last section: cut from the rule that separates it from the one before.
        rule = next((index for index in range(start - 1, -1, -1) if lines[index].strip() == SECTION_RULE), start)
        kept = lines[:rule]
    return re.sub(r"\n{3,}", "\n\n", "".join(kept)).rstrip("\n") + "\n"
