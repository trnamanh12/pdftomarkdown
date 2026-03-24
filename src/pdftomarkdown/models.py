from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class PageStats:
    page_number: int
    text_char_count: int
    word_count: int
    image_count: int
    drawing_count: int
    math_density: float
    born_digital: bool
    width: float
    height: float


@dataclass(slots=True)
class PageIR:
    page_number: int
    markdown: str
    source_backend: str
    stats: PageStats | None = None
    quality_score: float | None = None
    quality_flags: list[str] = field(default_factory=list)
    repair_applied: bool = False


@dataclass(slots=True)
class DocumentIR:
    source_path: Path
    pages: list[PageIR]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_markdown(self) -> str:
        chunks = [page.markdown.strip() for page in sorted(self.pages, key=lambda p: p.page_number)]
        return "\n\n".join(chunk for chunk in chunks if chunk)

    def to_debug_dict(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "metadata": self.metadata,
            "pages": [
                {
                    "page_number": page.page_number,
                    "source_backend": page.source_backend,
                    "quality_score": page.quality_score,
                    "quality_flags": page.quality_flags,
                    "repair_applied": page.repair_applied,
                    "stats": asdict(page.stats) if page.stats else None,
                }
                for page in sorted(self.pages, key=lambda p: p.page_number)
            ],
        }


@dataclass(slots=True)
class QualityAssessment:
    score: float
    flags: list[str]
    needs_fallback: bool
    needs_repair: bool


@dataclass(slots=True)
class RepairResult:
    markdown: str
    issue_tags: list[str]
    confidence: float
