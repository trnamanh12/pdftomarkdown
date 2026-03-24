# `pdftomarkdown` Documentation

## 1. Project Overview
`pdftomarkdown` is a sophisticated Python-based CLI tool designed to convert complex, math-heavy PDF documents into clean, structured Markdown. It employs a multi-stage hybrid pipeline that combines deterministic extraction tools with AI-driven quality assessment and repair.

### Key Features
- **Hybrid Extraction**: Uses [Marker](https://github.com/VikParuchuri/marker) and [MinerU](https://github.com/opendatalab/MinerU) as primary backends.
- **Intelligent Fallback**: Automatically switches between extraction engines on a per-page basis if quality drops below a threshold.
- **AI-Powered Repair**: Integrates with the **Gemini API** to visually inspect broken pages (formulas, symbols, reading order) and perform repairs using multimodal vision.
- **Math-First Design**: Specifically optimized for LaTeX preservation in scientific and academic documents.
- **Quality Scoring**: A rule-based engine evaluates OCR quality, math density, and line fragmentation to drive pipeline decisions.

---

## 2. Architecture & Components

The project is structured into modular components, each with a specific responsibility:

| Component | Responsibility |
| :--- | :--- |
| cli.py | Entry point; handles argument parsing and initializes the app configuration. |
| pipeline.py | The core orchestrator that coordinates extraction, scoring, fallback, and repair stages. |
| scoring.py | Implements the heuristic engine that assigns quality scores (0-100) to extracted pages. |
| repair.py | Manages communication with the Gemini API for vision-based Markdown correction. |
| preflight.py | PDF introspection using PyMuPDF (fitz); handles rendering, page splitting, and metadata analysis. |
| models.py | Defines the Internal Representation (IR) data structures (`PageIR`, `DocumentIR`, `PageStats`). |
| config.py | Centralized configuration for thresholds, model selection, and backend commands. |
| `backends/` | Abstractions for external tools. base.py defines the interface, while marker.py and mineru.py implement it. |

---

## 3. The Conversion Pipeline

The `ConversionPipeline` follows a strict three-phase process to ensure the highest output quality:

### Phase 1: Pre-flight & Selection
1. **PDF Analysis**: preflight.py scans the PDF to determine page counts, text/math density, and whether the document is born-digital or scanned.
2. **Primary Backend**: Based on configuration or automatic detection, a primary extraction backend (usually Marker) is invoked for the whole document.

### Phase 2: Scoring & Fallback
1. **Assessment**: Every extracted page is passed to `assess_page()` in scoring.py. It looks for:
   - Malformed LaTeX (unmatched `$`).
   - Line fragmentation (too many short lines).
   - Expected vs. Actual math density.
   - Truncated text or empty output.
2. **Fallback Strategy**: If a page's score falls below the `fallback_score` (default: 72), the pipeline triggers the secondary backend (MinerU) for just that specific page. The version with the higher score is kept.

### Phase 3: AI Repair
1. **Visual Verification**: For pages that still fall below the `repair_score` (default: 82), the system renders the page to a PNG image.
2. **Gemini Invocation**: The image, along with the "broken" Markdown and surrounding page context, is sent to the Gemini API.
3. **Refinement**: The AI interprets the visual layout and returns a corrected Markdown version, which is then re-integrated into the final document.

---

## 4. Scoring Heuristics
The scoring engine in scoring.py uses a penalty-based system to evaluate quality:

- **Empty/OCR Failure**: -60 points.
- **Malformed LaTeX**: -16 points (e.g., unclosed `\begin{...}`).
- **Math Not Preserved**: -30 points (high math density in PDF but no math markers in Markdown).
- **Fragmented Lines**: -12 points (indicates poor flow/column detection).
- **Replacement Characters**: Penalty for `\ufffd` or generic `??` symbols.

---

## 5. Usage & Configuration

### Installation
The tool requires high-level dependencies for PDF processing:
- `PyMuPDF` (fitz)
- `google-genai` (for Gemini repair)
- External CLIs: `marker_single` and `mineru`.

### CLI Interface
```bash
pdf2md input.pdf --out output.md \
    --backend auto \
    --gemini-model gemini-2.0-flash \
    --max-workers 4 \
    --emit-debug-report
```

### Environment Variables
- `GEMINI_API_KEY`: Required for the repair stage.
- `GEMINI_MODEL`: (Optional) Override the default repair model.

---

## 6. Data Representation (Models)
The system uses a hierarchy of data models to track the state of the conversion:

- `PageStats`: Raw physical properties (images, drawings, math density).
- `PageIR`: The "Intermediate Representation" of a page, containing its Markdown content, source backend, and quality flags.
- `DocumentIR`: The complete document container used to generate the final output and debug reports.

---

## 7. Error Handling
- **Backend Errors**: If an external CLI fails, the pipeline catches `BackendError` and attempts to proceed with other pages or backends.
- **Graceful Degradation**: If the Gemini API is unavailable or keys are missing, the pipeline skips the repair stage and returns the best available extracted Markdown.