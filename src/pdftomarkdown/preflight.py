from __future__ import annotations

from pathlib import Path

from pdftomarkdown.models import PageStats

MATH_CHARS = set("∑∫∞≈≠≤≥±÷√∂∇∈∉∩∪⊂⊆⊕⊗∧∨∀∃αβγδεζηθικλμνξοπρστυφχψω")


def analyze_pdf(pdf_path: Path) -> list[PageStats]:
    fitz = _require_fitz()
    stats: list[PageStats] = []
    with fitz.open(pdf_path) as doc:
        for zero_index, page in enumerate(doc):
            text = page.get_text("text")
            words = page.get_text("words")
            images = page.get_images(full=True)
            drawings = page.get_drawings()
            rect = page.rect
            math_density = _estimate_math_density(text)
            stats.append(
                PageStats(
                    page_number=zero_index + 1,
                    text_char_count=len(text.strip()),
                    word_count=len(words),
                    image_count=len(images),
                    drawing_count=len(drawings),
                    math_density=math_density,
                    born_digital=bool(text.strip()),
                    width=rect.width,
                    height=rect.height,
                )
            )
    return stats


def get_page_count(pdf_path: Path) -> int:
    fitz = _require_fitz()
    with fitz.open(pdf_path) as doc:
        return len(doc)


def render_page_png(pdf_path: Path, page_number: int, dpi: int = 220) -> bytes:
    fitz = _require_fitz()
    with fitz.open(pdf_path) as doc:
        page = doc.load_page(page_number - 1)
        matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        return pix.tobytes("png")


def extract_page_pdf(pdf_path: Path, page_number: int, out_path: Path) -> Path:
    fitz = _require_fitz()
    with fitz.open(pdf_path) as source:
        page_doc = fitz.open()
        page_doc.insert_pdf(source, from_page=page_number - 1, to_page=page_number - 1)
        page_doc.save(out_path)
        page_doc.close()
    return out_path


def _estimate_math_density(text: str) -> float:
    stripped = text.strip()
    if not stripped:
        return 0.0
    math_chars = sum(1 for char in stripped if char in MATH_CHARS)
    latex_tokens = stripped.count("\\") + stripped.count("$")
    return (math_chars + latex_tokens) / max(len(stripped), 1)


def _require_fitz():
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError(
            "PyMuPDF is not installed. Install project dependencies to analyze or render PDF pages."
        ) from exc
    return fitz
