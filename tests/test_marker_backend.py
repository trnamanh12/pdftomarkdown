from pathlib import Path

from pdftomarkdown.backends.marker import MARKER_PAGE_SEPARATOR, MarkerBackend
from pdftomarkdown.models import PageStats


def test_marker_backend_parses_paginated_output(monkeypatch, tmp_path: Path) -> None:
    input_pdf = tmp_path / "paper.pdf"
    input_pdf.write_bytes(b"%PDF-1.4")

    backend = MarkerBackend(command="marker_single")
    monkeypatch.setattr(backend, "_ensure_command", lambda: None)

    observed_ranges: list[str] = []

    def fake_run(cmd: list[str], *, env=None) -> None:
        output_dir = Path(cmd[cmd.index("--output_dir") + 1])
        observed_ranges.append(cmd[cmd.index("--page_range") + 1])
        _write_marker_output(
            output_dir,
            input_pdf,
            {
                1: "# Page 1",
                2: "# Page 2",
            },
        )

    monkeypatch.setattr(backend, "_run", fake_run)

    document = backend.extract(input_pdf, page_stats=_page_stats(1, 2))

    assert observed_ranges == ["0-1"]
    assert [page.page_number for page in document.pages] == [1, 2]
    assert [page.markdown for page in document.pages] == ["# Page 1", "# Page 2"]
    assert [page.stats.page_number for page in document.pages if page.stats] == [1, 2]


def test_marker_backend_shards_across_multiple_gpus(monkeypatch, tmp_path: Path) -> None:
    input_pdf = tmp_path / "paper.pdf"
    input_pdf.write_bytes(b"%PDF-1.4")

    backend = MarkerBackend(command="marker_single", gpu_devices=(0, 1))
    monkeypatch.setattr(backend, "_ensure_command", lambda: None)

    observed_calls: list[tuple[str, str | None]] = []

    def fake_run(cmd: list[str], *, env=None) -> None:
        output_dir = Path(cmd[cmd.index("--output_dir") + 1])
        page_range = cmd[cmd.index("--page_range") + 1]
        observed_calls.append((page_range, None if env is None else env.get("CUDA_VISIBLE_DEVICES")))
        pages = {
            "0-1": {1: "# Page 1", 2: "# Page 2"},
            "2-3": {3: "# Page 3", 4: "# Page 4"},
        }[page_range]
        _write_marker_output(output_dir, input_pdf, pages)

    monkeypatch.setattr(backend, "_run", fake_run)

    document = backend.extract(input_pdf, page_stats=_page_stats(1, 2, 3, 4))

    assert [page.page_number for page in document.pages] == [1, 2, 3, 4]
    assert [page.markdown for page in document.pages] == ["# Page 1", "# Page 2", "# Page 3", "# Page 4"]
    assert sorted(observed_calls) == [("0-1", "0"), ("2-3", "1")]


def _page_stats(*page_numbers: int) -> list[PageStats]:
    return [
        PageStats(
            page_number=page_number,
            text_char_count=100,
            word_count=20,
            image_count=0,
            drawing_count=0,
            math_density=0.1,
            born_digital=True,
            width=612,
            height=792,
        )
        for page_number in page_numbers
    ]


def _write_marker_output(output_dir: Path, pdf_path: Path, pages: dict[int, str]) -> None:
    rendered_dir = output_dir / pdf_path.stem
    rendered_dir.mkdir(parents=True, exist_ok=True)
    chunks = [
        f"\n\n{{{page_number - 1}}}{MARKER_PAGE_SEPARATOR}\n\n{markdown}"
        for page_number, markdown in sorted(pages.items())
    ]
    (rendered_dir / f"{pdf_path.stem}.md").write_text("".join(chunks), encoding="utf-8")
