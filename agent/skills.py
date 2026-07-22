"""Loads SKILL.md files (Claude-Code-style Agent Skills) from a skills directory."""

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class Skill:
    name: str
    description: str
    body: str
    path: Path


def load_skill_catalog(skills_dir: Path) -> dict[str, Skill]:
    catalog: dict[str, Skill] = {}
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        text = skill_md.read_text()
        if not text.startswith("---"):
            continue
        _, frontmatter, body = text.split("---", 2)
        meta = yaml.safe_load(frontmatter) or {}
        name = meta.get("name")
        if not name:
            continue
        catalog[name] = Skill(
            name=name,
            description=meta.get("description", ""),
            body=body.strip(),
            path=skill_md,
        )
    return catalog


def catalog_summary(catalog: dict[str, Skill]) -> str:
    lines = []
    for skill in catalog.values():
        first_sentence = skill.description.split(". ")[0].rstrip(".")
        lines.append(f"- {skill.name}: {first_sentence}")
    return "\n".join(lines)
