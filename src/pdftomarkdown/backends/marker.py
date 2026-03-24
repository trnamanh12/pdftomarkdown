from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from pdftomarkdown.backends.base import BackendError, ExtractorBackend
from pdftomarkdown.models import DocumentIR, PageIR, PageStats
from pdftomarkdown.preflight import extract_page_pdf


class MarkerBackend(ExtractorBackend):
    name = "marker"

    def __init__(self, command: str = "marker_single") -> None:
        self.command = command

    def extract(
        self,
        pdf_path: Path,
        *,
        page_numbers: list[int] | None = None,
        page_stats: list[PageStats] | None = None,
    ) -> DocumentIR:
        self._ensure_command()
        if page_numbers:
            pages = [
                self._extract_single_page(pdf_path, page_number, page_stats)
                for page_number in page_numbers
            ]
            return DocumentIR(source_path=pdf_path, pages=pages, metadata={"backend": self.name})

        with tempfile.TemporaryDirectory(prefix="marker-") as temp_dir:
            output_dir = Path(temp_dir) / "out"
            output_dir.mkdir(parents=True, exist_ok=True)
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
            self._run(cmd)
            markdown_files = sorted(output_dir.rglob("*.md"))
            if not markdown_files:
                raise BackendError("Marker did not produce any markdown output.")

            pages: list[PageIR] = []
            for index, md_path in enumerate(markdown_files, start=1):
                stats = _lookup_stats(page_stats, index)
                pages.append(
                    PageIR(
                        page_number=index,
                        markdown=md_path.read_text(encoding="utf-8").strip(),
                        source_backend=self.name,
                        stats=stats,
                    )
                )
            return DocumentIR(source_path=pdf_path, pages=pages, metadata={"backend": self.name})

    def _extract_single_page(
        self,
        pdf_path: Path,
        page_number: int,
        page_stats: list[PageStats] | None,
    ) -> PageIR:
        with tempfile.TemporaryDirectory(prefix=f"marker-page-{page_number}-") as temp_dir:
            temp_path = Path(temp_dir)
            page_pdf = extract_page_pdf(pdf_path, page_number, temp_path / f"page-{page_number}.pdf")
            output_dir = temp_path / "out"
            output_dir.mkdir(parents=True, exist_ok=True)
            cmd = [
                self.command,
                str(page_pdf),
                "--output_dir",
                str(output_dir),
                "--output_format",
                "markdown",
                "--force_ocr",
                "--redo_inline_math",
            ]
            self._run(cmd)
            markdown_files = sorted(output_dir.rglob("*.md"))
            if not markdown_files:
                raise BackendError(f"Marker did not produce markdown for page {page_number}.")
            return PageIR(
                page_number=page_number,
                markdown=markdown_files[0].read_text(encoding="utf-8").strip(),
                source_backend=self.name,
                stats=_lookup_stats(page_stats, page_number),
            )

    def _ensure_command(self) -> None:
        import sys
        from pathlib import Path
        
        # Try to resolve in the current python executable directory (e.g. .venv/bin)
        bindir_command = Path(sys.executable).parent / self.command
        if bindir_command.is_file():
            self.command = str(bindir_command)
            return

        if shutil.which(self.command) is None:
            raise BackendError(
                f"Marker command '{self.command}' was not found. Install Marker and ensure the CLI is on PATH."
            )

    def _run(self, cmd: list[str]) -> None:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise BackendError(result.stderr.strip() or result.stdout.strip() or "Marker backend failed.")


def _lookup_stats(page_stats: list[PageStats] | None, page_number: int) -> PageStats | None:
    if not page_stats:
        return None
    for stats in page_stats:
        if stats.page_number == page_number:
            return stats
    return None
