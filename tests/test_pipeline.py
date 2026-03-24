from pathlib import Path

from pdftomarkdown.config import AppConfig
from pdftomarkdown.models import DocumentIR, PageIR, PageStats, RepairResult
from pdftomarkdown.pipeline import ConversionPipeline


class FakeBackend:
    def __init__(self, name: str, pages: dict[int, str]) -> None:
        self.name = name
        self.pages = pages
        self.calls: list[list[int] | None] = []

    def extract(self, pdf_path: Path, *, page_numbers=None, page_stats=None) -> DocumentIR:
        self.calls.append(page_numbers)
        selected = page_numbers or sorted(self.pages)
        return DocumentIR(
            source_path=pdf_path,
            pages=[
                PageIR(
                    page_number=page_number,
                    markdown=self.pages.get(page_number, ""),
                    source_backend=self.name,
                )
                for page_number in selected
            ],
        )


class FakeRepairClient:
    def repair(self, page_image: bytes, candidate_markdown: str, page_context) -> RepairResult:
        return RepairResult(markdown="Fixed $x^2 + y^2 = z^2$", issue_tags=["gemini_repaired"], confidence=0.95)


def test_pipeline_uses_fallback_and_repair(monkeypatch, tmp_path: Path) -> None:
    input_pdf = tmp_path / "input.pdf"
    output_md = tmp_path / "output.md"
    input_pdf.write_bytes(b"%PDF-1.4")

    stats = [
        PageStats(
            page_number=1,
            text_char_count=100,
            word_count=20,
            image_count=0,
            drawing_count=0,
            math_density=0.2,
            born_digital=True,
            width=612,
            height=792,
        )
    ]
    monkeypatch.setattr("pdftomarkdown.pipeline.analyze_pdf", lambda _: stats)
    monkeypatch.setattr("pdftomarkdown.pipeline.render_page_png", lambda *_args, **_kwargs: b"png")

    config = AppConfig(
        input_path=input_pdf,
        output_path=output_md,
        emit_debug_report=True,
        gemini_api_key="test-key",
    )
    pipeline = ConversionPipeline(
        config,
        marker_backend=FakeBackend("marker", {1: "Bad math ???"}),
        mineru_backend=FakeBackend("mineru", {1: "Equation: $x^2 + y^2"}),
        repair_client=FakeRepairClient(),
    )

    document = pipeline.convert()
    pipeline.write_outputs(document)

    assert document.pages[0].source_backend == "mineru"
    assert document.pages[0].repair_applied is True
    assert "Fixed $x^2 + y^2 = z^2$" in output_md.read_text(encoding="utf-8")
    assert config.debug_report_path.exists()


def test_auto_mode_prefers_mineru_for_ocr_heavy_documents(monkeypatch, tmp_path: Path) -> None:
    input_pdf = tmp_path / "scan.pdf"
    output_md = tmp_path / "scan.md"
    input_pdf.write_bytes(b"%PDF-1.4")

    stats = [
        PageStats(
            page_number=1,
            text_char_count=0,
            word_count=0,
            image_count=4,
            drawing_count=2,
            math_density=0.01,
            born_digital=False,
            width=612,
            height=792,
        ),
        PageStats(
            page_number=2,
            text_char_count=10,
            word_count=3,
            image_count=3,
            drawing_count=1,
            math_density=0.02,
            born_digital=False,
            width=612,
            height=792,
        ),
    ]
    monkeypatch.setattr("pdftomarkdown.pipeline.analyze_pdf", lambda _: stats)

    marker_backend = FakeBackend("marker", {1: "marker page 1", 2: "marker page 2"})
    mineru_backend = FakeBackend("mineru", {1: "mineru page 1", 2: "mineru page 2"})
    config = AppConfig(input_path=input_pdf, output_path=output_md)
    pipeline = ConversionPipeline(
        config,
        marker_backend=marker_backend,
        mineru_backend=mineru_backend,
    )

    document = pipeline.convert()

    assert document.metadata["primary_backend"] == "mineru"
    assert mineru_backend.calls[0] is None
    assert marker_backend.calls == [[1, 2]]
