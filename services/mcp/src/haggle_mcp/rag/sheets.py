"""Parse model sheets (Markdown + YAML front matter) into retrievable chunks.

Chunking strategy: one chunk per "## " section. The sheets are written so each section is
self-contained (see db/sheets/_TEMPLATE.md), which is the simplest strategy that respects
meaning. Fixed-size windows would cut sentences and mix topics.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

FRONT_MATTER = re.compile(r"\A---\n(?P<meta>.*?)\n---\n(?P<body>.*)\Z", re.DOTALL)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
SECTION = re.compile(r"^## +(?P<title>.+)$", re.MULTILINE)


class SheetMeta(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    slug: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    make: str
    model: str
    years: str
    title: str
    version: int = Field(ge=1)
    sources: list[str] = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class Section:
    index: int
    title: str
    content: str

    @property
    def approx_tokens(self) -> int:
        return max(1, len(self.content) // 4)  # ~4 characters per token for English text


@dataclass(frozen=True, slots=True)
class Sheet:
    meta: SheetMeta
    body_md: str
    sections: tuple[Section, ...]


def parse_sheet(text: str) -> Sheet:
    match = FRONT_MATTER.match(text)
    if match is None:
        raise ValueError("sheet must start with a YAML front matter block delimited by ---")
    meta = SheetMeta.model_validate(yaml.safe_load(match["meta"]))
    body = HTML_COMMENT.sub("", match["body"]).strip()

    headings = list(SECTION.finditer(body))
    if not headings:
        raise ValueError(f"{meta.slug}: no '## ' sections found")
    sections = []
    for i, heading in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(body)
        content = body[heading.end() : end].strip()
        if content:
            sections.append(Section(index=i, title=heading["title"].strip(), content=content))
    return Sheet(meta=meta, body_md=body, sections=tuple(sections))


def load_sheets(directory: Path) -> list[Sheet]:
    """Every *.md in the directory except files starting with "_" (the template)."""
    return [
        parse_sheet(path.read_text(encoding="utf-8"))
        for path in sorted(directory.glob("*.md"))
        if not path.name.startswith("_")
    ]
