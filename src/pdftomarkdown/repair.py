from __future__ import annotations

import json
from dataclasses import dataclass

from pdftomarkdown.models import RepairResult


@dataclass(slots=True)
class PageContext:
    previous_heading: str | None = None
    next_heading: str | None = None


class GeminiRepairClient:
    def __init__(self, api_key: str, model: str) -> None:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError(
                "google-genai is not installed. Install project dependencies to enable Gemini repair."
            ) from exc

        self._genai = genai
        self._types = types
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def repair(self, page_image: bytes, candidate_markdown: str, page_context: PageContext) -> RepairResult:
        prompt = _build_prompt(candidate_markdown, page_context)
        response = self._client.models.generate_content(
            model=self._model,
            contents=[
                self._types.Part.from_bytes(data=page_image, mime_type="image/png"),
                prompt,
            ],
            config=self._types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        raw_text = getattr(response, "text", None)
        if not raw_text:
            raise RuntimeError("Gemini returned an empty response during repair.")

        parsed = json.loads(raw_text)
        return RepairResult(
            markdown=parsed.get("markdown", candidate_markdown).strip(),
            issue_tags=list(parsed.get("issue_tags", [])),
            confidence=float(parsed.get("confidence", 0.0)),
        )


def _build_prompt(candidate_markdown: str, page_context: PageContext) -> str:
    previous_heading = page_context.previous_heading or ""
    next_heading = page_context.next_heading or ""
    return f"""
You are repairing a single PDF page that was already converted to markdown.

Rules:
- Preserve only text actually visible in the page image.
- Do not summarize, expand, or invent content.
- Keep normal prose in Markdown.
- Represent inline math as $...$.
- Represent display math as $$...$$.
- Preserve equation numbering when visible.
- Prefer standard LaTeX commands for Greek letters, operators, fractions, matrices, superscripts, and subscripts.
- Return strict JSON with keys: markdown, issue_tags, confidence.

Previous heading context: {previous_heading}
Next heading context: {next_heading}

Candidate markdown:
```markdown
{candidate_markdown}
```
""".strip()
