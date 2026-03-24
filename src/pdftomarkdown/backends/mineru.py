from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from pdftomarkdown.backends.base import BackendError, ExtractorBackend
from pdftomarkdown.models import DocumentIR, PageIR, PageStats
from pdftomarkdown.preflight import extract_page_pdf


class MinerUBackend(ExtractorBackend):
    name = "mineru"

    def __init__(self, command: str = "mineru") -> None:
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

        with tempfile.TemporaryDirectory(prefix="mineru-") as temp_dir:
            output_dir = Path(temp_dir) / "out"
            output_dir.mkdir(parents=True, exist_ok=True)
            cmd = [
                self.command,
                "-p",
                str(pdf_path),
                "-o",
                str(output_dir),
                "--output",
                "markdown",
            ]
            self._run(cmd)
            return self._collect_output(pdf_path, output_dir, page_stats)

    def _extract_single_page(
        self,
        pdf_path: Path,
        page_number: int,
        page_stats: list[PageStats] | None,
    ) -> PageIR:
        with tempfile.TemporaryDirectory(prefix=f"mineru-page-{page_number}-") as temp_dir:
            temp_path = Path(temp_dir)
            page_pdf = extract_page_pdf(pdf_path, page_number, temp_path / f"page-{page_number}.pdf")
            output_dir = temp_path / "out"
            output_dir.mkdir(parents=True, exist_ok=True)
            cmd = [
                self.command,
                "-p",
                str(page_pdf),
                "-o",
                str(output_dir),
                "--output",
                "markdown",
            ]
            self._run(cmd)
            doc = self._collect_output(pdf_path, output_dir, page_stats, forced_page_number=page_number)
            if not doc.pages:
                raise BackendError(f"MinerU did not produce markdown for page {page_number}.")
            return doc.pages[0]

    def _collect_output(
        self,
        pdf_path: Path,
        output_dir: Path,
        page_stats: list[PageStats] | None,
        forced_page_number: int | None = None,
    ) -> DocumentIR:
        markdown_files = sorted(output_dir.rglob("*.md"))
        if not markdown_files:
            raise BackendError("MinerU did not produce any markdown output.")

        pages: list[PageIR] = []
        for index, md_path in enumerate(markdown_files, start=1):
            page_number = forced_page_number or index
            stats = _lookup_stats(page_stats, page_number)
            pages.append(
                PageIR(
                    page_number=page_number,
                    markdown=md_path.read_text(encoding="utf-8").strip(),
                    source_backend=self.name,
                    stats=stats,
                )
            )
        return DocumentIR(source_path=pdf_path, pages=pages, metadata={"backend": self.name})

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
                f"MinerU command '{self.command}' was not found. Install MinerU and ensure the CLI is on PATH."
            )

    def _run(self, cmd: list[str]) -> None:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise BackendError(result.stderr.strip() or result.stdout.strip() or "MinerU backend failed.")


def _lookup_stats(page_stats: list[PageStats] | None, page_number: int) -> PageStats | None:
    if not page_stats:
        return None
    for stats in page_stats:
        if stats.page_number == page_number:
            return stats
    return None
