from pathlib import Path

import pytest

from pdftomarkdown import cli
from pdftomarkdown import kaggle
from pdftomarkdown.models import DocumentIR, PageIR


class FakePipeline:
    def __init__(self, config) -> None:
        self.config = config

    def convert(self) -> DocumentIR:
        return DocumentIR(
            source_path=self.config.input_path,
            pages=[PageIR(page_number=1, markdown="# Title", source_backend="marker")],
        )

    def write_outputs(self, document: DocumentIR) -> None:
        self.config.output_path.write_text(document.to_markdown(), encoding="utf-8")


def test_cli_writes_output(monkeypatch, tmp_path: Path) -> None:
    input_pdf = tmp_path / "sample.pdf"
    output_md = tmp_path / "sample.md"
    input_pdf.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(cli, "ConversionPipeline", FakePipeline)

    exit_code = cli.main([str(input_pdf), "--out", str(output_md), "--disable-gemini-repair"])

    assert exit_code == 0
    assert output_md.read_text(encoding="utf-8") == "# Title"


def test_cli_defaults_to_kaggle_paths_when_running_in_kaggle(monkeypatch, tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    working_root = tmp_path / "working"
    input_pdf = input_root / "dataset" / "sample.pdf"
    input_pdf.parent.mkdir(parents=True, exist_ok=True)
    working_root.mkdir(parents=True, exist_ok=True)
    input_pdf.write_bytes(b"%PDF-1.4")

    monkeypatch.setattr(cli, "ConversionPipeline", FakePipeline)
    monkeypatch.setattr(kaggle, "KAGGLE_INPUT_DIR", input_root)
    monkeypatch.setattr(kaggle, "KAGGLE_WORKING_DIR", working_root)

    exit_code = cli.main(["dataset/sample.pdf"])

    assert exit_code == 0
    assert (working_root / "sample.md").read_text(encoding="utf-8") == "# Title"


def test_cli_requires_out_outside_kaggle(monkeypatch, tmp_path: Path) -> None:
    input_pdf = tmp_path / "sample.pdf"
    input_pdf.write_bytes(b"%PDF-1.4")

    monkeypatch.setattr(kaggle, "KAGGLE_INPUT_DIR", tmp_path / "missing-input")
    monkeypatch.setattr(kaggle, "KAGGLE_WORKING_DIR", tmp_path / "missing-working")

    with pytest.raises(SystemExit) as exc_info:
        cli.main([str(input_pdf)])

    assert exc_info.value.code == 2
