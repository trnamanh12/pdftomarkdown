from __future__ import annotations

import re

from pdftomarkdown.config import Thresholds
from pdftomarkdown.models import PageIR, PageStats, QualityAssessment

MALFORMED_LATEX_PATTERNS = (
    re.compile(r"\$\$[^\$]*$"),
    re.compile(r"(?<!\$)\$[^\$]*$"),
    re.compile(r"\\begin\{[^\}]+\}(?!.*\\end\{)"),
)


def assess_page(page: PageIR, stats: PageStats, thresholds: Thresholds) -> QualityAssessment:
    flags: list[str] = []
    score = 100.0
    markdown = page.markdown or ""
    stripped = markdown.strip()

    if not stripped:
        flags.append("empty_output")
        score -= 60

    if len(stripped) < thresholds.min_text_chars and stats.text_char_count >= thresholds.min_text_chars:
        flags.append("truncated_output")
        score -= 18

    replacement_chars = markdown.count("\ufffd")
    if "??" in markdown:
        replacement_chars += markdown.count("??")
    if replacement_chars:
        flags.append("replacement_characters")
        score -= min(18.0, replacement_chars * 4)

    if _has_malformed_latex(markdown):
        flags.append("malformed_latex")
        score -= 16

    fragmentation = _line_fragmentation(markdown)
    if fragmentation > thresholds.max_line_fragmentation:
        flags.append("fragmented_lines")
        score -= 12

    if stats.math_density >= thresholds.high_math_density and "$" not in markdown and "\\" not in markdown:
        flags.append("math_not_preserved")
        score -= 30

    if not stats.born_digital and not markdown.strip():
        flags.append("ocr_needed")
        score -= 10

    if stats.image_count > 2 and stats.text_char_count < thresholds.min_text_chars:
        flags.append("image_heavy_page")
        score -= 10

    score = max(score, 0.0)
    return QualityAssessment(
        score=score,
        flags=flags,
        needs_fallback=score < thresholds.fallback_score,
        needs_repair=score < thresholds.repair_score,
    )


def _has_malformed_latex(markdown: str) -> bool:
    if markdown.count("$$") % 2 != 0:
        return True
    inline_markers = markdown.count("$") - markdown.count("$$") * 2
    if inline_markers % 2 != 0:
        return True
    return any(pattern.search(markdown) for pattern in MALFORMED_LATEX_PATTERNS)


def _line_fragmentation(markdown: str) -> float:
    lines = [line for line in markdown.splitlines() if line.strip()]
    if not lines:
        return 1.0
    short_lines = sum(1 for line in lines if len(line.strip()) <= 40)
    return short_lines / len(lines)
