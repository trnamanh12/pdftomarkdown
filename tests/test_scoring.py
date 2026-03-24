from pdftomarkdown.config import Thresholds
from pdftomarkdown.models import PageIR, PageStats
from pdftomarkdown.scoring import assess_page


def test_assess_page_flags_broken_math() -> None:
    stats = PageStats(
        page_number=1,
        text_char_count=200,
        word_count=40,
        image_count=0,
        drawing_count=0,
        math_density=0.2,
        born_digital=True,
        width=612,
        height=792,
    )
    page = PageIR(page_number=1, markdown="Equation: $x^2 + y^2", source_backend="marker")
    assessment = assess_page(page, stats, Thresholds())

    assert assessment.score < 82
    assert "malformed_latex" in assessment.flags
