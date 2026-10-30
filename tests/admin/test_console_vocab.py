"""INT-565 — the console's copies of other services' closed sets, held to their owners.

``intake_platform.admin.console_vocab`` lets the API render PolicyGuard's
violation classes, Loop 2's proposal targets and evidence checks, and the
audit verifier's outcomes without importing the voice runtime, the learning
pipeline or the verifier. That is only safe while each copy equals its owner,
so this suite imports the owners — the test lane may — and fails the moment
one moves. The second half holds the boundary itself: the API's import
closure reaches none of the three.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from intake_learning.evidence import REQUIRED_CHECKS
from intake_learning.proposals import PROPOSAL_TARGETS
from intake_platform.admin.console_vocab import (
    AUDIT_VERIFIER_OUTCOMES,
    EVIDENCE_CHECK_NAMES,
    POLICYGUARD_CLASSES,
    PROPOSAL_TARGET_NAMES,
)
from intake_platform.audit_verifier.job import VerifierOutcome
from intake_voice_runtime.talker.policy_guard import ViolationClass

REPO = Path(__file__).resolve().parents[2]

#: What the API process must never load: the Talker and the learning
#: pipeline (no dependency edge exists, and none should), and the verifier,
#: whose import registers ``sec_audit_chain_ok`` at 0 in the importing process.
FORBIDDEN = ("intake_voice_runtime", "intake_learning", "intake_platform.audit_verifier")

_PROBE = (
    "import sys\n"
    "import intake_api.app, intake_api.admin.routes\n"
    "import intake_api.admin.protocols_console, intake_api.admin.quality_safety_console\n"
    "import intake_api.admin.security_console, intake_api.admin.cost_console\n"
    f"print('\\n'.join(sorted(m for m in sys.modules if m.startswith({FORBIDDEN!r}))))\n"
)


class TestEachCopyEqualsItsOwner:
    def test_policyguard_classes_are_the_violation_class_enum(self) -> None:
        assert tuple(cls.value for cls in ViolationClass) == POLICYGUARD_CLASSES

    def test_proposal_targets_are_loop_2s_vocabulary(self) -> None:
        assert tuple(target.__name__ for target in PROPOSAL_TARGETS) == PROPOSAL_TARGET_NAMES

    def test_evidence_checks_are_the_required_checks(self) -> None:
        assert tuple(check.name for check in REQUIRED_CHECKS) == EVIDENCE_CHECK_NAMES

    def test_verifier_outcomes_are_the_verifier_enum(self) -> None:
        assert tuple(outcome.value for outcome in VerifierOutcome) == AUDIT_VERIFIER_OUTCOMES

    def test_near_miss_a_reordered_copy_is_not_equal(self) -> None:
        # the comparison is ordered: a set check would pass a copy that lost
        # its owner's order, and the console renders in that order
        assert tuple(reversed(POLICYGUARD_CLASSES)) != tuple(c.value for c in ViolationClass)


class TestTheApiImportsNoneOfTheOwners:
    def test_the_api_import_closure_reaches_no_forbidden_module(self) -> None:
        loaded = subprocess.run(
            [sys.executable, "-c", _PROBE],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        ).stdout.split()
        assert loaded == []

    def test_near_miss_the_probe_sees_a_forbidden_import(self) -> None:
        # the same probe, after importing one owner, reports it: an empty answer
        # above is the closure, not a probe that cannot see
        probe = "import intake_platform.audit_verifier\n" + _PROBE
        loaded = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        ).stdout.split()
        assert "intake_platform.audit_verifier" in loaded
