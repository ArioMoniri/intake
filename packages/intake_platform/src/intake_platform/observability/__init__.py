"""INT-175 — the LLM-observability boundary: trace emission, annotation queues
and the recorded-experiment gate.

Nothing is re-exported here on purpose. ``from intake_platform.observability
import *`` would make it easy to reach the emission boundary without reading
:mod:`intake_platform.observability.spans`'s docstring, and that docstring is
the control (HB-L6). Import the submodule you mean.
"""

from __future__ import annotations
