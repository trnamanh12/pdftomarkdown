# pdftomarkdown

`pdftomarkdown` is a Python CLI for converting math-heavy PDFs into Markdown with a hybrid pipeline:

- Marker as the primary Markdown extractor
- MinerU as a page-level fallback on damaged pages
- Gemini as an optional page-scoped repair pass for formulas, symbols, and reading order

By default, the highest-quality free path is fully open-source:

- `auto` mode picks Marker or MinerU as the primary extractor from PDF preflight
- OCR-heavy and math-heavy pages are cross-checked with the other open-source extractor
- Gemini is only used if you provide `GEMINI_API_KEY`

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

External backends are installed separately:

- Marker CLI: `marker_single` (requires `pip install marker-pdf`)
- MinerU CLI: `mineru` (requires `pip install magic-pdf[lite-cpu]` or similar)

If these commands are not in your PATH, you can specify their full paths using:

```bash
pdf2md input.pdf --out output.md --marker-command /path/to/marker_single --mineru-command /path/to/mineru
```

## Configuration

Set Gemini credentials when you want repair enabled:

```bash
export GEMINI_API_KEY=your-key
export GEMINI_MODEL=gemini-flash-lite-latest
```

Notebook runtimes often set secrets after Python has already started. `pdftomarkdown` reads `GEMINI_API_KEY` and `GEMINI_MODEL` when `AppConfig` is created, so setting them from a notebook cell works as expected.

To shard Marker across multiple GPUs, set `MARKER_GPUS` or pass `--marker-gpus`:

```bash
export MARKER_GPUS=0,1
```

## Usage

```bash
pdf2md input.pdf --out output.md
pdf2md input.pdf --out output.md --backend marker --disable-gemini-repair
pdf2md input.pdf --out output.md --emit-debug-report
pdf2md input.pdf --out output.md --backend marker --marker-gpus 0,1
```

Notes:

- `--marker-gpus 0,1` shards a single PDF into Marker page ranges and runs one `marker_single` process per GPU.
- This is different from Marker's own `marker_chunk_convert`, which is designed for folders of input files.

## Kaggle Notebook

Kaggle notebooks conventionally read attached datasets from `/kaggle/input` and write generated files to `/kaggle/working`. `pdftomarkdown` now includes a small Kaggle helper and a `--kaggle` CLI mode for that layout.

### 1) Install `pdftomarkdown` and the backends

Install the project in the notebook, then install the backend CLIs you plan to use:

```bash
%cd /kaggle/working/pdftomarkdown
!pip install -q -e .
!pip install -q marker-pdf
!pip install -q "magic-pdf[lite-cpu]"
```

Notes:

- Marker and MinerU are not available by default in Kaggle. Install both if you want full `--backend auto` behavior.
- If you only install one backend, pin it explicitly with `--backend marker` or `--backend mineru`.
- If a backend CLI is missing, `pdf2md` will raise a backend error rather than silently falling back to a non-installed tool.

### 2) Set the Gemini API key and model

Create Kaggle secrets named `GEMINI_API_KEY` and, optionally, `GEMINI_MODEL`. The project reads these from the environment when it builds the runtime config.

```python
import os
from kaggle_secrets import UserSecretsClient

os.environ["GEMINI_API_KEY"] = UserSecretsClient().get_secret("GEMINI_API_KEY")
os.environ["GEMINI_MODEL"] = UserSecretsClient().get_secret("GEMINI_MODEL") or "gemini-flash-lite-latest"
```

Recommended model defaults:

- `gemini-flash-lite-latest` for the cheapest fast repair pass
- `gemini-flash-latest` or another model if you want to trade cost for quality

If `GEMINI_API_KEY` is not set, Gemini repair stays disabled and the pipeline uses Marker/MinerU only.

### 3) Run the converter

CLI usage from a Kaggle notebook:

```bash
!pdf2md my-dataset/paper.pdf --kaggle --backend auto
!pdf2md my-dataset/paper.pdf --kaggle --backend marker --out results/paper.md
!pdf2md /kaggle/input/my-dataset/paper.pdf --kaggle --backend marker
!pdf2md /kaggle/input/my-dataset/paper.pdf --kaggle --backend marker --marker-gpus 0,1 --out results/paper.md
```

With `--kaggle`:

- Relative input PDFs are resolved under `/kaggle/input`.
- Relative output paths are written under `/kaggle/working`.
- Omitting `--out` writes `/kaggle/working/<input-stem>.md`.

Notebook helper usage:

```python
from pdftomarkdown.kaggle import convert_pdf

output_path = convert_pdf("my-dataset/paper.pdf", backend="marker")
print(output_path)
```

If your Kaggle runtime exposes two T4s, you can also use both explicitly from Python:

```python
from pdftomarkdown.kaggle import convert_pdf

output_path = convert_pdf("my-dataset/paper.pdf", backend="marker", marker_gpus=(0, 1))
print(output_path)
```

Tip: you can also pass `gemini_model="gemini-flash-lite-latest"` directly to `convert_pdf(...)` or `--gemini-model` on the CLI, but the environment variable is the most convenient for Kaggle notebooks.

## Notes

- The first version prioritizes text and formulas over image or table preservation.
- Extraction quality comes from Marker and MinerU. The project orchestrates and compares their outputs; it does not reimplement OCR or document layout parsing itself.
- Backends are invoked through their CLIs because that is the most stable public integration surface across versions.
