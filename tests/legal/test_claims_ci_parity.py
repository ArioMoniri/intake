"""INT-536 F3 — the render-time claims scanner flags everything the CI gate flags.

Invariant 20 has two enforcers:
- ``scripts/ci/claims_scan.sh``, which CI runs over the committed trees;
- :mod:`intake_platform.legal.claims`, which refuses a legal text when it
  renders (``legal.document_index``, ``legal.synthetic``) and a store listing
  when it loads.

INT-529 found the second one weaker. Its Turkish arm was ``\\bdoğruluk``, so
the softened form in "doğruluğu yüzde 99" passed at render time, while the
shell gate caught it.

The render-time set now carries the shell gate's strict-tier expressions
verbatim. This suite holds that in two ways:
- **Text.** Each ``CI_*`` constant equals its variable in the shell script, so
  an edit to one without the other fails here.
- **Behaviour.** For a corpus of claims and near misses, every line the shell
  gate flags at its strict tier, the render-time scanner flags too.

It also pins the near misses that both gates let through, because they are
ordinary Turkish or legal prose. The render-time scanner's bare
``doğruluk`` / ``duyarlılık`` / ``özgüllük`` arms are stricter than CI and
stay as they were: gates only go up.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from intake_platform.legal import claims

REPO = Path(__file__).resolve().parents[2]
SHELL_GATE = REPO / "scripts" / "ci" / "claims_scan.sh"
PERFORMANCE = ("performance",)

#: shell variable -> the render-time constant that must equal it, verbatim
_MIRRORED = {
    "ALWAYS_PAT": claims.CI_ALWAYS_PAT,
    "TERM_EN": claims.CI_TERM_EN,
    "TERM_TR": claims.CI_TERM_TR,
    "FIG": claims.CI_FIG,
    "NEAR": claims.CI_NEAR,
}

#: Lines the CI gate flags at its strict tier. Each one must be flagged at
#: render time too.
CLAIMS = (
    "Konuşmayı tanımanın doğruluğu yüzde 99'dur.",
    "Doğruluğu %97 olarak ölçüldü.",
    "Sistemin duyarlılığı %95, özgüllüğü %90.",
    "Kesinliği 0,93 olan bir model.",
    "İsabet oranı %88.",
    "%92 doğrulukla yazıya döker.",
    "Our transcription accuracy is high.",
    "Triyaj hassasiyeti (sensitivity) yüksektir.",
    "High specificity for chest pain.",
    "WER 8.0 on Turkish speech.",
    "AUC 0.91 on the held-out set.",
    "Measured by f1_score on the corpus.",
    "The model's AUROC is reported in the annex.",
)

#: Ordinary prose that neither gate may flag.
NEAR_MISSES = (
    "Bilgilerinizin doğruluğundan siz sorumlusunuz.",
    "Kişisel verilerin doğru ve gerektiğinde güncel olması gerekir.",
    "Bu bilgileri kesinlikle kimseyle paylaşmayınız.",
    "İsabetli bir soru sorduk.",
    "Kültürel duyarlılığa özen gösteririz.",
    "Görüşme yüzde yüz gönüllüdür.",
    "Yanıtlarınız 30 gün sonra silinir.",
    "Answer every question in your own words.",
)


def _shell_variable(name: str) -> str:
    match = re.search(rf"^{name}='([^']*)'$", SHELL_GATE.read_text(encoding="utf-8"), re.M)
    assert match is not None, f"{name} is no longer a single-quoted line in {SHELL_GATE}"
    return match.group(1)


def _shell_flags(tmp_path: Path, line: str) -> bool:
    bash = shutil.which("bash")
    assert bash is not None
    probe = tmp_path / "probe.md"
    probe.write_text(line + "\n", encoding="utf-8")
    result = subprocess.run(
        [bash, str(SHELL_GATE), "--strict", str(probe)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in (0, 1), result.stderr
    return result.returncode == 1


@pytest.mark.parametrize("name", sorted(_MIRRORED))
def test_each_render_time_expression_is_the_ci_gate_s_own(name: str) -> None:
    assert _MIRRORED[name] == _shell_variable(name)


@pytest.mark.parametrize("line", CLAIMS)
def test_every_ci_claim_is_caught_at_render_time(tmp_path: Path, line: str) -> None:
    assert _shell_flags(tmp_path, line), "the corpus line no longer trips the CI gate"
    assert claims.scan_text(line, groups=PERFORMANCE)


@pytest.mark.parametrize("line", NEAR_MISSES)
def test_ordinary_prose_passes_both_gates(tmp_path: Path, line: str) -> None:
    assert not _shell_flags(tmp_path, line)
    assert claims.scan_text(line, groups=PERFORMANCE) == ()


def test_the_int529_case_is_caught() -> None:
    """The finding itself: the softened form beside a figure."""
    hits = claims.scan_text("doğruluğu yüzde 99", groups=PERFORMANCE)
    assert {hit.pattern for hit in hits} == {"ci_claim_tr"}
