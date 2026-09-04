"""INT-320 — the /embed/v1 handshake routes over the real app (ADR-029).

Exercised through the api unit-lane harness (SQLite DDL clone, real audit
chain). What this pins:
- the full happy path: an admin (the dev stand-in for a partner backend) mints
  a ticket, and a device launches it to get the branded context;
- the mint is authenticated and admin-only; a patient token cannot mint;
- unknown tenant, missing signing key and a replayed/tampered/malformed ticket
  each fail closed with an id-shaped code and NO token content;
- the whole surface answers 503 when the embed wiring is absent;
- both routes carry the partner_embed marker and the consent scan stays green;
- the handshake writes hash-chained audit entries and no clinical data.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from api_harness import ADMIN_TOKEN, PATIENT_TOKEN, ApiHarness, build_harness
from intake_api.consent_guard import partner_embed_routes, unguarded_data_routes
from intake_api.embed.service import EmbedWiring, MappingSigningKeys
from intake_platform.consent import ConsentTextCatalog
from intake_platform.embed import InMemoryNonceStore, load_shipped_registry

DEV_TENANT = "0b6f9d2e-1111-5aaa-8bbb-000000000001"
DEV_KEY_REF = "embed/dev-partner-alpha/signing-key"
DEV_DOC_SET = "embed.dev-partner-alpha"
TEST_KEY = b"unit-lane-embed-signing-key-32byte"
LAUNCH_BASE = "https://intake.app/embed/launch"

_CORE = """---
consent_text_version: v1-demo.1
---
Temel hizmet

Muayeneden önce şikâyetlerinizi toplar ve hekiminize düzenli bir ön not iletiriz.
"""

_DISCLOSURE = """---
consent_text_version: v1-demo.1
---
Ortak üzerinden giriş

Bu ön görüşmeyi ortağınız üzerinden başlattınız. Verileriniz, ortağınız adına
Vizite tarafından işlenir.
"""


def _wiring(
    *,
    keys: dict[str, bytes] | None = None,
    consent_catalog: ConsentTextCatalog | None = None,
    legal_base: Path | None = None,
) -> EmbedWiring:
    return EmbedWiring(
        registry=load_shipped_registry(),
        signing_keys=MappingSigningKeys(keys if keys is not None else {DEV_KEY_REF: TEST_KEY}),
        launch_base_url=LAUNCH_BASE,
        nonce_store=InMemoryNonceStore(),
        consent_catalog=consent_catalog,
        legal_base=legal_base,
    )


def _author_dev_legal(base: Path) -> Path:
    """Author the dev embed consent set under a dev-legal base: the global
    ``core`` service consent and the tenant's partner-processor disclosure at
    the path its committed ``legal_root`` (docs/legal/embed/dev-partner-alpha)
    resolves to under this base. Returns the global consents dir."""
    consents = base / "consents"
    consents.mkdir(parents=True, exist_ok=True)
    (consents / "core.tr.md").write_text(_CORE, encoding="utf-8")
    disclosure_root = base / "embed" / "dev-partner-alpha"
    disclosure_root.mkdir(parents=True, exist_ok=True)
    (disclosure_root / "partner_processor.tr.md").write_text(_DISCLOSURE, encoding="utf-8")
    return consents


@pytest.fixture()
def embed_harness(tmp_path: Path) -> Iterator[ApiHarness]:
    yield from build_harness(
        tmp_path, token_patient=PATIENT_TOKEN, token_admin=ADMIN_TOKEN, embed=_wiring()
    )


@pytest.fixture()
def unconfigured_embed_harness(tmp_path: Path) -> Iterator[ApiHarness]:
    yield from build_harness(
        tmp_path, token_patient=PATIENT_TOKEN, token_admin=ADMIN_TOKEN, embed=None
    )


def _mint(h: ApiHarness, tenant: str = DEV_TENANT) -> object:
    return h.client.post("/embed/v1/launch-tickets", json={"tenant_id": tenant}, headers=h.admin())


def test_mint_then_launch_happy_path(embed_harness: ApiHarness) -> None:
    minted = _mint(embed_harness)
    assert minted.status_code == 200, minted.text
    body = minted.json()
    assert body["ticket"] and body["launch_url"].startswith(LAUNCH_BASE)
    # the ticket rides in the URL fragment, not the query — never in a log
    assert "#ticket=" in body["launch_url"]

    launched = embed_harness.client.post("/embed/v1/launch", json={"ticket": body["ticket"]})
    assert launched.status_code == 200, launched.text
    ctx = launched.json()
    assert ctx["tenant_id"] == DEV_TENANT
    assert ctx["theme"]["display_name"] == "Vizite Dev Partner"
    assert ctx["theme"]["primary_color"] == "#0B5FFF"
    assert ctx["consent_doc_set_id"] == "embed.dev-partner-alpha"
    assert ctx["device_functions"] is False


def test_mint_is_admin_only(embed_harness: ApiHarness) -> None:
    patient = embed_harness.client.post(
        "/embed/v1/launch-tickets", json={"tenant_id": DEV_TENANT}, headers=embed_harness.patient()
    )
    assert patient.status_code == 403
    anon = embed_harness.client.post("/embed/v1/launch-tickets", json={"tenant_id": DEV_TENANT})
    assert anon.status_code == 401


def test_mint_unknown_tenant_fails_closed(embed_harness: ApiHarness) -> None:
    resp = _mint(embed_harness, tenant="99999999-9999-5999-8999-999999999999")
    assert resp.status_code == 404
    assert resp.json() == {"error": "unknown_embed_tenant"}


def test_mint_without_a_signing_key_is_503(tmp_path: Path) -> None:
    gen = build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        embed=_wiring(keys={}),  # registered tenant, no key available
    )
    harness = next(gen)
    try:
        resp = _mint(harness)
        assert resp.status_code == 503
        assert resp.json() == {"error": "embed_signing_key_unavailable"}
    finally:
        gen.close()


def test_launch_is_single_use(embed_harness: ApiHarness) -> None:
    ticket = _mint(embed_harness).json()["ticket"]
    assert embed_harness.client.post("/embed/v1/launch", json={"ticket": ticket}).status_code == 200
    replay = embed_harness.client.post("/embed/v1/launch", json={"ticket": ticket})
    assert replay.status_code == 400
    assert replay.json() == {"error": "embed_ticket_refused", "reason": "replayed"}


def test_launch_tampered_ticket_fails_closed(embed_harness: ApiHarness) -> None:
    ticket = _mint(embed_harness).json()["ticket"]
    head, payload, _sig = ticket.split(".")
    resp = embed_harness.client.post(
        "/embed/v1/launch", json={"ticket": f"{head}.{payload}.{'A' * 43}"}
    )
    assert resp.status_code == 400
    assert resp.json()["reason"] == "signature"


def test_launch_malformed_ticket_fails_closed(embed_harness: ApiHarness) -> None:
    resp = embed_harness.client.post("/embed/v1/launch", json={"ticket": "not-a-ticket"})
    assert resp.status_code == 400
    assert resp.json()["reason"] == "malformed"


def test_unconfigured_surface_answers_503(unconfigured_embed_harness: ApiHarness) -> None:
    h = unconfigured_embed_harness
    mint = h.client.post(
        "/embed/v1/launch-tickets", json={"tenant_id": DEV_TENANT}, headers=h.admin()
    )
    assert mint.status_code == 503
    assert mint.json() == {"error": "embed_unconfigured"}
    launch = h.client.post("/embed/v1/launch", json={"ticket": "x.y.z"})
    assert launch.status_code == 503


def test_embed_routes_carry_the_marker_and_scan_stays_green(embed_harness: ApiHarness) -> None:
    app = embed_harness.client.app
    assert unguarded_data_routes(app) == []
    assert partner_embed_routes(app) == [
        "POST /embed/v1/consent",
        "POST /embed/v1/launch",
        "POST /embed/v1/launch-tickets",
    ]


def test_launch_then_consent_render_in_dev(tmp_path: Path) -> None:
    """The end-to-end dev path: mint → launch → the consent step returns the
    hash-bound document set (no longer 503/empty) once the dev texts are
    authored and the tenant key is seeded (here the unit-lane MappingSigningKeys
    stands in for the seeded OpenBao key)."""
    base = tmp_path / "dev-legal"
    consents = _author_dev_legal(base)
    gen = build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        legal_root=consents,
        embed=_wiring(consent_catalog=ConsentTextCatalog(consents), legal_base=base),
    )
    harness = next(gen)
    try:
        minted = _mint(harness)
        assert minted.status_code == 200, minted.text
        launched = harness.client.post("/embed/v1/launch", json={"ticket": minted.json()["ticket"]})
        assert launched.status_code == 200, launched.text
        doc_set_id = launched.json()["consent_doc_set_id"]
        assert doc_set_id == DEV_DOC_SET

        rendered = harness.client.post(
            "/embed/v1/consent",
            json={"tenant_id": DEV_TENANT, "consent_doc_set_id": doc_set_id},
        )
        assert rendered.status_code == 200, rendered.text
        body = rendered.json()
        assert body["consent_doc_set_id"] == DEV_DOC_SET
        by_id = {d["doc_id"]: d for d in body["documents"]}
        # the patient sees BOTH the grantable core consent and the disclosure
        assert by_id["core"]["kind"] == "consent"
        assert by_id["core"]["grant_scope"] == "core"
        assert len(by_id["core"]["text_hash"]) == 64
        assert by_id["partner_processor"]["kind"] == "disclosure"
        assert by_id["partner_processor"]["grant_scope"] is None
        assert "işlenir" in by_id["partner_processor"]["body"]
        # the render is audited, ids only (never a token or copy)
        rendered_entries = [
            e for e in harness.audit_store.entries() if e.action == "embed.consent_rendered"
        ]
        assert rendered_entries
        assert rendered_entries[0].resource_ref == f"tenant:{DEV_TENANT}"
        assert rendered_entries[0].consent_scope_ref == "basis:embed-handshake"
    finally:
        gen.close()


def test_consent_render_fails_closed_when_texts_unauthored(tmp_path: Path) -> None:
    """STAYS fail closed for an unauthored tenant: the consent catalogue is
    wired but the tenant's disclosure is not authored (the pre-sign-off state,
    HB-L27), so the consent step answers 503, never an empty consent
    (invariant 18)."""
    base = tmp_path / "dev-legal"
    consents = base / "consents"
    consents.mkdir(parents=True, exist_ok=True)
    (consents / "core.tr.md").write_text(_CORE, encoding="utf-8")
    # the tenant's partner-processor disclosure is deliberately NOT authored
    gen = build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        legal_root=consents,
        embed=_wiring(consent_catalog=ConsentTextCatalog(consents), legal_base=base),
    )
    harness = next(gen)
    try:
        resp = harness.client.post(
            "/embed/v1/consent",
            json={"tenant_id": DEV_TENANT, "consent_doc_set_id": DEV_DOC_SET},
        )
        assert resp.status_code == 503
        assert resp.json() == {"error": "embed_consent_unavailable"}
    finally:
        gen.close()


def test_consent_render_is_503_when_the_render_is_unconfigured(
    embed_harness: ApiHarness,
) -> None:
    """No consent catalogue wired at all (the default harness embed wiring) →
    the consent step is unconfigured and fails closed rather than answering
    with no documents."""
    resp = embed_harness.client.post(
        "/embed/v1/consent",
        json={"tenant_id": DEV_TENANT, "consent_doc_set_id": DEV_DOC_SET},
    )
    assert resp.status_code == 503
    assert resp.json() == {"error": "embed_consent_unavailable"}


def test_consent_render_rejects_a_mismatched_doc_set(tmp_path: Path) -> None:
    """A doc-set id that is not the one bound to the tenant's row is refused —
    no peek at another tenant's consent set (tenant isolation, invariant 14)."""
    base = tmp_path / "dev-legal"
    consents = _author_dev_legal(base)
    gen = build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        legal_root=consents,
        embed=_wiring(consent_catalog=ConsentTextCatalog(consents), legal_base=base),
    )
    harness = next(gen)
    try:
        resp = harness.client.post(
            "/embed/v1/consent",
            json={"tenant_id": DEV_TENANT, "consent_doc_set_id": "embed.some-other-tenant"},
        )
        assert resp.status_code == 503
        assert resp.json() == {"error": "embed_consent_unavailable"}
    finally:
        gen.close()


def test_consent_render_unknown_tenant_fails_closed(embed_harness: ApiHarness) -> None:
    resp = embed_harness.client.post(
        "/embed/v1/consent",
        json={
            "tenant_id": "99999999-9999-5999-8999-999999999999",
            "consent_doc_set_id": DEV_DOC_SET,
        },
    )
    assert resp.status_code == 404
    assert resp.json() == {"error": "unknown_embed_tenant"}


def test_handshake_writes_audit_entries(embed_harness: ApiHarness) -> None:
    ticket = _mint(embed_harness).json()["ticket"]
    embed_harness.client.post("/embed/v1/launch", json={"ticket": ticket})
    entries = [e for e in embed_harness.audit_store.entries() if e.action.startswith("embed.")]
    by_action = {e.action: e for e in entries}
    assert by_action["embed.ticket_minted"].resource_ref == f"tenant:{DEV_TENANT}"
    assert by_action["embed.launched"].resource_ref.startswith("embed_launch:")
    # audit carries ids only — a tenant id and a launch nonce, never a token
    for e in entries:
        assert e.consent_scope_ref == "basis:embed-handshake"
