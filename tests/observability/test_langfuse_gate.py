"""INT-175 — self-hosted Langfuse, the trace emission boundary, the annotation
queues and the recorded-experiment gate (CLAUDE.md inv. 4/6/13/14/15/17/19;
files/08 §0b F1, §2.5, §3, §6, §7; files/10 §6, §9 row observability-pipeline).

The acceptance line under test, verbatim (docs/backlog/issues.yaml INT-175):
  "compose profile; OTel span export; CI job runs recorded simulator
   experiment and gates on scores"

The risk this file exists to hold shut is files/HUMAN_BLOCKERS.md **HB-L6**:
Langfuse stores prompts and completions verbatim, the extraction prompt IS
the patient's transcript, and counsel has not ruled on staff read paths into
patient content. So the tests below are adversarial rather than descriptive —
they plant a Turkish symptom sentence at every seam that could carry it and
assert it never reaches a payload, a queue item, a review, a recorded run or
an audit row, and that the content-carrying mode is ABSENT rather than off.

CI never boots Langfuse: the compose tier is validated statically, exactly as
tests/observability/test_obs_compose.py validates the obs tier.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from intake_platform.audit import AuditChain, InMemoryAuditStore
from intake_platform.observability.annotation import (
    QUEUES,
    ContentReadRefused,
    Label,
    QueueId,
    QueueItem,
    ReviewerRole,
    SectionReason,
    authorize_content_read,
    enqueue,
    queue_def,
    record_review,
)
from intake_platform.observability.experiment import (
    ExperimentRecord,
    GateResult,
    RecordRefused,
    Thresholds,
    gate,
    load_records,
    load_thresholds,
    score,
)
from intake_platform.observability.spans import (
    DENIED_FIELD_TOKENS,
    LLM_SPAN_FIELDS,
    LlmSpan,
    SpanFieldRefused,
    SpanKind,
    SpanOutcome,
    emit_llm_span,
)
from intake_platform.slo import load_metrics_catalog, load_slo_file
from intake_probes.registry import load_registry
from intake_probes.runner import DevProbeConfig, build_dev_clients

REPO = Path(__file__).resolve().parents[2]
INFRA = REPO / "infra"
COMPOSE_PATH = INFRA / "docker-compose.langfuse.yml"
REGISTRY_PATH = REPO / "observability" / "registry.yaml"
CATALOG_PATH = REPO / "observability" / "metrics_catalog.yaml"
THRESHOLDS_PATH = REPO / "observability" / "experiment_thresholds.yaml"
SLO_PATH = REPO / "docs" / "slo" / "langfuse.yaml"
RECORDED_RUN = REPO / "tests" / "fixtures" / "experiments" / "extraction_recorded_run.jsonl"
EXPERIMENT_CLI = REPO / "scripts" / "observability" / "langfuse_experiment.py"

SPANS_SRC = (
    REPO / "packages" / "intake_platform" / "src" / "intake_platform" / "observability" / "spans.py"
)
ANNOTATION_SRC = SPANS_SRC.with_name("annotation.py")

#: The planted adversary. B1-Turkish symptom narrative — spaces, Turkish
#: diacritics, no identifier pattern in it at all, so `redact_text` would
#: pass it through untouched. That is the point: the boundary must refuse a
#: carrier, not scrub a string.
TURKISH_SYMPTOM = "Göğsümde iki gündür şiddetli bir ağrı var ve nefes almakta zorlanıyorum."

#: A second adversary that also carries a checksum-valid TC Kimlik, to prove
#: the refusal is structural rather than a lucky pattern hit.
TURKISH_WITH_TCKN = "Hastanın kimlik numarası 10000000146 ve karın ağrısı şikayeti var."


def _compose() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    return loaded


def _services() -> dict[str, dict[str, Any]]:
    services: dict[str, dict[str, Any]] = _compose()["services"]
    return services


def _image_refs(service: dict[str, Any]) -> list[str]:
    if "image" in service:
        return [str(service["image"])]
    inline = str(service.get("build", {}).get("dockerfile_inline", ""))
    return [
        line.split()[1] for line in inline.splitlines() if line.strip().upper().startswith("FROM ")
    ]


def _valid_span(**overrides: Any) -> LlmSpan:
    base: dict[str, Any] = {
        "work_id": "work_0f3a1c",
        "session_id_hash": "4d1a9c77b0e2f513",
        "tenant_id": "tenant_acibadem",
        "prompt_version": "extraction@v7",
        "protocol_hash": "9f2c1de4aa10bb37",
        "model_id": "Qwen/Qwen3.5-9B",
        "model_revision": "c202236",
        "kind": SpanKind.EXTRACTION,
        "outcome": SpanOutcome.OK,
        "latency_ms": 812,
        "input_tokens": 1240,
        "output_tokens": 96,
        "input_chars": 4821,
        "output_chars": 311,
        "candidate_flag_count": 1,
        "schema_id": "slots.chest_pain.v3",
    }
    base.update(overrides)
    return LlmSpan(**base)


def _item(**overrides: Any) -> QueueItem:
    base: dict[str, Any] = {
        "item_id": "aq_00019",
        "queue": QueueId.NOTE_QUALITY,
        "tenant_id": "tenant_acibadem",
        "session_id_hash": "4d1a9c77b0e2f513",
        "work_id": "work_0f3a1c",
        "span_ref": "lf:trace:8b1c0d2e",
        "created_at_utc": "2026-08-29T09:15:00Z",
    }
    base.update(overrides)
    return QueueItem(**base)


class _RecordingSink:
    """A span sink that keeps what it was handed, so a test can assert on the
    exact bytes that left the boundary. It lives here rather than in the
    package because a recording sink is a test double (invariant 17)."""

    def __init__(self) -> None:
        self.emitted: list[tuple[str, dict[str, str | int]]] = []

    def emit(self, name: str, attributes: Any) -> None:
        self.emitted.append((name, dict(attributes)))


class _AllowingConsent:
    """A consent gate that says yes to everything — so that every refusal
    below is attributable to the content gate, never to a missing consent."""

    def allows(self, *, tenant_id: str, session_id_hash: str, scope: str) -> bool:
        return True


class _DenyingConsent:
    def allows(self, *, tenant_id: str, session_id_hash: str, scope: str) -> bool:
        return False


class _Chain:
    """An audit chain plus the store behind it, so a test can read back what
    was appended without production code growing a test-only accessor."""

    def __init__(self) -> None:
        self.store = InMemoryAuditStore()
        self.chain = AuditChain(self.store)

    def append(self, **kwargs: str) -> object:
        return self.chain.append(**kwargs)  # type: ignore[arg-type]

    def actions(self) -> list[str]:
        return [entry.action for entry in self.store.entries()]


def _module_ast(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imported_modules(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(_module_ast(path)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            names.add(node.module)
    return names


def _identifier_tokens(path: Path) -> set[str]:
    """Every attribute name and bare name the module mentions."""
    tokens: set[str] = set()
    for node in ast.walk(_module_ast(path)):
        if isinstance(node, ast.Attribute):
            tokens.add(node.attr)
        elif isinstance(node, ast.Name):
            tokens.add(node.id)
    return tokens


# =====================================================================================
# 1. The compose tier — its own file, and the shared dev tier is untouched
# =====================================================================================


class TestLangfuseComposeTier:
    def test_it_is_its_own_file_and_the_shared_dev_tier_is_untouched(self) -> None:
        # INT-202 set the precedent (tests/infra/test_restore_drill.py) and
        # this restates it for the hottest shared file in the repo: nothing
        # about Langfuse belongs in the tier every developer boots.
        assert COMPOSE_PATH.is_file()
        dev = (INFRA / "docker-compose.dev.yml").read_text(encoding="utf-8")
        assert "langfuse" not in dev.lower()
        assert "clickhouse" not in dev.lower()

    def test_every_service_is_gated_behind_the_langfuse_profile(self) -> None:
        for name, service in _services().items():
            assert service.get("profiles") == ["langfuse"], (
                f"{name} would start with the plain dev tier"
            )

    def test_the_tier_carries_the_whole_langfuse_v3_dependency_set(self) -> None:
        # Langfuse v3+ needs Postgres, ClickHouse, Redis and S3; a tier that
        # silently borrowed the dev Postgres would put trace data in the
        # patient database.
        assert {
            "langfuse-web",
            "langfuse-worker",
            "langfuse-postgres",
            "langfuse-clickhouse",
            "langfuse-redis",
            "langfuse-minio",
        } == set(_services())

    def test_every_image_is_tag_pinned(self) -> None:
        for name, service in _services().items():
            refs = _image_refs(service)
            assert refs, f"{name} pulls no image and builds nothing"
            for ref in refs:
                assert ":" in ref, f"{name}: unpinned image reference {ref}"
                assert ref.rsplit(":", 1)[1] not in {"latest", ""}, f"{name}: floating tag {ref}"

    def test_only_the_web_ui_publishes_a_port_and_it_binds_loopback(self) -> None:
        publishing = {
            name: service["ports"] for name, service in _services().items() if service.get("ports")
        }
        assert set(publishing) == {"langfuse-web"}, (
            "a backing store that publishes a port is a second, unguarded door "
            "into trace storage (files/08 §0b F1)"
        )
        for name, ports in publishing.items():
            for port in ports:
                assert str(port).startswith("127.0.0.1:"), (
                    f"{name} publishes {port} beyond loopback"
                )

    def test_every_service_has_a_healthcheck(self) -> None:
        for name, service in _services().items():
            assert "healthcheck" in service, f"{name} has no healthcheck"

    def test_no_credential_literal_and_no_inline_default_for_a_secret(self) -> None:
        # invariant 14: secrets come from OpenBao. The tier interpolates them
        # from the caller's environment, which scripts/observability/
        # langfuse_secrets.sh fills; a `${X:-default}` on a secret is how a
        # dev default reaches a deployed stack.
        text = COMPOSE_PATH.read_text(encoding="utf-8")
        for secret in (
            "LANGFUSE_SALT",
            "LANGFUSE_ENCRYPTION_KEY",
            "LANGFUSE_NEXTAUTH_SECRET",
            "LANGFUSE_POSTGRES_PASSWORD",
            "LANGFUSE_CLICKHOUSE_PASSWORD",
            "LANGFUSE_REDIS_PASSWORD",
            "LANGFUSE_S3_ACCESS_KEY_ID",
            "LANGFUSE_S3_SECRET_ACCESS_KEY",
        ):
            assert f"${{{secret}}}" in text, f"{secret} is not interpolated from the environment"
            assert f"${{{secret}:-" not in text, f"{secret} carries an inline default"

    def test_the_env_template_did_not_grow_a_langfuse_key(self) -> None:
        # tests/security/test_openbao_wiring.py pins env.example to the
        # OpenBao pointer; this restates it from the Langfuse side so a later
        # "just add the key to env.example" is caught here too.
        env = (REPO / "env.example").read_text(encoding="utf-8")
        assert "LANGFUSE" not in env.upper()

    def test_vendor_telemetry_is_off(self) -> None:
        # files/08 §9: "no vendor network". Langfuse phones home by default.
        for name in ("langfuse-web", "langfuse-worker"):
            env = _services()[name]["environment"]
            assert env["TELEMETRY_ENABLED"] == "false", f"{name} would phone home"

    def test_the_enterprise_edition_is_not_licensed_in(self) -> None:
        # The published image contains ee/, which is NOT MIT (ee/LICENSE:
        # "may only be used, if you ... have a valid Langfuse Enterprise
        # License"). Without a key those paths stay inert; a key in this file
        # would be an unlicensed commercial use (invariant 19).
        text = COMPOSE_PATH.read_text(encoding="utf-8")
        assert "LANGFUSE_EE_LICENSE_KEY" not in text
        assert "EE_LICENSE" not in text

    def test_the_header_names_hb_l6_and_the_content_posture(self) -> None:
        header = COMPOSE_PATH.read_text(encoding="utf-8")[:4000]
        assert "HB-L6" in header
        assert "INT-175" in header


# =====================================================================================
# 2. The emission boundary — a closed field set, and no carrier for content
# =====================================================================================


class TestSpanShape:
    def test_the_field_set_is_closed_and_frozen(self) -> None:
        assert LLM_SPAN_FIELDS == (
            "work_id",
            "session_id_hash",
            "tenant_id",
            "prompt_version",
            "protocol_hash",
            "model_id",
            "model_revision",
            "kind",
            "outcome",
            "latency_ms",
            "input_tokens",
            "output_tokens",
            "input_chars",
            "output_chars",
            "candidate_flag_count",
            "schema_id",
        )

    def test_no_field_name_could_carry_content(self) -> None:
        for field_name in LLM_SPAN_FIELDS:
            for token in DENIED_FIELD_TOKENS:
                assert token not in field_name, (
                    f"field {field_name!r} contains {token!r} — a content-shaped name is "
                    "how a content-shaped value arrives (HB-L6)"
                )

    def test_lengths_travel_but_the_string_they_measure_does_not(self) -> None:
        span = _valid_span()
        payload = emit_llm_span(span, _RecordingSink())
        assert payload["input_chars"] == 4821
        assert all(not isinstance(value, str) or " " not in value for value in payload.values())

    def test_the_payload_keys_are_exactly_the_closed_field_set(self) -> None:
        sink = _RecordingSink()
        payload = emit_llm_span(_valid_span(), sink)
        assert tuple(payload) == LLM_SPAN_FIELDS
        assert sink.emitted == [("llm.extraction", payload)]

    def test_the_span_is_frozen(self) -> None:
        with pytest.raises(Exception):  # noqa: B017 — dataclasses raise FrozenInstanceError
            _valid_span().work_id = "other"  # type: ignore[misc]


class TestAdversarialContent:
    """Plant the sentence at every seam. It must never reach a payload."""

    @pytest.mark.parametrize(
        "field_name",
        [
            "work_id",
            "session_id_hash",
            "tenant_id",
            "prompt_version",
            "protocol_hash",
            "model_id",
            "model_revision",
            "schema_id",
        ],
    )
    @pytest.mark.parametrize("planted", [TURKISH_SYMPTOM, TURKISH_WITH_TCKN])
    def test_every_string_field_refuses_the_sentence(self, field_name: str, planted: str) -> None:
        with pytest.raises(SpanFieldRefused) as excinfo:
            _valid_span(**{field_name: planted})
        message = str(excinfo.value)
        assert field_name in message, "the refusal must name the field"
        # invariant 6: the refused value is exactly what must not reach a log,
        # and an exception message reaches a log.
        assert planted not in message
        assert "Göğsümde" not in message
        assert "10000000146" not in message

    def test_a_post_construction_mutation_is_caught_at_the_boundary(self) -> None:
        # `frozen=True` is not a security boundary — object.__setattr__ walks
        # straight past it. Re-validating in the serialiser is what makes the
        # boundary hold.
        span = _valid_span()
        object.__setattr__(span, "schema_id", TURKISH_SYMPTOM)
        sink = _RecordingSink()
        with pytest.raises(SpanFieldRefused):
            emit_llm_span(span, sink)
        assert sink.emitted == []

    def test_a_subclass_cannot_smuggle_an_extra_attribute(self) -> None:
        span = _valid_span()
        object.__setattr__(span, "completion", TURKISH_SYMPTOM)
        sink = _RecordingSink()
        payload = emit_llm_span(span, sink)
        assert "completion" not in payload
        assert TURKISH_SYMPTOM not in json.dumps(payload, ensure_ascii=False)

    def test_a_bare_mapping_is_not_an_emittable_span(self) -> None:
        sink = _RecordingSink()
        with pytest.raises(TypeError):
            emit_llm_span({"prompt": TURKISH_SYMPTOM}, sink)  # type: ignore[arg-type]
        assert sink.emitted == []

    def test_the_serialised_payload_never_contains_the_sentence(self) -> None:
        sink = _RecordingSink()
        emit_llm_span(_valid_span(), sink)
        blob = json.dumps(sink.emitted, ensure_ascii=False, default=str)
        assert TURKISH_SYMPTOM not in blob
        assert "ağrı" not in blob


class TestContentModeIsUnreachableByConstruction:
    """Not "off". Absent. A flag someone can flip is not fail-closed."""

    def test_the_emission_module_reads_no_configuration_at_all(self) -> None:
        tokens = _identifier_tokens(SPANS_SRC)
        for switch in ("environ", "getenv", "getenv_bool", "flags", "is_enabled", "settings"):
            assert switch not in tokens, (
                f"spans.py reaches for {switch!r} — a content mode behind a config read "
                "is one operator away from open (HB-L6)"
            )

    def test_no_content_mode_type_or_function_exists(self) -> None:
        import intake_platform.observability.spans as spans_module

        offenders = [
            name
            for name in dir(spans_module)
            if any(token in name.lower() for token in ("raw", "verbatim", "content", "prompt"))
            and not name.startswith("_")
        ]
        assert offenders == [], f"a content-carrying surface exists: {offenders}"

    def test_the_emission_module_imports_nothing_that_holds_a_transcript(self) -> None:
        # The 12 §5 import-boundary shape: what a module cannot import, it
        # cannot accidentally be handed.
        allowed = {
            "__future__",
            "dataclasses",
            "enum",
            "re",
            "collections.abc",
            "typing",
            "prometheus_client",
            "opentelemetry.trace",
        }
        assert _imported_modules(SPANS_SRC) <= allowed, (
            f"unexpected imports: {sorted(_imported_modules(SPANS_SRC) - allowed)}"
        )


# =====================================================================================
# 3. Annotation queues — the mechanism, its access control, and the shut gate
# =====================================================================================


class TestQueueDefinitions:
    def test_the_three_acceptance_queues_exist(self) -> None:
        assert {q.id for q in QUEUES} == {
            QueueId.NOTE_QUALITY,
            QueueId.HALLUCINATION_AUDIT,
            QueueId.FALSE_RED_REVIEW,
        }

    def test_every_queue_declares_a_resolvable_enqueue_scope(self) -> None:
        from intake_platform.consent.registry import resolve_scope

        for definition in QUEUES:
            assert resolve_scope(definition.enqueue_scope).id

    def test_no_queue_has_a_content_scope_and_every_one_names_hb_l6(self) -> None:
        # files/08 §2.6: the files/06 §2 purpose list contains NOTHING that
        # covers staff access to patient content; counsel is asked for a
        # `support_access` explicit-consent purpose. Until then there is no
        # lawful basis to check, so there is nothing to check it against.
        for definition in QUEUES:
            assert definition.requires_clinical_content is True
            assert definition.content_scope is None
            assert definition.content_blocker == "HB-L6"


class TestEnqueueCarriesIdsOnly:
    def test_enqueue_records_a_pointer_and_audits_it(self) -> None:
        chain = _Chain()
        item = enqueue(
            QueueId.HALLUCINATION_AUDIT,
            item_id="aq_00020",
            tenant_id="tenant_acibadem",
            session_id_hash="4d1a9c77b0e2f513",
            work_id="work_0f3a1c",
            span_ref="lf:trace:8b1c0d2e",
            now=datetime(2026, 8, 29, 9, 15, tzinfo=UTC),
            consent=_AllowingConsent(),
            audit=chain,
            actor="svc-learning",
        )
        assert item.queue is QueueId.HALLUCINATION_AUDIT
        assert item.created_at_utc == "2026-08-29T09:15:00Z"
        entries = list(chain.store.entries())
        assert [e.action for e in entries] == ["annotation.enqueue"]
        assert entries[0].consent_scope_ref == queue_def(QueueId.HALLUCINATION_AUDIT).enqueue_scope

    def test_enqueue_refuses_without_the_enqueue_consent_scope(self) -> None:
        chain = _Chain()
        from intake_platform.observability.annotation import ConsentScopeRefused

        with pytest.raises(ConsentScopeRefused):
            enqueue(
                QueueId.NOTE_QUALITY,
                item_id="aq_00021",
                tenant_id="tenant_acibadem",
                session_id_hash="4d1a9c77b0e2f513",
                work_id="work_0f3a1c",
                span_ref="lf:trace:8b1c0d2e",
                now=datetime(2026, 8, 29, 9, 15, tzinfo=UTC),
                consent=_DenyingConsent(),
                audit=chain,
                actor="svc-learning",
            )
        # invariant 4: a denial is a signal, and it is audited too
        assert [e.action for e in chain.store.entries()] == ["annotation.enqueue.refused"]

    @pytest.mark.parametrize(
        "field_name", ["item_id", "tenant_id", "session_id_hash", "work_id", "span_ref"]
    )
    def test_a_queue_item_field_refuses_the_sentence(self, field_name: str) -> None:
        with pytest.raises(SpanFieldRefused):
            _item(**{field_name: TURKISH_SYMPTOM})


class TestContentReadFailsClosed:
    def test_the_only_outcome_of_a_content_read_is_a_refusal(self) -> None:
        chain = _Chain()
        decision = authorize_content_read(
            _item(), actor="dr.kaya", role=ReviewerRole.CLINICAL_LEAD, audit=chain
        )
        assert isinstance(decision, ContentReadRefused)
        assert decision.blocker_id == "HB-L6"

    def test_no_granted_counterpart_type_exists(self) -> None:
        import intake_platform.observability.annotation as annotation_module

        offenders = [
            name
            for name in dir(annotation_module)
            if any(token in name.lower() for token in ("granted", "allowed", "opened", "raw"))
            and not name.startswith("_")
        ]
        assert offenders == [], (
            f"a granted-read surface exists, so the gate is a branch and not a wall: {offenders}"
        )

    def test_the_signature_can_only_return_a_refusal(self) -> None:
        assert authorize_content_read.__annotations__["return"] == "ContentReadRefused"

    def test_the_refusal_object_carries_no_handle_to_content(self) -> None:
        decision = authorize_content_read(
            _item(), actor="dr.kaya", role=ReviewerRole.CLINICAL_LEAD, audit=_Chain()
        )
        for field_name in decision.__dataclass_fields__:
            for token in DENIED_FIELD_TOKENS:
                assert token not in field_name

    def test_the_audit_row_is_written_before_the_decision_is_returned(self) -> None:
        # files/08 §2.5 item 6: "The audit row is written **before** the read."
        chain = _Chain()
        seen_before: list[int] = []

        class _Watching:
            def append(self, **kwargs: str) -> object:
                seen_before.append(len(list(chain.store.entries())))
                return chain.append(**kwargs)

        authorize_content_read(
            _item(), actor="dr.kaya", role=ReviewerRole.CLINICAL_LEAD, audit=_Watching()
        )
        assert seen_before == [0], "nothing may precede the audit row"
        entries = list(chain.store.entries())
        assert [e.action for e in entries] == ["annotation.content_read.refused"]
        assert entries[0].consent_scope_ref == "HB-L6"

    def test_the_annotation_module_reads_no_configuration_either(self) -> None:
        tokens = _identifier_tokens(ANNOTATION_SRC)
        for switch in ("environ", "getenv", "flags", "is_enabled", "settings"):
            assert switch not in tokens


class TestReviewLabelsCarryNoFreeText:
    def test_a_permitted_role_may_record_a_closed_label(self) -> None:
        chain = _Chain()
        review = record_review(
            _item(),
            actor="dr.kaya",
            role=ReviewerRole.CLINICIAN,
            label=Label.EDIT,
            section_reason=SectionReason.MEDICATIONS,
            now=datetime(2026, 8, 29, 10, 0, tzinfo=UTC),
            audit=chain,
        )
        assert review.label is Label.EDIT
        assert [e.action for e in chain.store.entries()] == ["annotation.review"]

    def test_a_role_outside_the_queue_is_refused_and_audited(self) -> None:
        from intake_platform.observability.annotation import ReviewerRoleRefused

        chain = _Chain()
        with pytest.raises(ReviewerRoleRefused):
            record_review(
                _item(),
                actor="ops.engineer",
                role=ReviewerRole.COMPLIANCE_OFFICER,
                label=Label.ACCEPT,
                section_reason=SectionReason.MEDICATIONS,
                now=datetime(2026, 8, 29, 10, 0, tzinfo=UTC),
                audit=chain,
            )
        assert [e.action for e in chain.store.entries()] == ["annotation.review.refused"]

    def test_the_reason_is_a_closed_enum_so_the_sentence_has_no_carrier(self) -> None:
        with pytest.raises(ValueError, match="section_reason"):
            record_review(
                _item(),
                actor="dr.kaya",
                role=ReviewerRole.CLINICIAN,
                label=Label.EDIT,
                section_reason=TURKISH_SYMPTOM,  # type: ignore[arg-type]
                now=datetime(2026, 8, 29, 10, 0, tzinfo=UTC),
                audit=_Chain(),
            )


# =====================================================================================
# 4. The recorded-experiment gate
# =====================================================================================


def _record(**overrides: Any) -> ExperimentRecord:
    base: dict[str, Any] = {
        "case_id": "sim_chest_pain_001",
        "kind": SpanKind.EXTRACTION,
        "outcome": SpanOutcome.OK,
        "schema_valid": True,
        "required_slots_filled": 6,
        "required_slots_total": 6,
        "llm_triage_level": "candidate_flag",
        "policyguard_pass": True,
        "latency_ms": 900,
    }
    base.update(overrides)
    return ExperimentRecord(**base)


class TestExperimentGate:
    def test_the_committed_recorded_run_loads_and_passes_the_committed_thresholds(self) -> None:
        records = load_records(RECORDED_RUN)
        assert len(records) >= 10, "a gate over three cases gates nothing"
        result = gate(score(records), load_thresholds(THRESHOLDS_PATH))
        assert isinstance(result, GateResult)
        assert result.passed, result.failures

    def test_a_run_carrying_a_transcript_is_refused_not_scrubbed(self, tmp_path: Path) -> None:
        path = tmp_path / "leaky.jsonl"
        row = {
            "case_id": "sim_chest_pain_001",
            "kind": "extraction",
            "outcome": "ok",
            "schema_valid": True,
            "required_slots_filled": 6,
            "required_slots_total": 6,
            "llm_triage_level": "candidate_flag",
            "policyguard_pass": True,
            "latency_ms": 900,
            "transcript": TURKISH_SYMPTOM,
        }
        path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
        with pytest.raises(RecordRefused) as excinfo:
            load_records(path)
        assert TURKISH_SYMPTOM not in str(excinfo.value)

    def test_a_run_whose_string_field_is_a_sentence_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "sentence.jsonl"
        row = {
            "case_id": TURKISH_SYMPTOM,
            "kind": "extraction",
            "outcome": "ok",
            "schema_valid": True,
            "required_slots_filled": 6,
            "required_slots_total": 6,
            "llm_triage_level": "candidate_flag",
            "policyguard_pass": True,
            "latency_ms": 900,
        }
        path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
        with pytest.raises(RecordRefused):
            load_records(path)

    def test_an_llm_produced_red_fails_the_gate_regardless_of_thresholds(self) -> None:
        # invariant 1: RED/YELLOW come from packages/protocols/triage alone.
        result = gate(
            score([_record(), _record(case_id="sim_002", llm_triage_level="RED")]),
            load_thresholds(THRESHOLDS_PATH),
        )
        assert not result.passed
        assert any("invariant 1" in failure for failure in result.failures)

    def test_a_schema_regression_fails_the_gate_and_names_the_score(self) -> None:
        records = [_record(case_id=f"sim_{n:03d}", schema_valid=n % 2 == 0) for n in range(10)]
        result = gate(score(records), load_thresholds(THRESHOLDS_PATH))
        assert not result.passed
        assert any("schema_valid_ratio" in failure for failure in result.failures)

    def test_a_latency_regression_fails_the_gate(self) -> None:
        records = [_record(case_id=f"sim_{n:03d}", latency_ms=60_000) for n in range(10)]
        result = gate(score(records), load_thresholds(THRESHOLDS_PATH))
        assert not result.passed
        assert any("latency" in failure for failure in result.failures)

    def test_the_committed_thresholds_validate(self) -> None:
        thresholds = load_thresholds(THRESHOLDS_PATH)
        assert isinstance(thresholds, Thresholds)
        assert 0.0 < thresholds.min_schema_valid_ratio <= 1.0

    def test_the_cli_exits_zero_on_the_recorded_run_and_prints_no_content(self) -> None:
        completed = subprocess.run(  # noqa: S603 — fixed argv, our own script
            [
                sys.executable,
                str(EXPERIMENT_CLI),
                "--run",
                str(RECORDED_RUN),
                "--thresholds",
                str(THRESHOLDS_PATH),
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=REPO,
        )
        assert completed.returncode == 0, completed.stderr
        assert "schema_valid_ratio" in completed.stdout
        assert TURKISH_SYMPTOM not in completed.stdout + completed.stderr

    def test_the_cli_exits_nonzero_when_the_gate_fails(self, tmp_path: Path) -> None:
        thresholds = tmp_path / "impossible.yaml"
        thresholds.write_text(
            yaml.safe_dump(
                {
                    "min_schema_valid_ratio": 1.0,
                    "min_slot_fill_ratio": 1.0,
                    "min_policyguard_pass_ratio": 1.0,
                    "max_latency_p95_ms": 1,
                }
            ),
            encoding="utf-8",
        )
        completed = subprocess.run(  # noqa: S603 — fixed argv, our own script
            [
                sys.executable,
                str(EXPERIMENT_CLI),
                "--run",
                str(RECORDED_RUN),
                "--thresholds",
                str(thresholds),
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=REPO,
        )
        assert completed.returncode == 1


# =====================================================================================
# 5. Invariant 15 + 19 — the registry row, the licence provenance, the probe, the SLO
# =====================================================================================


class TestOperabilityContract:
    def test_langfuse_is_in_the_self_hosting_registry(self) -> None:
        entry = load_registry(REGISTRY_PATH).get("langfuse")
        assert entry.self_hostable is True
        assert entry.probe.value == "http_health"

    def test_the_licence_is_verified_from_a_named_hashed_blob(self) -> None:
        # invariant 19: never a badge, never a card tag. The row must record
        # which bytes were read so an auditor can re-read them.
        entry = load_registry(REGISTRY_PATH).get("langfuse")
        assert entry.licence_verified_at is not None
        assert entry.licence_blob_url is not None
        assert entry.licence_blob_url.startswith("https://raw.githubusercontent.com/")
        assert entry.licence_blob_sha256 == (
            "fd09d42b5b16606ad2042cc1edf3a82da1c47743709f170c959c74758af229d6"
        )

    def test_the_row_records_the_enterprise_carve_out(self) -> None:
        # "MIT" alone would be a laundered claim: ee/ is commercially
        # licensed, and the shipped image contains it.
        entry = load_registry(REGISTRY_PATH).get("langfuse")
        assert entry.licence_note is not None
        assert "ee/LICENSE" in entry.licence_note
        assert "760f5202be4f31f9f8ca43a3c558bebaa5187fa7d7eccad6a32de8392cdccee6" in (
            entry.licence_note
        )

    def test_clickhouse_is_registered_with_its_own_verified_blob(self) -> None:
        entry = load_registry(REGISTRY_PATH).get("langfuse-clickhouse")
        assert entry.license.startswith("Apache-2.0")
        assert entry.licence_blob_sha256 == (
            "e276e9cd356772864ed82575f081ef1b8225914c3ac39a03c9112821a7e33f62"
        )

    def test_the_registry_row_states_why_it_is_not_on_the_phi_path(self) -> None:
        entry = load_registry(REGISTRY_PATH).get("langfuse")
        assert entry.phi_path is False
        text = REGISTRY_PATH.read_text(encoding="utf-8")
        assert "HB-L6" in text, "the row must name the blocker that keeps content out"

    def test_the_probe_is_wired_when_its_target_exists(self) -> None:
        registry = load_registry(REGISTRY_PATH)
        without = build_dev_clients(registry, DevProbeConfig(env={}))
        assert "langfuse" not in without, (
            "a probe with no target must be visibly SKIPPED, not faked"
        )
        with_target = build_dev_clients(
            registry,
            DevProbeConfig(
                env={"INTAKE_LANGFUSE_HEALTH_URL": "http://127.0.0.1:3030/api/public/health"}
            ),
        )
        assert "langfuse" in with_target

    def test_the_slo_file_exists_validates_and_matches_its_filename(self) -> None:
        slo_file = load_slo_file(SLO_PATH)
        assert slo_file.service == "langfuse"
        assert slo_file.slos

    def test_the_slo_references_only_catalogued_metrics(self) -> None:
        catalog = load_metrics_catalog(CATALOG_PATH)
        for slo in load_slo_file(SLO_PATH).slos:
            assert catalog.unknown_references(slo.sli) == frozenset()

    def test_the_emitted_families_are_catalogued(self) -> None:
        catalog = load_metrics_catalog(CATALOG_PATH)
        for name in (
            "llm_trace_spans_emitted_total",
            "llm_trace_fields_refused_total",
            "annotation_queue_enqueued_total",
            "annotation_content_reads_refused_total",
        ):
            assert catalog.covers(name), f"{name} is emitted but not catalogued (inv. 13)"

    def test_the_makefile_exposes_the_tier_and_the_gate(self) -> None:
        makefile = (REPO / "Makefile").read_text(encoding="utf-8")
        for target in ("langfuse:", "langfuse-down:", "langfuse-experiment:"):
            assert f"\n{target}" in makefile, f"missing Makefile target {target}"


# =====================================================================================
# 6. The refusal branches — every guard exercised, because an unexercised guard is
#    a guard nobody has seen refuse
# =====================================================================================


class TestSpanGuardBranches:
    @pytest.mark.parametrize(
        "field_name",
        [
            "latency_ms",
            "input_tokens",
            "output_tokens",
            "input_chars",
            "output_chars",
            "candidate_flag_count",
        ],
    )
    @pytest.mark.parametrize("bad", [-1, True, "812", 1.5])
    def test_count_fields_take_non_negative_ints_only(self, field_name: str, bad: Any) -> None:
        # `True` is listed on purpose: bool is an int subclass in Python, and a
        # boolean silently counted as 1 is a metric that lies.
        with pytest.raises(SpanFieldRefused, match=field_name):
            _valid_span(**{field_name: bad})

    def test_kind_and_outcome_must_be_enum_members(self) -> None:
        with pytest.raises(SpanFieldRefused, match="kind"):
            _valid_span(kind="extraction")
        with pytest.raises(SpanFieldRefused, match="outcome"):
            _valid_span(outcome="ok")

    def test_the_otel_sink_sets_one_attribute_per_field(self) -> None:
        from intake_platform.observability.spans import OtelSpanSink

        recorded: dict[str, Any] = {}

        class _Span:
            def set_attribute(self, key: str, value: Any) -> None:
                recorded[key] = value

            def __enter__(self) -> _Span:
                return self

            def __exit__(self, *exc: object) -> None:
                return None

        class _Tracer:
            started: list[str] = []

            def start_as_current_span(self, name: str) -> _Span:
                _Tracer.started.append(name)
                return _Span()

        sink = OtelSpanSink(_Tracer())  # type: ignore[arg-type]
        payload = emit_llm_span(_valid_span(), sink)
        assert _Tracer.started == ["llm.extraction"]
        assert recorded == dict(payload)


class TestQueueListingAndGuards:
    def test_pending_items_filters_by_queue_and_keeps_order(self) -> None:
        from intake_platform.observability.annotation import pending_items

        first = _item(item_id="aq_1")
        second = _item(item_id="aq_2", queue=QueueId.FALSE_RED_REVIEW)
        third = _item(item_id="aq_3")
        listed = pending_items([first, second, third], QueueId.NOTE_QUALITY)
        assert [i.item_id for i in listed] == ["aq_1", "aq_3"]

    def test_a_queue_item_needs_a_real_queue_id(self) -> None:
        with pytest.raises(ValueError, match="queue"):
            _item(queue="note_quality")

    def test_a_label_must_be_a_label_member(self) -> None:
        with pytest.raises(ValueError, match="label"):
            record_review(
                _item(),
                actor="dr.kaya",
                role=ReviewerRole.CLINICIAN,
                label="edit",  # type: ignore[arg-type]
                section_reason=SectionReason.SUMMARY,
                now=datetime(2026, 8, 29, 10, 0, tzinfo=UTC),
                audit=_Chain(),
            )

    def test_a_naive_timestamp_is_refused(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            enqueue(
                QueueId.NOTE_QUALITY,
                item_id="aq_00022",
                tenant_id="tenant_acibadem",
                session_id_hash="4d1a9c77b0e2f513",
                work_id="work_0f3a1c",
                span_ref="lf:trace:8b1c0d2e",
                now=datetime(2026, 8, 29, 9, 15),  # noqa: DTZ001 — the point of the test
                consent=_AllowingConsent(),
                audit=_Chain(),
                actor="svc-learning",
            )

    def test_queue_def_resolves_every_member(self) -> None:
        for queue in QueueId:
            assert queue_def(queue).id is queue


class TestRecordedRunGuards:
    def _write(self, tmp_path: Path, payload: str) -> Path:
        path = tmp_path / "run.jsonl"
        path.write_text(payload, encoding="utf-8")
        return path

    def test_a_non_json_line_is_refused_by_line_number(self, tmp_path: Path) -> None:
        with pytest.raises(RecordRefused, match="line 1"):
            load_records(self._write(tmp_path, "{not json\n"))

    def test_a_json_scalar_line_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(RecordRefused, match="not a JSON object"):
            load_records(self._write(tmp_path, "42\n"))

    def test_a_missing_key_is_named(self, tmp_path: Path) -> None:
        with pytest.raises(RecordRefused, match="missing"):
            load_records(self._write(tmp_path, json.dumps({"case_id": "sim_1"}) + "\n"))

    def test_an_empty_file_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(RecordRefused, match="no records"):
            load_records(self._write(tmp_path, "\n\n"))

    def _row(self, **overrides: Any) -> str:
        base: dict[str, Any] = {
            "case_id": "sim_1",
            "kind": "extraction",
            "outcome": "ok",
            "schema_valid": True,
            "required_slots_filled": 6,
            "required_slots_total": 6,
            "llm_triage_level": "none",
            "policyguard_pass": True,
            "latency_ms": 900,
        }
        base.update(overrides)
        return json.dumps(base) + "\n"

    def test_a_non_boolean_flag_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(RecordRefused, match="schema_valid"):
            load_records(self._write(tmp_path, self._row(schema_valid="yes")))

    def test_a_non_integer_count_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(RecordRefused, match="latency_ms"):
            load_records(self._write(tmp_path, self._row(latency_ms="900")))

    def test_an_unknown_enum_value_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(RecordRefused, match="kind"):
            load_records(self._write(tmp_path, self._row(kind="rerank")))

    def test_a_non_string_enum_value_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(RecordRefused, match="outcome"):
            load_records(self._write(tmp_path, self._row(outcome=3)))

    def test_slot_counts_must_be_coherent(self, tmp_path: Path) -> None:
        with pytest.raises(RecordRefused, match="required_slots_total"):
            load_records(self._write(tmp_path, self._row(required_slots_total=0)))
        with pytest.raises(RecordRefused, match="required_slots_filled"):
            load_records(self._write(tmp_path, self._row(required_slots_filled=9)))

    def test_a_negative_latency_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(RecordRefused, match="latency_ms"):
            load_records(self._write(tmp_path, self._row(latency_ms=-1)))

    def test_scoring_an_empty_run_is_refused(self) -> None:
        with pytest.raises(RecordRefused, match="empty run"):
            score([])


class TestThresholdGuards:
    def _write(self, tmp_path: Path, payload: Any) -> Path:
        path = tmp_path / "t.yaml"
        path.write_text(yaml.safe_dump(payload), encoding="utf-8")
        return path

    def test_a_non_mapping_document_is_refused(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, [1, 2])
        with pytest.raises(RecordRefused, match="mapping"):
            load_thresholds(path)

    def test_an_unknown_threshold_key_is_refused(self, tmp_path: Path) -> None:
        payload = {
            "min_schema_valid_ratio": 0.9,
            "min_slot_fill_ratio": 0.85,
            "min_policyguard_pass_ratio": 1.0,
            "max_latency_p95_ms": 5000,
            "min_vibes": 0.5,
        }
        with pytest.raises(RecordRefused, match="unknown keys"):
            load_thresholds(self._write(tmp_path, payload))

    @pytest.mark.parametrize("ratio", [0.0, 1.5])
    def test_a_ratio_outside_the_unit_interval_is_refused(
        self, tmp_path: Path, ratio: float
    ) -> None:
        payload = {
            "min_schema_valid_ratio": ratio,
            "min_slot_fill_ratio": 0.85,
            "min_policyguard_pass_ratio": 1.0,
            "max_latency_p95_ms": 5000,
        }
        with pytest.raises(RecordRefused, match="min_schema_valid_ratio"):
            load_thresholds(self._write(tmp_path, payload))

    def test_a_non_positive_latency_bar_is_refused(self, tmp_path: Path) -> None:
        payload = {
            "min_schema_valid_ratio": 0.9,
            "min_slot_fill_ratio": 0.85,
            "min_policyguard_pass_ratio": 1.0,
            "max_latency_p95_ms": 0,
        }
        with pytest.raises(RecordRefused, match="max_latency_p95_ms"):
            load_thresholds(self._write(tmp_path, payload))

    def test_a_slot_fill_regression_fails_the_gate(self) -> None:
        records = [
            _record(case_id=f"sim_{n:03d}", required_slots_filled=1, required_slots_total=6)
            for n in range(10)
        ]
        result = gate(score(records), load_thresholds(THRESHOLDS_PATH))
        assert not result.passed
        assert any("slot_fill_ratio" in failure for failure in result.failures)

    def test_a_policyguard_block_fails_the_gate(self) -> None:
        records = [_record(case_id=f"sim_{n:03d}", policyguard_pass=n > 0) for n in range(10)]
        result = gate(score(records), load_thresholds(THRESHOLDS_PATH))
        assert not result.passed
        assert any("policyguard_pass_ratio" in failure for failure in result.failures)

    def test_scores_render_as_rounded_json_ready_values(self) -> None:
        # what the CLI prints, asserted in-process: the subprocess test above
        # proves the exit code, this proves the shape and the rounding.
        rendered = score(load_records(RECORDED_RUN)).as_dict()
        assert rendered == {
            "cases": 20,
            "schema_valid_ratio": 0.95,
            "slot_fill_ratio": 0.903,
            "policyguard_pass_ratio": 1.0,
            "latency_p95_ms": 2260,
            "llm_triage_violations": [],
        }
