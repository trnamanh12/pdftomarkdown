from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace

from pdftomarkdown.backends import BackendError, ExtractorBackend, MarkerBackend, MinerUBackend
from pdftomarkdown.config import AppConfig
from pdftomarkdown.models import DocumentIR, PageIR, RepairResult
from pdftomarkdown.preflight import analyze_pdf, render_page_png
from pdftomarkdown.repair import GeminiRepairClient, PageContext
from pdftomarkdown.scoring import assess_page


class ConversionPipeline:
    def __init__(
        self,
        config: AppConfig,
        *,
        marker_backend: ExtractorBackend | None = None,
        mineru_backend: ExtractorBackend | None = None,
        repair_client: GeminiRepairClient | None = None,
    ) -> None:
        self.config = config
        self.runtime_notes: list[str] = []
        self.marker_backend = marker_backend or MarkerBackend(
            command=config.marker_command,
            gpu_devices=config.marker_gpus,
        )
        self.mineru_backend = mineru_backend or MinerUBackend(command=config.mineru_command)
        self.repair_client = repair_client or (
            GeminiRepairClient(api_key=config.gemini_api_key, model=config.gemini_model)
            if config.gemini_enabled
            else None
        )

    def convert(self) -> DocumentIR:
        stats = analyze_pdf(self.config.input_path)
        primary = self._select_primary_backend(stats)
        self.runtime_notes.append(f"Primary backend selected: {primary.name}")
        try:
            document = primary.extract(self.config.input_path, page_stats=stats)
        except BackendError:
            if self.config.backend != "auto" or primary is self.mineru_backend:
                raise
            self.runtime_notes.append("Marker failed as primary backend; using MinerU for full-document extraction.")
            primary = self.mineru_backend
            document = self.mineru_backend.extract(self.config.input_path, page_stats=stats)

        pages_by_number = {page.page_number: page for page in document.pages}
        assessed = [
            self._assess_page(pages_by_number.get(stat.page_number), stat)
            for stat in stats
        ]
        pages = {page.page_number: page for page in assessed}
        cross_check_pages = self._candidate_pages_for_cross_check(pages, stats)

        if self.config.backend == "auto" and cross_check_pages:
            secondary = self._secondary_backend(primary)
            pages = self._apply_cross_check(pages, stats, cross_check_pages, secondary)

        if self.repair_client:
            pages = self._apply_repairs(pages, stats)

        final_document = DocumentIR(
            source_path=self.config.input_path,
            pages=sorted(pages.values(), key=lambda page: page.page_number),
            metadata={
                "backend_policy": self.config.backend,
                "primary_backend": primary.name,
                "gemini_model": self.config.gemini_model if self.repair_client else None,
                "page_count": len(stats),
                "runtime_notes": self.runtime_notes,
            },
        )
        return final_document

    def write_outputs(self, document: DocumentIR) -> None:
        self.config.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.output_path.write_text(document.to_markdown(), encoding="utf-8")
        if self.config.emit_debug_report:
            self.config.debug_report_path.write_text(
                json.dumps(document.to_debug_dict(), indent=2),
                encoding="utf-8",
            )

    def _select_primary_backend(self, stats) -> ExtractorBackend:
        if self.config.backend == "marker":
            return self.marker_backend
        if self.config.backend == "mineru":
            return self.mineru_backend
        ocr_heavy_pages = sum(1 for item in stats if _is_ocr_heavy(item, self.config))
        if stats and ocr_heavy_pages / len(stats) >= 0.4:
            self.runtime_notes.append("Auto mode chose MinerU primary because the document appears OCR-heavy.")
            return self.mineru_backend
        return self.marker_backend

    def _assess_page(self, page: PageIR | None, stats) -> PageIR:
        current = page or PageIR(page_number=stats.page_number, markdown="", source_backend="missing", stats=stats)
        assessment = assess_page(current, stats, self.config.thresholds)
        current.stats = stats
        current.quality_score = assessment.score
        current.quality_flags = assessment.flags
        return current

    def _apply_cross_check(
        self,
        pages: dict[int, PageIR],
        stats,
        candidate_pages: list[int],
        secondary_backend: ExtractorBackend,
    ) -> dict[int, PageIR]:
        try:
            comparison_results = secondary_backend.extract(
                self.config.input_path,
                page_numbers=candidate_pages,
                page_stats=stats,
            )
        except BackendError:
            self.runtime_notes.append(
                f"{secondary_backend.name} cross-check failed; keeping current output for candidate pages."
            )
            return pages
        comparison_by_number = {page.page_number: page for page in comparison_results.pages}
        for page_number in candidate_pages:
            alternative_page = comparison_by_number.get(page_number)
            if not alternative_page:
                continue
            assessed_alternative = self._assess_page(alternative_page, _stats_for_page(stats, page_number))
            current_page = pages[page_number]
            current_score = current_page.quality_score or 0.0
            if (assessed_alternative.quality_score or 0.0) > current_score:
                pages[page_number] = assessed_alternative
                self.runtime_notes.append(
                    f"Page {page_number} switched from {current_page.source_backend} to {secondary_backend.name}."
                )
        return pages

    def _apply_repairs(self, pages: dict[int, PageIR], stats) -> dict[int, PageIR]:
        repair_targets = [
            page.page_number
            for page in pages.values()
            if page.quality_score is not None and page.quality_score < self.config.thresholds.repair_score
        ]
        if not repair_targets:
            return pages

        max_workers = max(1, self.config.max_workers)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._repair_page, pages[page_number], stats): page_number
                for page_number in repair_targets
            }
            for future in as_completed(futures):
                page_number = futures[future]
                try:
                    repaired_page = future.result()
                except Exception:
                    continue
                pages[page_number] = repaired_page
        return pages

    def _repair_page(self, page: PageIR, stats) -> PageIR:
        if not self.repair_client:
            return page
        context = PageContext(
            previous_heading=_guess_heading(pages=stats, page_number=page.page_number - 1),
            next_heading=_guess_heading(pages=stats, page_number=page.page_number + 1),
        )
        page_image = render_page_png(self.config.input_path, page.page_number)
        repair = self.repair_client.repair(page_image, page.markdown, context)
        repaired = replace(
            page,
            markdown=repair.markdown,
            repair_applied=True,
            quality_flags=sorted(set(page.quality_flags + repair.issue_tags)),
        )
        reassessed = self._assess_page(repaired, _stats_for_page(stats, page.page_number))
        reassessed.repair_applied = True
        return reassessed

    def _candidate_pages_for_cross_check(self, pages: dict[int, PageIR], stats) -> list[int]:
        candidates: list[int] = []
        for stat in stats:
            page = pages[stat.page_number]
            low_score = (page.quality_score or 0.0) < self.config.thresholds.fallback_score
            if low_score or _should_cross_check(stat, self.config):
                candidates.append(stat.page_number)
        return candidates

    def _secondary_backend(self, primary_backend: ExtractorBackend) -> ExtractorBackend:
        if primary_backend is self.marker_backend:
            return self.mineru_backend
        return self.marker_backend


def _stats_for_page(stats, page_number: int):
    for item in stats:
        if item.page_number == page_number:
            return item
    raise ValueError(f"Unknown page number: {page_number}")


def _guess_heading(pages, page_number: int) -> str | None:
    for item in pages:
        if item.page_number == page_number:
            return f"Page {page_number}"
    return None


def _is_ocr_heavy(stats, config: AppConfig) -> bool:
    return (not stats.born_digital) or (
        stats.image_count > 2 and stats.text_char_count < config.thresholds.min_text_chars
    )


def _should_cross_check(stats, config: AppConfig) -> bool:
    return (
        _is_ocr_heavy(stats, config)
        or stats.math_density >= config.thresholds.high_math_density
        or stats.drawing_count > 20
    )
