"""INT-269 — the files/12 §5 attestation belongs to the rules engine.

files/12 §5 puts an HMAC-SHA256 attestation over every ``TriageVerdict`` and
then says who may hold it:

    The signing key is fetched from OpenBao **by the rules-engine subsystem
    alone**, and an import-boundary test asserts no module under
    ``extraction/``, ``observers/`` or ``talker/`` transitively imports the
    attestor.

INT-091 had assigned the attestor to the Talker, which is the one place that
rule forbids — *a signature verified by the party that could forge it is not a
signature*. So the attestor lives in ``protocols.triage.attestation`` (this
package is the only producer of a level, CLAUDE.md invariant 1) and this suite
holds four things:

1. **Ownership**, by AST: nothing under ``services/voice-runtime/**`` imports a
   signing primitive, imports the attestor, calls a keyed hash, or carries key
   material — with negative controls proving each arm of the gate can fail, and
   a floor on the number of files scanned so an empty scan cannot pass as a
   clean one.
2. **The seven-way mutation**: level, rule-id set, session id, ``inputs_hash``,
   nonce, key and ``issued_at`` each altered on their own, each refused, with
   the unaltered attestation accepted as the control.
3. **Replay**: a genuine RED replayed against a different session, a later turn
   or a spent nonce is refused, which is what ``inputs_hash`` + nonce buy over
   MAC validity alone.
4. **Invariant 1 is not widened**: :func:`attest` derives its level from a
   :class:`~protocols.triage.engine.TriageEvaluation` and has no parameter that
   could set one; :func:`verify` returns nothing at all.

SENTETİK TEST VERİSİ — every key, session id, rule id, slot name and Turkish
string here is invented for the mechanism tests and carries no clinical
meaning. **Every key is generated inside the test** with
``secrets.token_bytes``: no key material is committed anywhere in this repo,
and the "keys" in the negative controls are runs of a single character chosen
so they cannot be mistaken for one.
"""

from __future__ import annotations

import ast
import base64
import re
import secrets
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import (
    RedLocation,
    RedRegister,
    RuleFire,
    RulesTriageResult,
    TriageLevel,
)
from protocols.triage import SlotAnswer, TriageContext, evaluate_triage
from protocols.triage.attestation import (
    ATTESTATION_KV_PATH,
    FORGED_TRIAGE_TOTAL,
    FRESHNESS_WINDOW,
    MIN_KEY_BYTES,
    AttestationKeyring,
    AttestationRefused,
    ForgedTriageTally,
    KeyringBootError,
    KvSecrets,
    NonceLedger,
    RefusalReason,
    TriageAttestation,
    TriageClaim,
    UnknownKeyId,
    attest,
    context_inputs_hash,
    keyring_from_secrets,
    new_nonce,
    verify,
)
from protocols.types import EK4Level
from pydantic import ValidationError
from synthetic_triage import REF_TIME, ctx, make_rule, present

REPO = Path(__file__).resolve().parents[2]
VOICE_RUNTIME = REPO / "services" / "voice-runtime"
TRIAGE_PACKAGE = REPO / "packages" / "protocols" / "src" / "protocols" / "triage"
ATTESTOR_SOURCE = TRIAGE_PACKAGE / "attestation.py"

SESSION_ID = "ses_sentetik_269"
OTHER_SESSION_ID = "ses_sentetik_269_baska"
PROTOCOL_HASH = "1" * 64
OTHER_PROTOCOL_HASH = "2" * 64
LIFE_THREAT_VERSION = "sentetik.life_threat@0"
ENGINE_VERSION = "protocols.triage@0"
SENTETIK_SLOT = "sentetik.gogus_baskisi"
SENTETIK_RULE = "rf.sentetik_kirmizi"
SENTETIK_RULE_ALT = "rf.sentetik_kirmizi_ikinci"


# ---------------------------------------------------------------------------
# Synthetic keys, generated here — never committed, never in a fixture file.
# ---------------------------------------------------------------------------


def _synthetic_key() -> bytes:
    return secrets.token_bytes(MIN_KEY_BYTES)


def _keyring(active: str = "v1") -> AttestationKeyring:
    return AttestationKeyring({active: _synthetic_key()}, active)


@dataclass(frozen=True)
class FakeKvSecrets:
    """The recorded stand-in for ``intake_platform.secrets.SecretsProvider``.

    No live OpenBao is reachable in this environment (no Docker daemon), which
    is exactly why the key source is an injected interface rather than a
    module-level read: the production path is a `SecretsProvider`, the test
    path is this, and neither one is an environment variable.
    """

    bundle: dict[str, Any]
    path_seen: list[str]

    def get_kv(self, path: str) -> dict[str, Any]:
        self.path_seen.append(path)
        return self.bundle


def _fake_secrets(bundle: dict[str, Any]) -> FakeKvSecrets:
    return FakeKvSecrets(bundle=bundle, path_seen=[])


# ---------------------------------------------------------------------------
# A synthetic RED, produced the only way a level may be produced (invariant 1).
# ---------------------------------------------------------------------------


def _red_context() -> TriageContext:
    return ctx(**{SENTETIK_SLOT: present(True)})


def _red_evaluation(location: RedLocation = RedLocation.REMOTE) -> Any:
    rule = make_rule(
        SENTETIK_RULE,
        EK4Level.KIRMIZI_K2,
        f"{SENTETIK_SLOT} == true",
        register=RedRegister.ALERT,
    )
    return evaluate_triage([rule], _red_context(), location)


def _green_evaluation() -> Any:
    rule = make_rule(
        SENTETIK_RULE,
        EK4Level.KIRMIZI_K2,
        f"{SENTETIK_SLOT} == true",
        register=RedRegister.ALERT,
    )
    return evaluate_triage([rule], ctx(), RedLocation.REMOTE)


@dataclass
class Signed:
    """One signed verdict plus everything a verifier is handed alongside it."""

    attestation: TriageAttestation
    result: RulesTriageResult
    keyring: AttestationKeyring
    inputs_hash: str
    issued_at: datetime
    nonces: NonceLedger
    tally: ForgedTriageTally

    def check(self, **overrides: Any) -> None:
        kwargs: dict[str, Any] = {
            "keyring": self.keyring,
            "session_id": SESSION_ID,
            "inputs_hash": self.inputs_hash,
            "protocol_hash": PROTOCOL_HASH,
            "now": self.issued_at,
            "nonces": self.nonces,
            "tally": self.tally,
        }
        attestation = overrides.pop("attestation", self.attestation)
        result = overrides.pop("result", self.result)
        kwargs.update(overrides)
        verify(attestation, result, **kwargs)


def _signed(keyring: AttestationKeyring | None = None) -> Signed:
    evaluation = _red_evaluation()
    ring = keyring if keyring is not None else _keyring()
    inputs_hash = context_inputs_hash(_red_context())
    issued_at = REF_TIME
    attestation = attest(
        evaluation,
        session_id=SESSION_ID,
        inputs_hash=inputs_hash,
        protocol_hash=PROTOCOL_HASH,
        life_threat_version=LIFE_THREAT_VERSION,
        engine_version=ENGINE_VERSION,
        issued_at=issued_at,
        keyring=ring,
    )
    return Signed(
        attestation=attestation,
        result=evaluation.result,
        keyring=ring,
        inputs_hash=inputs_hash,
        issued_at=issued_at,
        nonces=NonceLedger(),
        tally=ForgedTriageTally(),
    )


def _reclaim(signed: Signed, **updates: Any) -> TriageAttestation:
    """Rewrite claim fields *without* re-signing — a forgery, by construction."""
    forged = signed.attestation.claim.model_copy(update=updates)
    return signed.attestation.model_copy(update={"claim": forged})


# ---------------------------------------------------------------------------
# 1. Ownership — the AST gate over services/voice-runtime/**, and its controls.
# ---------------------------------------------------------------------------

#: Import roots that can produce or verify a signature. ``hashlib`` is NOT one:
#: the runtime hashes content (``work_key``, clip hashes) and must keep doing
#: so. Its keyed modes are caught separately below, because a keyed BLAKE2 is a
#: MAC hiding inside an allowed import.
SIGNING_IMPORT_ROOTS = frozenset(
    {
        "hmac",
        "cryptography",
        "nacl",
        "Crypto",
        "jwt",
        "jose",
        "joserfc",
        "authlib",
        "ecdsa",
        "itsdangerous",
    }
)
ATTESTOR_MODULE = "protocols.triage.attestation"
KEYED_HASH_FUNCTIONS = frozenset({"blake2b", "blake2s", "pbkdf2_hmac", "scrypt"})
#: A name that would be holding key material if it held a long literal.
KEYISH_NAME = re.compile(r"(?:\b|_)(key|keys|secret|secrets|hmac|mac|seed)(?:\b|_)", re.IGNORECASE)
KEY_MATERIAL_MIN_LEN = 16


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str
    detail: str


def scan_source(source: str, path: str) -> list[Finding]:
    """Every way this file could hold or use a signing capability."""
    findings: list[Finding] = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in SIGNING_IMPORT_ROOTS:
                    findings.append(Finding(path, node.lineno, "signing-import", alias.name))
                if alias.name == ATTESTOR_MODULE or alias.name.startswith(f"{ATTESTOR_MODULE}."):
                    findings.append(Finding(path, node.lineno, "attestor-import", alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            root = node.module.split(".")[0]
            if root in SIGNING_IMPORT_ROOTS:
                findings.append(Finding(path, node.lineno, "signing-import", node.module))
            # `from protocols.triage import attestation` names the attestor in
            # the alias, not the module — both forms are the same import.
            named = [node.module, *(f"{node.module}.{alias.name}" for alias in node.names)]
            for candidate in named:
                if candidate == ATTESTOR_MODULE or candidate.startswith(f"{ATTESTOR_MODULE}."):
                    findings.append(Finding(path, node.lineno, "attestor-import", candidate))
        elif isinstance(node, ast.Call):
            findings.extend(_keyed_hash_findings(node, path))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            findings.extend(_key_material_findings(node, path))
    return findings


def _keyed_hash_findings(node: ast.Call, path: str) -> Iterator[Finding]:
    name = node.func.attr if isinstance(node.func, ast.Attribute) else None
    if isinstance(node.func, ast.Name):
        name = node.func.id
    if name in KEYED_HASH_FUNCTIONS and any(kw.arg == "key" for kw in node.keywords):
        yield Finding(path, node.lineno, "keyed-hash", f"{name}(key=...)")


def _key_material_findings(node: ast.Assign | ast.AnnAssign, path: str) -> Iterator[Finding]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    names = [target.id for target in targets if isinstance(target, ast.Name)]
    value = node.value
    if not isinstance(value, ast.Constant) or not isinstance(value.value, (str, bytes)):
        return
    if len(value.value) < KEY_MATERIAL_MIN_LEN:
        return
    for name in names:
        if KEYISH_NAME.search(name):
            yield Finding(path, node.lineno, "key-material", name)


def _scan_tree(root: Path) -> tuple[list[Finding], list[Path]]:
    findings: list[Finding] = []
    scanned: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        scanned.append(path)
        findings.extend(scan_source(path.read_text(encoding="utf-8"), str(path)))
    return findings, scanned


class TestOwnershipBoundary:
    def test_the_attestor_lives_under_packages_protocols_triage(self) -> None:
        assert ATTESTOR_SOURCE.is_file()
        import protocols.triage.attestation as attestor

        assert Path(attestor.__file__ or "").resolve() == ATTESTOR_SOURCE.resolve()

    def test_the_gate_has_something_to_exclude(self) -> None:
        """The attestor itself trips every arm the runtime must not trip —
        otherwise the boundary test below would be vacuous."""
        findings = scan_source(ATTESTOR_SOURCE.read_text(encoding="utf-8"), str(ATTESTOR_SOURCE))
        assert {finding.kind for finding in findings} == {"signing-import"}

    def test_voice_runtime_holds_no_signing_capability(self) -> None:
        findings, scanned = _scan_tree(VOICE_RUNTIME)
        assert findings == []
        assert len(scanned) >= 40, "an empty or truncated scan must not pass as a clean one"

    @pytest.mark.parametrize(
        ("source", "kind"),
        [
            ("import hmac\n", "signing-import"),
            ("from hmac import compare_digest\n", "signing-import"),
            (f"from {ATTESTOR_MODULE} import attest\n", "attestor-import"),
            (f"import {ATTESTOR_MODULE}\n", "attestor-import"),
            ("from protocols.triage import attestation\n", "attestor-import"),
            ("import hashlib\nd = hashlib.blake2b(b'x', key=k)\n", "keyed-hash"),
            (f'SIGNING_KEY = "{"a" * 40}"\n', "key-material"),
            (f'hmac_secret: bytes = b"{"b" * 40}"\n', "key-material"),
        ],
    )
    def test_negative_control_the_gate_fails_when_it_should(self, source: str, kind: str) -> None:
        findings = scan_source(source, "<synthetic offender>")
        assert findings, "the gate must report this offender"
        assert {finding.kind for finding in findings} == {kind}

    @pytest.mark.parametrize(
        "source",
        [
            "import hashlib\nd = hashlib.sha256(b'x').hexdigest()\n",  # content hash: allowed
            'script_hash = "0" * 64\n',  # not a keyish name
            'KEY_PREFIX = "sh"\n',  # keyish name, far too short to be material
            "from protocols.triage import evaluate_triage\n",  # the engine, not the attestor
        ],
    )
    def test_the_gate_does_not_fire_on_the_runtime_s_legitimate_hashing(self, source: str) -> None:
        assert scan_source(source, "<allowed>") == []


# --- and the same boundary transitively, which is what files/12 §5 asks for ---

FIRST_PARTY_ROOTS = {
    "intake_voice_runtime": REPO / "services" / "voice-runtime" / "src",
    "protocols": REPO / "packages" / "protocols" / "src",
    "clinical_schemas": REPO / "packages" / "clinical-schemas" / "src",
    "intake_platform": REPO / "packages" / "intake_platform" / "src",
    "voice_clips": REPO / "packages" / "voice-clips" / "src",
}


def imported_modules(source: str) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
            # `from pkg import submodule` is a module edge too, not just a name.
            modules.update(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


def _module_files(module: str, roots: dict[str, Path]) -> list[Path]:
    """Every file Python executes to import ``module`` — the leaf and every
    package ``__init__`` above it, which is exactly how a package re-export
    turns a submodule import into a transitive one."""
    parts = module.split(".")
    root = roots.get(parts[0])
    if root is None:
        return []
    files: list[Path] = []
    for depth in range(1, len(parts) + 1):
        prefix = parts[:depth]
        init = root.joinpath(*prefix, "__init__.py")
        if init.is_file():
            files.append(init)
        if depth == len(parts):
            leaf = root.joinpath(*prefix[:-1], f"{prefix[-1]}.py")
            if leaf.is_file():
                files.append(leaf)
    return files


def reachable_modules(seeds: list[Path], roots: dict[str, Path]) -> set[str]:
    seen: set[Path] = set(seeds)
    queue = list(seeds)
    modules: set[str] = set()
    while queue:
        source = queue.pop().read_text(encoding="utf-8")
        for module in imported_modules(source):
            if module.split(".")[0] not in roots:
                continue
            modules.add(module)
            for path in _module_files(module, roots):
                if path not in seen:
                    seen.add(path)
                    queue.append(path)
    return modules


class TestTransitiveBoundary:
    def test_no_voice_runtime_module_transitively_imports_the_attestor(self) -> None:
        seeds = sorted((REPO / "services" / "voice-runtime").rglob("*.py"))
        reached = reachable_modules(seeds, FIRST_PARTY_ROOTS)
        assert ATTESTOR_MODULE not in reached
        assert not any(module.startswith(f"{ATTESTOR_MODULE}.") for module in reached)
        # Non-vacuous: the walk does reach into this very package.
        assert "protocols.triage.context" in reached

    def test_the_package_init_does_not_re_export_the_attestor(self) -> None:
        """``typed/render.py`` imports ``protocols.triage.context``, which
        executes ``protocols/triage/__init__.py``. A re-export there would put
        the attestor — and ``hmac`` — inside the runtime process."""
        init = REPO / "packages" / "protocols" / "src" / "protocols" / "triage" / "__init__.py"
        assert "attestation" not in init.read_text(encoding="utf-8")

    def test_negative_control_the_walk_follows_edges_transitively(self, tmp_path: Path) -> None:
        package = tmp_path / "sentetikpkg"
        package.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "a.py").write_text("from sentetikpkg import b\n", encoding="utf-8")
        (package / "b.py").write_text(f"from {ATTESTOR_MODULE} import attest\n", encoding="utf-8")
        roots = dict(FIRST_PARTY_ROOTS) | {"sentetikpkg": tmp_path}
        reached = reachable_modules([package / "a.py"], roots)
        assert ATTESTOR_MODULE in reached


class TestCompareDigest:
    def test_the_mac_is_compared_with_hmac_compare_digest(self) -> None:
        source = ATTESTOR_SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "compare_digest"
        ]
        assert calls, "the attestor must compare the MAC in constant time"

    def test_no_equality_comparison_touches_the_mac(self) -> None:
        source = ATTESTOR_SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        offenders = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            if not any(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops):
                continue
            segment = ast.get_source_segment(source, node) or ""
            if ".mac" in segment or "_mac(" in segment:
                offenders.append(segment)
        assert offenders == []


# ---------------------------------------------------------------------------
# 2. The key comes from OpenBao through an injected interface — never an env var.
# ---------------------------------------------------------------------------


def _bundle(**keys: bytes) -> dict[str, Any]:
    encoded = {
        key_id: base64.b64encode(material).decode("ascii") for key_id, material in keys.items()
    }
    return {"active_key_id": next(iter(encoded)), "keys": encoded}


class TestKeySource:
    def test_the_keyring_is_read_from_the_kv_path_the_rules_engine_owns(self) -> None:
        material = _synthetic_key()
        secrets_provider = _fake_secrets(_bundle(v1=material))
        keyring = keyring_from_secrets(secrets_provider)
        assert secrets_provider.path_seen == [ATTESTATION_KV_PATH]
        assert keyring.active_key_id == "v1"
        assert keyring.key_ids == ("v1",)
        assert keyring.signing_key("v1") == material

    def test_the_fake_provider_satisfies_the_declared_slice(self) -> None:
        assert isinstance(_fake_secrets(_bundle(v1=_synthetic_key())), KvSecrets)

    def test_a_missing_active_key_id_fails_closed(self) -> None:
        bundle = _bundle(v1=_synthetic_key())
        del bundle["active_key_id"]
        with pytest.raises(KeyringBootError):
            keyring_from_secrets(_fake_secrets(bundle))

    def test_an_empty_key_set_fails_closed(self) -> None:
        with pytest.raises(KeyringBootError):
            keyring_from_secrets(_fake_secrets({"active_key_id": "v1", "keys": {}}))

    def test_a_non_string_key_fails_closed(self) -> None:
        with pytest.raises(KeyringBootError):
            keyring_from_secrets(_fake_secrets({"active_key_id": "v1", "keys": {"v1": 7}}))

    def test_a_key_that_is_not_base64_fails_closed_without_echoing_it(self) -> None:
        with pytest.raises(KeyringBootError) as excinfo:
            keyring_from_secrets(_fake_secrets({"active_key_id": "v1", "keys": {"v1": "!!!!"}}))
        assert "!!!!" not in str(excinfo.value)

    def test_a_short_key_fails_closed(self) -> None:
        short = base64.b64encode(secrets.token_bytes(MIN_KEY_BYTES - 1)).decode("ascii")
        with pytest.raises(KeyringBootError):
            keyring_from_secrets(_fake_secrets({"active_key_id": "v1", "keys": {"v1": short}}))

    def test_an_active_key_id_outside_the_key_set_fails_closed(self) -> None:
        with pytest.raises(KeyringBootError):
            AttestationKeyring({"v1": _synthetic_key()}, "v2")

    def test_an_unknown_key_id_raises_rather_than_returning_a_key(self) -> None:
        with pytest.raises(UnknownKeyId):
            _keyring().signing_key("v9")

    def test_the_keyring_never_renders_key_material(self) -> None:
        material = _synthetic_key()
        keyring = AttestationKeyring({"v1": material}, "v1")
        rendered = f"{keyring!r} {keyring}"
        assert material.hex() not in rendered
        assert base64.b64encode(material).decode("ascii") not in rendered
        assert "v1" in rendered

    def test_the_attestor_reads_no_environment_variable(self) -> None:
        source = ATTESTOR_SOURCE.read_text(encoding="utf-8")
        assert "os.environ" not in source
        assert "getenv" not in source


# ---------------------------------------------------------------------------
# 3. Signing — and invariant 1: attest authenticates a level, never mints one.
# ---------------------------------------------------------------------------


class TestAttestationIsNotASecondRouteToALevel:
    def test_attest_takes_no_parameter_that_could_set_a_level(self) -> None:
        import inspect

        parameters = set(inspect.signature(attest).parameters)
        assert parameters & {"level", "ek4", "rule_ids", "result", "register", "location"} == set()

    def test_the_claim_carries_the_evaluation_s_own_determination(self) -> None:
        signed = _signed()
        evaluation = _red_evaluation()
        assert signed.attestation.claim.level is evaluation.result.level
        assert signed.attestation.claim.ek4 is evaluation.ek4
        assert signed.attestation.claim.rule_ids == (SENTETIK_RULE,)
        assert signed.attestation.claim.register is RedRegister.ALERT
        assert signed.attestation.claim.location is RedLocation.REMOTE

    def test_verify_returns_nothing(self) -> None:
        signed = _signed()
        assert signed.check() is None

    def test_a_green_evaluation_attests_too_and_carries_no_red_axes(self) -> None:
        evaluation = _green_evaluation()
        keyring = _keyring()
        attestation = attest(
            evaluation,
            session_id=SESSION_ID,
            inputs_hash=context_inputs_hash(ctx()),
            protocol_hash=PROTOCOL_HASH,
            life_threat_version=LIFE_THREAT_VERSION,
            engine_version=ENGINE_VERSION,
            issued_at=REF_TIME,
            keyring=keyring,
        )
        assert attestation.claim.level is TriageLevel.GREEN
        assert attestation.claim.rule_ids == ()
        assert attestation.claim.register is None
        assert attestation.claim.location is None
        verify(
            attestation,
            evaluation.result,
            keyring=keyring,
            session_id=SESSION_ID,
            inputs_hash=context_inputs_hash(ctx()),
            protocol_hash=PROTOCOL_HASH,
            now=REF_TIME,
            nonces=NonceLedger(),
        )

    def test_an_explicit_key_id_signs_under_that_key(self) -> None:
        keyring = AttestationKeyring({"v1": _synthetic_key(), "v2": _synthetic_key()}, "v1")
        attestation = attest(
            _red_evaluation(),
            session_id=SESSION_ID,
            inputs_hash=context_inputs_hash(_red_context()),
            protocol_hash=PROTOCOL_HASH,
            life_threat_version=LIFE_THREAT_VERSION,
            engine_version=ENGINE_VERSION,
            issued_at=REF_TIME,
            keyring=keyring,
            key_id="v2",
            nonce=new_nonce(),
        )
        assert attestation.claim.key_id == "v2"

    def test_the_nonce_moves_and_the_versions_do_not(self) -> None:
        first, second = _signed(), _signed()
        assert first.attestation.claim.nonce != second.attestation.claim.nonce
        assert first.attestation.claim.protocol_hash == second.attestation.claim.protocol_hash
        assert (
            first.attestation.claim.life_threat_version
            == second.attestation.claim.life_threat_version
        )
        assert first.attestation.claim.engine_version == second.attestation.claim.engine_version


class TestClaimShape:
    def test_rule_ids_must_be_sorted_and_unique(self) -> None:
        signed = _signed()
        payload = signed.attestation.claim.model_dump()
        payload["rule_ids"] = (SENTETIK_RULE_ALT, SENTETIK_RULE)
        with pytest.raises(ValidationError):
            TriageClaim.model_validate(payload)

    def test_a_duplicated_rule_id_is_refused(self) -> None:
        signed = _signed()
        payload = signed.attestation.claim.model_dump()
        payload["rule_ids"] = (SENTETIK_RULE, SENTETIK_RULE)
        with pytest.raises(ValidationError):
            TriageClaim.model_validate(payload)


class TestInputsHash:
    def test_the_same_context_hashes_the_same_and_a_changed_answer_does_not(self) -> None:
        first = context_inputs_hash(_red_context())
        assert first == context_inputs_hash(_red_context())
        changed = ctx(**{SENTETIK_SLOT: present(False)})
        assert context_inputs_hash(changed) != first

    def test_the_answer_state_is_part_of_the_hash(self) -> None:
        asked = ctx(**{SENTETIK_SLOT: present(True)})
        declined = ctx(**{SENTETIK_SLOT: SlotAnswer(state=AnswerState.DECLINED)})
        assert context_inputs_hash(asked) != context_inputs_hash(declined)

    def test_a_decimal_slot_value_hashes_by_its_exact_form(self) -> None:
        """INT-267: a Decimal keeps its authored scale on every boundary."""
        one = ctx(**{SENTETIK_SLOT: present(Decimal("38.50"))})
        two = ctx(**{SENTETIK_SLOT: present(Decimal("38.5"))})
        assert context_inputs_hash(one) != context_inputs_hash(two)


class TestCanonicalisation:
    def test_field_boundaries_cannot_be_slid(self) -> None:
        """Length-prefixed fields: no pair of different claims shares a MAC."""
        keyring = _keyring()
        base = _signed(keyring).attestation
        slid = base.claim.model_copy(
            update={
                "session_id": SESSION_ID[:-1],
                "life_threat_version": SESSION_ID[-1] + LIFE_THREAT_VERSION,
            }
        )
        other = TriageAttestation(
            claim=slid,
            mac=attest(
                _red_evaluation(),
                session_id=SESSION_ID,
                inputs_hash=base.claim.inputs_hash,
                protocol_hash=PROTOCOL_HASH,
                life_threat_version=LIFE_THREAT_VERSION,
                engine_version=ENGINE_VERSION,
                issued_at=REF_TIME,
                keyring=keyring,
                nonce=base.claim.nonce,
            ).mac,
        )
        # The slid claim is a different claim, so the genuine MAC does not fit it.
        with pytest.raises(AttestationRefused) as excinfo:
            verify(
                other,
                _red_evaluation().result,
                keyring=keyring,
                session_id=SESSION_ID[:-1],
                inputs_hash=base.claim.inputs_hash,
                protocol_hash=PROTOCOL_HASH,
                now=REF_TIME,
                nonces=NonceLedger(),
            )
        assert excinfo.value.reason is RefusalReason.BAD_MAC


# ---------------------------------------------------------------------------
# 4. THE SEVEN-WAY MUTATION — one control accepted, seven mutations refused.
# ---------------------------------------------------------------------------


def _mutate_level(signed: Signed) -> dict[str, Any]:
    """ "Set me green" — files/10 §9's named triage threat, coherently forged:
    both the verdict and the claim say GREEN, so only the MAC can catch it."""
    green = {"level": TriageLevel.GREEN, "register": None, "location": None, "rule_ids": ()}
    return {
        "attestation": _reclaim(signed, **green),
        "result": signed.result.model_copy(
            update={
                "level": TriageLevel.GREEN,
                "rules": (),
                "register": None,
                "location": None,
            }
        ),
    }


def _mutate_rule_ids(signed: Signed) -> dict[str, Any]:
    return {
        "attestation": _reclaim(signed, rule_ids=(SENTETIK_RULE_ALT,)),
        "result": signed.result.model_copy(
            update={"rules": (RuleFire(id=SENTETIK_RULE_ALT, evidence="sentetik"),)}
        ),
    }


def _mutate_session_id(signed: Signed) -> dict[str, Any]:
    return {
        "attestation": _reclaim(signed, session_id=OTHER_SESSION_ID),
        "session_id": OTHER_SESSION_ID,
    }


def _mutate_inputs_hash(signed: Signed) -> dict[str, Any]:
    other = context_inputs_hash(ctx(**{SENTETIK_SLOT: present(False)}))
    return {"attestation": _reclaim(signed, inputs_hash=other), "inputs_hash": other}


def _mutate_nonce(signed: Signed) -> dict[str, Any]:
    return {"attestation": _reclaim(signed, nonce=new_nonce())}


def _mutate_key(signed: Signed) -> dict[str, Any]:
    """A second key under the *same* key id: the claim is untouched and every
    binding still matches, so nothing but the key itself is on trial."""
    other_ring = AttestationKeyring({signed.keyring.active_key_id: _synthetic_key()}, "v1")
    forged = attest(
        _red_evaluation(),
        session_id=SESSION_ID,
        inputs_hash=signed.inputs_hash,
        protocol_hash=PROTOCOL_HASH,
        life_threat_version=LIFE_THREAT_VERSION,
        engine_version=ENGINE_VERSION,
        issued_at=signed.issued_at,
        keyring=other_ring,
        nonce=signed.attestation.claim.nonce,
    )
    return {"attestation": forged}


def _mutate_issued_at(signed: Signed) -> dict[str, Any]:
    """Moved inside the freshness window, so the clock check would pass — the
    MAC is the only thing that can refuse it."""
    moved = signed.issued_at + timedelta(seconds=3)
    return {"attestation": _reclaim(signed, issued_at=moved), "now": moved}


SEVEN_WAYS = [
    ("level", _mutate_level),
    ("rule_ids", _mutate_rule_ids),
    ("session_id", _mutate_session_id),
    ("inputs_hash", _mutate_inputs_hash),
    ("nonce", _mutate_nonce),
    ("key", _mutate_key),
    ("issued_at", _mutate_issued_at),
]


class TestSevenWayMutation:
    def test_the_control_is_accepted(self) -> None:
        signed = _signed()
        signed.check()
        assert signed.tally.total == 0

    @pytest.mark.parametrize(("name", "mutate"), SEVEN_WAYS, ids=[name for name, _ in SEVEN_WAYS])
    def test_each_mutation_on_its_own_is_refused(self, name: str, mutate: Any) -> None:
        signed = _signed()
        with pytest.raises(AttestationRefused) as excinfo:
            signed.check(**mutate(signed))
        assert excinfo.value.reason is RefusalReason.BAD_MAC, name
        assert signed.tally.count(RefusalReason.BAD_MAC) == 1
        assert signed.tally.total == 1

    def test_all_seven_are_refused_and_the_control_still_passes(self) -> None:
        signed = _signed()
        refused = []
        for name, mutate in SEVEN_WAYS:
            with pytest.raises(AttestationRefused):
                signed.check(**mutate(signed))
            refused.append(name)
        assert refused == [name for name, _ in SEVEN_WAYS]
        assert signed.tally.total == 7
        signed.check()  # the unaltered attestation is still accepted
        assert signed.tally.total == 7


# ---------------------------------------------------------------------------
# 5. Replay — what inputs_hash + nonce buy over MAC validity alone.
# ---------------------------------------------------------------------------


class TestReplay:
    def test_a_genuine_red_replayed_into_another_session_is_refused(self) -> None:
        signed = _signed()
        with pytest.raises(AttestationRefused) as excinfo:
            signed.check(session_id=OTHER_SESSION_ID)
        assert excinfo.value.reason is RefusalReason.SESSION_MISMATCH
        assert signed.tally.count(RefusalReason.SESSION_MISMATCH) == 1

    def test_a_genuine_red_replayed_on_a_later_turn_is_refused(self) -> None:
        signed = _signed()
        with pytest.raises(AttestationRefused) as excinfo:
            signed.check(now=signed.issued_at + FRESHNESS_WINDOW + timedelta(milliseconds=1))
        assert excinfo.value.reason is RefusalReason.STALE

    def test_an_attestation_from_the_future_is_refused(self) -> None:
        signed = _signed()
        with pytest.raises(AttestationRefused) as excinfo:
            signed.check(now=signed.issued_at - FRESHNESS_WINDOW - timedelta(milliseconds=1))
        assert excinfo.value.reason is RefusalReason.STALE

    def test_the_same_nonce_is_spent_once(self) -> None:
        signed = _signed()
        signed.check()
        with pytest.raises(AttestationRefused) as excinfo:
            signed.check()
        assert excinfo.value.reason is RefusalReason.NONCE_REUSE

    def test_a_verdict_the_attestation_does_not_cover_is_refused(self) -> None:
        signed = _signed()
        other = RulesTriageResult(
            level=TriageLevel.RED,
            rules=(RuleFire(id=SENTETIK_RULE_ALT, evidence="sentetik"),),
            register=RedRegister.ALERT,
            location=RedLocation.REMOTE,
        )
        with pytest.raises(AttestationRefused) as excinfo:
            signed.check(result=other)
        assert excinfo.value.reason is RefusalReason.VERDICT_MISMATCH

    def test_a_register_swap_on_the_verdict_is_refused(self) -> None:
        signed = _signed()
        other = signed.result.model_copy(update={"register": RedRegister.SILENT})
        with pytest.raises(AttestationRefused) as excinfo:
            signed.check(result=other)
        assert excinfo.value.reason is RefusalReason.VERDICT_MISMATCH

    def test_a_location_swap_on_the_verdict_is_refused(self) -> None:
        signed = _signed()
        other = signed.result.model_copy(update={"location": RedLocation.ON_SITE})
        with pytest.raises(AttestationRefused) as excinfo:
            signed.check(result=other)
        assert excinfo.value.reason is RefusalReason.VERDICT_MISMATCH

    def test_inputs_that_are_not_the_context_just_evaluated_are_refused(self) -> None:
        signed = _signed()
        with pytest.raises(AttestationRefused) as excinfo:
            signed.check(inputs_hash=context_inputs_hash(ctx()))
        assert excinfo.value.reason is RefusalReason.INPUTS_MISMATCH

    def test_a_pack_the_session_is_not_pinned_to_is_refused(self) -> None:
        signed = _signed()
        with pytest.raises(AttestationRefused) as excinfo:
            signed.check(protocol_hash=OTHER_PROTOCOL_HASH)
        assert excinfo.value.reason is RefusalReason.PROTOCOL_MISMATCH

    def test_an_unknown_key_id_is_refused(self) -> None:
        signed = _signed()
        with pytest.raises(AttestationRefused) as excinfo:
            signed.check(attestation=_reclaim(signed, key_id="v9"))
        assert excinfo.value.reason is RefusalReason.UNKNOWN_KEY

    def test_a_refusal_without_a_tally_still_raises(self) -> None:
        signed = _signed()
        with pytest.raises(AttestationRefused):
            verify(
                signed.attestation,
                signed.result,
                keyring=signed.keyring,
                session_id=OTHER_SESSION_ID,
                inputs_hash=signed.inputs_hash,
                protocol_hash=PROTOCOL_HASH,
                now=signed.issued_at,
                nonces=signed.nonces,
            )


class TestNonceLedger:
    def test_a_nonce_is_remembered_once_per_session(self) -> None:
        ledger = NonceLedger()
        nonce = new_nonce()
        assert ledger.remember(SESSION_ID, nonce) is True
        assert ledger.remember(SESSION_ID, nonce) is False
        assert ledger.remember(OTHER_SESSION_ID, nonce) is True
        assert len(ledger) == 2

    def test_the_ledger_is_bounded(self) -> None:
        """Bounded because the freshness window already refuses anything old
        enough to have been evicted (files/12 §5: issued_at within 5 s)."""
        ledger = NonceLedger(capacity=2)
        first, second, third = new_nonce(), new_nonce(), new_nonce()
        assert ledger.remember(SESSION_ID, first) is True
        assert ledger.remember(SESSION_ID, second) is True
        assert ledger.remember(SESSION_ID, third) is True
        assert len(ledger) == 2
        assert ledger.remember(SESSION_ID, second) is False

    def test_a_ledger_with_no_capacity_is_refused(self) -> None:
        with pytest.raises(ValueError, match="capacity"):
            NonceLedger(capacity=0)


# ---------------------------------------------------------------------------
# 6. The metric — declared, catalogued before emitted, no PHI in the labels.
# ---------------------------------------------------------------------------

CATALOG = REPO / "observability" / "metrics_catalog.yaml"
PHI_LABEL_NAMES = frozenset(
    {
        "session",
        "session_id",
        "patient",
        "patient_id",
        "phone",
        "tc_kimlik",
        "text",
        "transcript",
        "utterance",
        "evidence",
        "slot",
        "value",
        "rule",
    }
)


class TestForgedTriageMetric:
    def test_the_counter_is_declared_with_a_closed_label_set(self) -> None:
        assert FORGED_TRIAGE_TOTAL.id == "safety.forged_triage_total"
        assert FORGED_TRIAGE_TOTAL.name == "safety_forged_triage_total"
        assert FORGED_TRIAGE_TOTAL.labels == ("reason",)

    def test_no_label_can_carry_patient_content(self) -> None:
        assert set(FORGED_TRIAGE_TOTAL.labels) & PHI_LABEL_NAMES == set()

    def test_every_reason_is_a_closed_enumeration_value(self) -> None:
        signed = _signed()
        with pytest.raises(AttestationRefused):
            signed.check(session_id=OTHER_SESSION_ID)
        for reason in signed.tally.by_reason:
            assert isinstance(reason, RefusalReason)
            assert reason.value.isidentifier()

    def test_nothing_is_emitted_while_the_catalogue_row_is_absent(self) -> None:
        """Invariant 13 is row-first: until observability/metrics_catalog.yaml
        carries ``safety_forged_triage_total``, the attestor counts in process
        and constructs no Prometheus family."""
        source = ATTESTOR_SOURCE.read_text(encoding="utf-8")
        assert "prometheus_client" not in source
        tree = ast.parse(source)
        constructed = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert constructed & {"Counter", "Gauge", "Histogram", "Summary"} == set()

    def test_the_catalogue_row_is_still_the_open_prerequisite(self) -> None:
        catalogued = "safety_forged_triage_total" in CATALOG.read_text(encoding="utf-8")
        emitted = "prometheus_client" in ATTESTOR_SOURCE.read_text(encoding="utf-8")
        assert not emitted or catalogued, "a series may never be emitted before it is catalogued"

    def test_the_tally_counts_each_refusal_once(self) -> None:
        tally = ForgedTriageTally()
        tally.record(RefusalReason.BAD_MAC)
        tally.record(RefusalReason.BAD_MAC)
        tally.record(RefusalReason.STALE)
        assert tally.count(RefusalReason.BAD_MAC) == 2
        assert tally.count(RefusalReason.NONCE_REUSE) == 0
        assert tally.total == 3
        assert dict(tally.by_reason) == {RefusalReason.BAD_MAC: 2, RefusalReason.STALE: 1}


class TestNoPhiOnTheRefusalPath:
    def test_a_refusal_message_carries_no_session_or_slot_content(self) -> None:
        signed = _signed()
        messages = []
        for _name, mutate in SEVEN_WAYS:
            with pytest.raises(AttestationRefused) as excinfo:
                signed.check(**mutate(signed))
            messages.append(str(excinfo.value))
        joined = " ".join(messages)
        assert SESSION_ID not in joined
        assert OTHER_SESSION_ID not in joined
        assert SENTETIK_SLOT not in joined
        assert signed.attestation.claim.inputs_hash not in joined
