"""Skill catalog: SKILL.md files under agents/skills/<name>/ (front matter: name, description).

Specs list the skills to preload; the body is injected into the system prompt with a content hash
recorded in the run manifest.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "skills"


@dataclass
class Skill:
    name: str
    description: str
    body: str
    sha: str


def _parse(path: Path) -> Skill:
    text = path.read_text(encoding="utf-8")
    meta, body = {}, text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.S)
    if m:
        body = m.group(2)
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
    name = meta.get("name") or path.parent.name
    return Skill(name=name, description=meta.get("description", ""), body=body.strip(),
                 sha=hashlib.sha256(text.encode("utf-8")).hexdigest()[:12])


class SkillCatalog:
    def __init__(self, root: Path = DEFAULT_ROOT):
        self.root = root
        self._cache: dict[str, Skill] | None = None

    def _all(self) -> dict[str, Skill]:
        if self._cache is None:
            self._cache = {}
            if self.root.exists():
                for path in sorted(self.root.glob("*/SKILL.md")):
                    skill = _parse(path)
                    self._cache[skill.name] = skill
        return self._cache

    def catalog(self) -> list[dict]:
        return [{"name": s.name, "description": s.description, "sha": s.sha} for s in self._all().values()]

    def load(self, names: tuple[str, ...] | list[str]) -> list[Skill]:
        skills = self._all()
        missing = [n for n in names if n not in skills]
        if missing:
            raise KeyError(f"skills not found: {missing}")
        return [skills[n] for n in names]
