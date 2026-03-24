from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from pdftomarkdown.models import DocumentIR, PageStats


class BackendError(RuntimeError):
    """Raised when an external extraction backend fails."""


class ExtractorBackend(ABC):
    name: str

    @abstractmethod
    def extract(
        self,
        pdf_path: Path,
        *,
        page_numbers: list[int] | None = None,
        page_stats: list[PageStats] | None = None,
    ) -> DocumentIR:
        raise NotImplementedError
