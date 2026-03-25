"""Kaggle notebook example for pdftomarkdown with Gemini repair.

Copy this into a Kaggle notebook cell or run it as a script in the Kaggle
runtime after installing the project and the backend CLIs.

Expected Kaggle layout:
- inputs live under /kaggle/input
- outputs are written under /kaggle/working
"""

from __future__ import annotations

import os
from pathlib import Path

from kaggle_secrets import UserSecretsClient

from pdftomarkdown.kaggle import convert_pdf


# --- Gemini secrets -------------------------------------------------------
# In Kaggle, add secrets named GEMINI_API_KEY and GEMINI_MODEL.
# GEMINI_MODEL is optional; this example falls back to the project's default.
os.environ["GEMINI_API_KEY"] = UserSecretsClient().get_secret("GEMINI_API_KEY")
os.environ["GEMINI_MODEL"] = (
    UserSecretsClient().get_secret("GEMINI_MODEL") or "gemini-flash-lite-latest"
)


# --- PDF conversion -------------------------------------------------------
# Relative paths are resolved under /kaggle/input when using the Kaggle helper.
# Outputs default to /kaggle/working/<input-stem>.md when `out=None`.
input_pdf = "my-dataset/paper.pdf"
output_path = convert_pdf(
    input_pdf,
    backend="marker",
    out=Path("results/paper.md"),
)

print(f"Wrote markdown to: {output_path}")
