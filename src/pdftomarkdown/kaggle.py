from __future__ import annotations

from pathlib import Path

from pdftomarkdown.config import (
    AppConfig,
    DEFAULT_KAGGLE_INPUT_DIR,
    DEFAULT_KAGGLE_WORKING_DIR,
    get_default_gemini_api_key,
    get_default_gemini_model,
)
from pdftomarkdown.pipeline import ConversionPipeline

KAGGLE_INPUT_DIR = DEFAULT_KAGGLE_INPUT_DIR
KAGGLE_WORKING_DIR = DEFAULT_KAGGLE_WORKING_DIR


def is_kaggle_environment(*, input_root: Path | None = None, working_root: Path | None = None) -> bool:
    resolved_input_root = input_root or KAGGLE_INPUT_DIR
    resolved_working_root = working_root or KAGGLE_WORKING_DIR
    return resolved_input_root.exists() and resolved_working_root.exists()


def resolve_input_path(input_pdf: str | Path, *, input_root: Path | None = None) -> Path:
    resolved_input_root = input_root or KAGGLE_INPUT_DIR
    input_path = Path(input_pdf).expanduser()
    if input_path.is_absolute() or input_path.exists():
        return input_path
    return resolved_input_root / input_path


def resolve_output_path(
    input_pdf: str | Path,
    output_path: str | Path | None = None,
    *,
    working_root: Path | None = None,
) -> Path:
    resolved_working_root = working_root or KAGGLE_WORKING_DIR
    if output_path is None:
        input_name = Path(input_pdf).name
        return resolved_working_root / f"{Path(input_name).stem}.md"

    resolved_output_path = Path(output_path).expanduser()
    if resolved_output_path.is_absolute():
        return resolved_output_path
    return resolved_working_root / resolved_output_path


def build_kaggle_config(
    input_pdf: str | Path,
    *,
    out: str | Path | None = None,
    backend: str = "auto",
    gemini_model: str | None = None,
    gemini_api_key: str | None = None,
    max_workers: int = 1,
    disable_gemini_repair: bool = False,
    emit_debug_report: bool = False,
    marker_command: str = "marker_single",
    mineru_command: str = "mineru",
    input_root: Path | None = None,
    working_root: Path | None = None,
) -> AppConfig:
    input_path = resolve_input_path(input_pdf, input_root=input_root)
    output_path = resolve_output_path(input_path, out, working_root=working_root)
    return AppConfig(
        input_path=input_path,
        output_path=output_path,
        backend=backend,
        gemini_model=gemini_model or get_default_gemini_model(),
        gemini_api_key=gemini_api_key or get_default_gemini_api_key(),
        max_workers=max(1, max_workers),
        disable_gemini_repair=disable_gemini_repair,
        emit_debug_report=emit_debug_report,
        marker_command=marker_command,
        mineru_command=mineru_command,
    )


def convert_pdf(
    input_pdf: str | Path,
    *,
    out: str | Path | None = None,
    backend: str = "auto",
    gemini_model: str | None = None,
    gemini_api_key: str | None = None,
    max_workers: int = 1,
    disable_gemini_repair: bool = False,
    emit_debug_report: bool = False,
    marker_command: str = "marker_single",
    mineru_command: str = "mineru",
    input_root: Path | None = None,
    working_root: Path | None = None,
) -> Path:
    config = build_kaggle_config(
        input_pdf,
        out=out,
        backend=backend,
        gemini_model=gemini_model,
        gemini_api_key=gemini_api_key,
        max_workers=max_workers,
        disable_gemini_repair=disable_gemini_repair,
        emit_debug_report=emit_debug_report,
        marker_command=marker_command,
        mineru_command=mineru_command,
        input_root=input_root,
        working_root=working_root,
    )
    pipeline = ConversionPipeline(config)
    document = pipeline.convert()
    pipeline.write_outputs(document)
    return config.output_path
