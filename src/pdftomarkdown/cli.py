from __future__ import annotations

import argparse
from pathlib import Path

from pdftomarkdown import kaggle
from pdftomarkdown.config import AppConfig, get_default_gemini_model
from pdftomarkdown.pipeline import ConversionPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert math-heavy PDFs into markdown.")
    parser.add_argument("input_pdf", type=Path, help="Path to the input PDF file.")
    parser.add_argument(
        "--out",
        type=Path,
        help="Path to the output markdown file. Required unless Kaggle mode is active.",
    )
    parser.add_argument(
        "--kaggle",
        action="store_true",
        help="Resolve relative input paths under /kaggle/input and relative outputs under /kaggle/working.",
    )
    parser.add_argument(
        "--backend",
        default="marker",
        choices=("auto", "marker", "mineru"),
        help="Extraction backend policy.",
    )
    parser.add_argument(
        "--gemini-model",
        default=get_default_gemini_model(),
        help="Gemini model name. Defaults to GEMINI_MODEL or gemini-flash-lite-latest.",
    )
    parser.add_argument("--max-workers", default=1, type=int, help="Max workers for page-scoped repair.")
    parser.add_argument(
        "--disable-gemini-repair",
        action="store_true",
        help="Skip Gemini repair even when GEMINI_API_KEY is present.",
    )
    parser.add_argument(
        "--emit-debug-report",
        action="store_true",
        help="Write a JSON sidecar with per-page backend and quality metadata.",
    )
    parser.add_argument(
        "--marker-command",
        default="marker_single",
        help="Command or absolute path to the Marker CLI. Defaults to 'marker_single'.",
    )
    parser.add_argument(
        "--mineru-command",
        default="mineru",
        help="Command or absolute path to the MinerU CLI. Defaults to 'mineru'.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    kaggle_mode = args.kaggle or (args.out is None and kaggle.is_kaggle_environment())

    if kaggle_mode:
        config = kaggle.build_kaggle_config(
            args.input_pdf,
            out=args.out,
            backend=args.backend,
            gemini_model=args.gemini_model,
            max_workers=max(1, args.max_workers),
            disable_gemini_repair=args.disable_gemini_repair,
            emit_debug_report=args.emit_debug_report,
            marker_command=args.marker_command,
            mineru_command=args.mineru_command,
        )
    else:
        if args.out is None:
            parser.error("the following arguments are required: --out")

        config = AppConfig(
            input_path=args.input_pdf,
            output_path=args.out,
            backend=args.backend,
            gemini_model=args.gemini_model or get_default_gemini_model(),
            max_workers=max(1, args.max_workers),
            disable_gemini_repair=args.disable_gemini_repair,
            emit_debug_report=args.emit_debug_report,
            marker_command=args.marker_command,
            mineru_command=args.mineru_command,
        )
    pipeline = ConversionPipeline(config)
    document = pipeline.convert()
    pipeline.write_outputs(document)
    return 0
