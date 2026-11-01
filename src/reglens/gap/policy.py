"""Split a policy document (Markdown) into citable clauses: numbered paragraphs ("7.3 ...")
under their section headings, and annex table rows. The gap analysis cites clauses as "§7.3"."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Clause:
    id: str  # "§7.3" or "Annex 2"
    section: str  # "7. Data and definition of default"
    text: str

    def render(self) -> str:
        return f"[{self.id}] ({self.section}) {self.text}"


_HEADING = re.compile(r"^##\s+(.+)$")
_NUMBERED = re.compile(r"^(\d+\.\d+)\s+(.*)$")


def parse_policy(markdown: str) -> list[Clause]:
    clauses: list[Clause] = []
    section, current, annex_rows = "", None, 0
    for raw in markdown.splitlines():
        line = raw.strip()
        if m := _HEADING.match(line):
            section, current = m.group(1).strip(), None
            continue
        if section.lower().startswith("annex") and line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if set("".join(cells)) <= set("-: ") or cells[0] == "Parameter":
                continue  # separator or header row
            annex_rows += 1
            clauses.append(Clause(f"Annex {annex_rows}", section, " | ".join(cells)))
            continue
        if m := _NUMBERED.match(line):
            current = Clause(f"§{m.group(1)}", section, m.group(2).strip())
            clauses.append(current)
        elif line and current is not None and not line.startswith(("|", ">", "#")):
            current.text += " " + line  # continuation of a wrapped paragraph
        elif not line:
            current = None
    return clauses


def load_policy(path: Path) -> list[Clause]:
    return parse_policy(path.read_text(encoding="utf-8"))
