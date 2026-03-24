from pathlib import Path

from pdftomarkdown.config import AppConfig
from pdftomarkdown.kaggle import build_kaggle_config
from pdftomarkdown.models import DocumentIR, PageIR
from pdftomarkdown.pipeline import ConversionPipeline


def test_build_kaggle_config_resolves_input_and_output_paths(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    working_root = tmp_path / "working"
    input_pdf = input_root / "dataset" / "paper.pdf"
    input_pdf.parent.mkdir(parents=True, exist_ok=True)
    input_pdf.write_bytes(b"%PDF-1.4")

    config = build_kaggle_config(
        "dataset/paper.pdf",
        out="results/paper.md",
        input_root=input_root,
        working_root=working_root,
    )

    assert config.input_path == input_pdf
    assert config.output_path == working_root / "results" / "paper.md"


def test_app_config_reads_gemini_env_at_instantiation(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "kaggle-secret")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-kaggle-test")

    config = AppConfig(
        input_path=tmp_path / "paper.pdf",
        output_path=tmp_path / "paper.md",
    )

    assert config.gemini_api_key == "kaggle-secret"
    assert config.gemini_model == "gemini-kaggle-test"


def test_pipeline_write_outputs_creates_missing_parent_directories(tmp_path: Path) -> None:
    output_path = tmp_path / "nested" / "results" / "paper.md"
    config = AppConfig(
        input_path=tmp_path / "paper.pdf",
        output_path=output_path,
    )
    pipeline = ConversionPipeline(config)
    document = DocumentIR(
        source_path=config.input_path,
        pages=[PageIR(page_number=1, markdown="# Title", source_backend="marker")],
    )

    pipeline.write_outputs(document)

    assert output_path.read_text(encoding="utf-8") == "# Title"
