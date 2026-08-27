"""INT-015 — the NER tier: names and addresses (KVKK-9/16).

The model is our own fine-tune (base MIT via raw blob; data CC-BY-4.0
synthetic; provenance.json + SHA256SUMS inside the artefact) fetched by
`make deid-model` into .cache/deid-tr-ner-v1 (or INTAKE_DEID_MODEL_DIR).
These tests REQUIRE it — a missing model fails with the fetch instruction
rather than skipping, because a silently green suite without the names tier
is exactly the false comfort the egress contract exists to prevent.

Gate corpus: the vendored 400-row held-out sample (see ATTRIBUTION.md) —
machine-generated synthetic, no real persons. The measured recalls are
recorded in docs/evidence/INT-015.md as dated internal measurements (D16).
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from intake_platform.deid import Deidentifier

REPO = Path(__file__).resolve().parents[2]
SAMPLE = REPO / "tests" / "fixtures" / "deid" / "vendor" / "btx24_test_sample400.jsonl"

_FETCH_HINT = (
    "NER model missing — run `make deid-model` (downloads the pinned "
    "deid-tr-ner-v1 release artefact) or set INTAKE_DEID_MODEL_DIR"
)


def _model_dir() -> Path:
    env = os.environ.get("INTAKE_DEID_MODEL_DIR")
    path = Path(env) if env else REPO / ".cache" / "deid-tr-ner-v1"
    assert (path / "config.json").is_file(), _FETCH_HINT
    return path


@lru_cache(maxsize=1)
def _engine() -> Deidentifier:
    return Deidentifier(ner_model_dir=_model_dir(), subject_key="ner-test-subject")


def test_model_artefact_carries_provenance_and_sums() -> None:
    model_dir = _model_dir()
    provenance = json.loads((model_dir / "provenance.json").read_text(encoding="utf-8"))
    assert provenance["base_model"] == "dbmdz/distilbert-base-turkish-cased"
    assert "CC-BY-4.0" in provenance["dataset_licence"]
    assert (model_dir / "SHA256SUMS").is_file()


def test_egress_no_longer_fails_closed() -> None:
    masked = _engine().deidentify_for_egress("Hasta Ayşe Yılmaz bugün geldi.")
    assert "Ayşe" not in masked
    assert "[PERSON]" in masked


def test_person_and_address_leak_gate_on_heldout_sample() -> None:
    engine = _engine()
    counts = {"private_person": [0, 0], "private_address": [0, 0]}  # [caught, total]
    for line in SAMPLE.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        spans = [e for e in (row.get("label") or []) if e["category"] in counts]
        if not spans:
            continue
        masked = engine.deidentify(row["text"])
        for span in spans:
            value = row["text"][span["start"] : span["end"]]
            counts[span["category"]][1] += 1
            if value not in masked:
                counts[span["category"]][0] += 1
    for category, (caught, total) in counts.items():
        assert total >= 30, f"sample lost its {category} cases ({total})"
        recall = caught / total
        # The held-out gate: on machine-generated synthetic text the tier must
        # be near-perfect; degradation here means the artefact regressed.
        assert recall >= 0.97, f"{category}: recall {recall:.3f} ({caught}/{total}) under the gate"


def test_pattern_tier_still_owns_deterministic_classes() -> None:
    masked = _engine().deidentify("Ali Veli, TCKN 72096654290, 05321114455.")
    assert "[TCKN]" in masked and "[PHONE]" in masked and "[PERSON]" in masked
