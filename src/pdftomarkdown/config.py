from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_GEMINI_MODEL = "gemini-flash-lite-latest"
DEFAULT_KAGGLE_INPUT_DIR = Path("/kaggle/input")
DEFAULT_KAGGLE_WORKING_DIR = Path("/kaggle/working")


def get_default_gemini_model() -> str:
    return os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)


def get_default_gemini_api_key() -> str | None:
    return os.getenv("GEMINI_API_KEY")


def parse_marker_gpus(value: str | list[int] | tuple[int, ...] | None) -> tuple[int, ...]:
    if value is None:
        return ()

    if isinstance(value, (list, tuple)):
        raw_items = list(value)
    else:
        stripped = value.strip()
        if not stripped:
            return ()
        raw_items = [item.strip() for item in stripped.split(",")]

    devices: list[int] = []
    for item in raw_items:
        try:
            device = int(item)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid Marker GPU index: {item!r}") from exc
        if device < 0:
            raise ValueError(f"Marker GPU indices must be non-negative: {item!r}")
        if device not in devices:
            devices.append(device)
    return tuple(devices)


def get_default_marker_gpus() -> tuple[int, ...]:
    return parse_marker_gpus(os.getenv("MARKER_GPUS"))


@dataclass(slots=True)
class Thresholds:
    fallback_score: float = 72.0
    repair_score: float = 82.0
    min_text_chars: int = 40
    high_math_density: float = 0.06
    max_line_fragmentation: float = 0.55


@dataclass(slots=True)
class AppConfig:
    input_path: Path
    output_path: Path
    backend: str = "auto"
    gemini_model: str = field(default_factory=get_default_gemini_model)
    gemini_api_key: str | None = field(default_factory=get_default_gemini_api_key)
    max_workers: int = 1
    disable_gemini_repair: bool = False
    emit_debug_report: bool = False
    marker_command: str = "marker_single"
    marker_gpus: tuple[int, ...] = field(default_factory=get_default_marker_gpus)
    mineru_command: str = "mineru"
    thresholds: Thresholds = field(default_factory=Thresholds)

    @property
    def debug_report_path(self) -> Path:
        return self.output_path.with_suffix(".debug.json")

    @property
    def gemini_enabled(self) -> bool:
        return bool(self.gemini_api_key) and not self.disable_gemini_repair
