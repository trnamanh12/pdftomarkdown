from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Sequence

from pdftomarkdown.backends.base import BackendError, ExtractorBackend
from pdftomarkdown.models import DocumentIR, PageIR, PageStats
from pdftomarkdown.preflight import get_page_count

MARKER_PAGE_SEPARATOR = "-" * 48
PAGINATION_MARKER_RE = re.compile(rf"\n\n\{{(\d+)\}}{re.escape(MARKER_PAGE_SEPARATOR)}\n\n")


class MarkerBackend(ExtractorBackend):
    name = "marker"

    def __init__(self, command: str = "marker_single", gpu_devices: tuple[int, ...] = ()) -> None:
        self.command = command
        self.gpu_devices = tuple(gpu_devices)

    def extract(
        self,
        pdf_path: Path,
        *,
        page_numbers: list[int] | None = None,
        page_stats: list[PageStats] | None = None,
    ) -> DocumentIR:
        self._ensure_command()
        selected_page_numbers = _normalize_page_numbers(page_numbers) or _all_page_numbers(pdf_path, page_stats)
        if not selected_page_numbers:
            return DocumentIR(source_path=pdf_path, pages=[], metadata={"backend": self.name})

        if len(self.gpu_devices) > 1 and len(selected_page_numbers) > 1:
            pages = self._extract_sharded(pdf_path, selected_page_numbers, page_stats)
        else:
            pages = self._extract_page_group(pdf_path, selected_page_numbers, page_stats)
        return DocumentIR(source_path=pdf_path, pages=pages, metadata={"backend": self.name})

    def _extract_sharded(
        self,
        pdf_path: Path,
        page_numbers: list[int],
        page_stats: list[PageStats] | None,
    ) -> list[PageIR]:
        page_groups = _split_page_numbers(page_numbers, len(self.gpu_devices))
        pages: list[PageIR] = []

        with ThreadPoolExecutor(max_workers=len(page_groups)) as executor:
            futures = {
                executor.submit(
                    self._extract_page_group,
                    pdf_path,
                    page_group,
                    page_stats,
                    device_number=device_number,
                ): tuple(page_group)
                for device_number, page_group in zip(self.gpu_devices, page_groups)
            }
            for future in as_completed(futures):
                pages.extend(future.result())
        return _ordered_pages(pages, page_numbers)

    def _extract_page_group(
        self,
        pdf_path: Path,
        page_numbers: list[int],
        page_stats: list[PageStats] | None,
        *,
        device_number: int | None = None,
    ) -> list[PageIR]:
        with tempfile.TemporaryDirectory(prefix="marker-") as temp_dir:
            output_dir = Path(temp_dir) / "out"
            output_dir.mkdir(parents=True, exist_ok=True)
            cmd = self._build_cmd(pdf_path, output_dir, page_numbers)
            self._run(cmd, env=self._build_env(device_number))
            return self._read_pages(output_dir, page_numbers, page_stats)

    def _build_cmd(self, pdf_path: Path, output_dir: Path, page_numbers: Sequence[int]) -> list[str]:
        cmd = [
            self.command,
            str(pdf_path),
            "--output_dir",
            str(output_dir),
            "--output_format",
            "markdown",
            "--paginate_output",
            "--force_ocr",
            "--redo_inline_math",
        ]
        if page_numbers:
            cmd.extend(["--page_range", _format_page_range(page_numbers)])
        return cmd

    def _build_env(self, device_number: int | None) -> dict[str, str] | None:
        if device_number is None:
            return None
        env = os.environ.copy()
        env["CUDA_VISIBLE_DEVICES"] = str(device_number)
        env["TORCH_DEVICE"] = "cuda"
        return env

    def _read_pages(
        self,
        output_dir: Path,
        expected_page_numbers: Sequence[int],
        page_stats: list[PageStats] | None,
    ) -> list[PageIR]:
        markdown_files = sorted(output_dir.rglob("*.md"))
        if not markdown_files:
            raise BackendError("Marker did not produce any markdown output.")
        if len(markdown_files) != 1:
            raise BackendError("Marker produced multiple markdown files for a single conversion.")

        markdown = markdown_files[0].read_text(encoding="utf-8")
        matches = list(PAGINATION_MARKER_RE.finditer(markdown))
        if not matches:
            if len(expected_page_numbers) == 1:
                page_number = expected_page_numbers[0]
                return [
                    PageIR(
                        page_number=page_number,
                        markdown=markdown.strip(),
                        source_backend=self.name,
                        stats=_lookup_stats(page_stats, page_number),
                    )
                ]
            raise BackendError("Marker output did not include page pagination markers.")

        pages: list[PageIR] = []
        for index, match in enumerate(matches):
            page_number = int(match.group(1)) + 1
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
            pages.append(
                PageIR(
                    page_number=page_number,
                    markdown=markdown[start:end].strip(),
                    source_backend=self.name,
                    stats=_lookup_stats(page_stats, page_number),
                )
            )
        return _ordered_pages(pages, expected_page_numbers)

    def _ensure_command(self) -> None:
        import sys

        bindir_command = Path(sys.executable).parent / self.command
        if bindir_command.is_file():
            self.command = str(bindir_command)
            return

        if shutil.which(self.command) is None:
            raise BackendError(
                f"Marker command '{self.command}' was not found. Install Marker and ensure the CLI is on PATH."
            )

    def _run(self, cmd: list[str], *, env: dict[str, str] | None = None) -> None:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)
        if result.returncode != 0:
            raise BackendError(result.stderr.strip() or result.stdout.strip() or "Marker backend failed.")


def _lookup_stats(page_stats: list[PageStats] | None, page_number: int) -> PageStats | None:
    if not page_stats:
        return None
    for stats in page_stats:
        if stats.page_number == page_number:
            return stats
    return None


def _all_page_numbers(pdf_path: Path, page_stats: list[PageStats] | None) -> list[int]:
    if page_stats:
        return [stats.page_number for stats in page_stats]
    return list(range(1, get_page_count(pdf_path) + 1))


def _format_page_range(page_numbers: Sequence[int]) -> str:
    zero_based_pages = sorted({page_number - 1 for page_number in page_numbers})
    ranges: list[str] = []
    start = zero_based_pages[0]
    end = zero_based_pages[0]

    for page_number in zero_based_pages[1:]:
        if page_number == end + 1:
            end = page_number
            continue
        ranges.append(f"{start}-{end}" if start != end else str(start))
        start = end = page_number
    ranges.append(f"{start}-{end}" if start != end else str(start))
    return ",".join(ranges)


def _normalize_page_numbers(page_numbers: Sequence[int] | None) -> list[int]:
    if not page_numbers:
        return []
    normalized = sorted(set(page_numbers))
    if normalized[0] <= 0:
        raise BackendError("Marker page numbers must be 1-based positive integers.")
    return normalized


def _ordered_pages(pages: Sequence[PageIR], expected_page_numbers: Sequence[int]) -> list[PageIR]:
    pages_by_number = {page.page_number: page for page in pages}
    expected = list(expected_page_numbers)
    expected_set = set(expected)
    missing = [page_number for page_number in expected if page_number not in pages_by_number]
    unexpected = sorted(page_number for page_number in pages_by_number if page_number not in expected_set)
    if missing or unexpected:
        problems: list[str] = []
        if missing:
            problems.append(f"missing pages {missing}")
        if unexpected:
            problems.append(f"unexpected pages {unexpected}")
        raise BackendError(f"Marker returned inconsistent page output: {', '.join(problems)}.")
    return [pages_by_number[page_number] for page_number in expected]


def _split_page_numbers(page_numbers: Sequence[int], chunk_count: int) -> list[list[int]]:
    if not page_numbers:
        return []
    chunk_count = max(1, min(chunk_count, len(page_numbers)))
    chunk_size, remainder = divmod(len(page_numbers), chunk_count)
    chunks: list[list[int]] = []
    start = 0
    for chunk_index in range(chunk_count):
        stop = start + chunk_size + (1 if chunk_index < remainder else 0)
        chunks.append(list(page_numbers[start:stop]))
        start = stop
    return [chunk for chunk in chunks if chunk]
