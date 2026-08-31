"""The adversarial harness for RT-09…RT-14 (INT-102).

Two modules, each holding the half of an attack that a deterministic assertion
cannot fabricate:

* :mod:`llm_evals.adversarial.hidden_pdf` — a real PDF whose payload is in the
  text layer and not on the page, and a reader that returns both projections
  so the asymmetry itself can be asserted.
* :mod:`llm_evals.adversarial.spoken_ids` — the two shapes an identifier takes
  once it has been said out loud, and the inverse that proves it is still
  fully recoverable from the transcript.

Neither is on any serving path, and neither calls a model.
"""

from __future__ import annotations

from llm_evals.adversarial.hidden_pdf import (
    HIDDEN_TEXT_EN,
    HiddenTechnique,
    PdfTextLayer,
    PdfTextLayerError,
    PdfTextLayerOcr,
    build_layered_pdf,
    read_pdf_text_layer,
)
from llm_evals.adversarial.spoken_ids import (
    DIGIT_GROUPING,
    digits_from_spoken,
    spaced_digit_groups,
    spoken_turkish_digits,
)

__all__ = [
    "DIGIT_GROUPING",
    "HIDDEN_TEXT_EN",
    "HiddenTechnique",
    "PdfTextLayer",
    "PdfTextLayerError",
    "PdfTextLayerOcr",
    "build_layered_pdf",
    "digits_from_spoken",
    "read_pdf_text_layer",
    "spaced_digit_groups",
    "spoken_turkish_digits",
]
