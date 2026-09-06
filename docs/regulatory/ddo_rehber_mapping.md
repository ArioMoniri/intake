# DDO Rehber control mapping — public-hospital (tr-residency) pack

**Source framework.** *Bilgi ve İletişim Güvenliği Rehberi* — the Information
and Communication Security Guide published by the Cumhurbaşkanlığı Dijital
Dönüşüm Ofisi (DDO). `files/10 §6` names it as a framework INTAKE maps to *"for
public-hospital tenants"*, alongside OWASP ASVS, ISO/IEC 27001:2022 + 27701 and
the KVKK Board's adequate-technical-measures.

**What this document is, and is not.** It maps INTAKE's *implemented* controls
to the Rehber's control **domains**, and cites the committed artefact that
implements each. It does **not** quote or paraphrase specific Rehber measure
numbers: the Rehber's clause text and numbering must be read from a committed
verbatim snapshot, and none lives in this repository. Paraphrasing a regulatory
requirement from memory is the same failure mode as inventing a clinical
threshold — authoritative to every later reader, with no diff that makes it look
wrong (files/HUMAN_BLOCKERS.md Rule 1; HB-A12 records the same discipline for
store artefacts). So clause-level conformance assertions are marked
`awaiting-human` against the blocker that owns them, and the rows below assert
only what a committed file already proves.

**No performance figure appears here** (CLAUDE.md invariant 20). This tree is
scanned by the claims gate (`packages/intake_platform/.../legal/claims.py`).

---

## A. Derivable rows — mapped to a committed control

Each row states a Rehber control **domain**, the INTAKE control that addresses
it, and the committed artefact an auditor can read. "Implemented" here means the
mechanism is committed and tested; it does **not** by itself assert clause-level
conformance to the Rehber, which is section C.

| Rehber control domain | INTAKE control | committed artefact | status |
|---|---|---|---|
| Ağ ve sistem güvenliği — dış bağlantı denetimi (egress) | Default-deny egress allow-list; the PHI-path tier reaches no external model or speech vendor; resolve-once-and-pin against SSRF | `infra/security/egress-allowlist.yaml`; `packages/intake_platform/src/intake_platform/egress.py` | implemented |
| Yerli barındırma / bulut bağımsızlığı (self-hosting) | Self-hosting registry; every PHI-path model and service declares `self_hostable: true`; the residency attestation cross-checks it | `observability/registry.yaml`; `services/probes/src/intake_probes/registry.py`; `services/probes/src/intake_probes/residency.py` | implemented |
| Kriptografi ve veri güvenliği (at-rest) | Field-level envelope encryption for transcripts, notes and learned facts | `packages/intake_platform/src/intake_platform/envelope.py` | implemented |
| Kişisel verinin maskelenmesi / tokenizasyon | Identifiers tokenized; no raw identifier in logs, traces or analytics | `packages/intake_platform/src/intake_platform/` (tokenization + redaction) | implemented |
| İz kaydı yönetimi — bütünlük | Hash-chained audit log; INSERT-only writer | `packages/intake_platform/src/intake_platform/` (audit chain) | implemented (external anchor: section C) |
| Gizli anahtar yönetimi | Secrets only from OpenBao; never committed; never in logs | `infra/` (OpenBao); registry `openbao` row | implemented |
| Uygulama güvenliği — girdi güvenliği | Speech, documents and records are data, never instructions: delimited, schema-constrained, refused rather than escaped | `packages/intake_platform/src/intake_platform/data_boundary.py` | implemented |
| Üçüncü taraf / veri aktarımı kaydı | KVKK vendor-transfer register auto-filled from the egress feed; a transfer with no sourced lawful basis is refused | `packages/intake_platform/src/intake_platform/compliance/register.py` | implemented (live destination DPA: section C) |
| Loglarda kişisel veri sızıntısının önlenmesi | Redaction processor; PHI-pattern scan; error messages carry ids, not payloads | `packages/intake_platform/src/intake_platform/redaction.py` | implemented |
| İzleme ve olay yönetimi (health/metrics contract) | Every PHI-path service exposes `/healthz`, `/readyz`, `/metrics`, `/version`; synthetic probes; egress denials paged | `packages/intake_platform/src/intake_platform/health`; `services/probes/` | implemented |

---

## B. USVS conformance (national health-data dictionary)

The public-hospital exchange maps to the USVS (Ulusal Sağlık Veri Sözlüğü) as a
mechanism that refuses to guess: only sourced rows serve, an inbound code with
no committed source resolves to no code, and a sourced HBYS field id is one its
committed source defines. Conformance is enforced by test, not by prose.

| item | committed artefact |
|---|---|
| USVS + HBYS mapping tables | `packages/connectors/src/intake_connectors/usvs_map.yaml`; `packages/connectors/src/intake_connectors/usvs.py` |
| conformance test suite | `tests/legal/test_usvs_conformance.py` (and INT-162 `tests/connectors/test_usvs_mapping.py`) |

The USVS code bindings remain `draft_needs_source` until a committed USVS
dictionary vouches for each element (INT-162 blocker; HB-A5 for a given
hospital's own local codes).

---

## C. Human-gated rows — `awaiting-human`, against an existing blocker

These map to a Rehber domain but their **conformance** turns on a legal or
security decision no agent may take. Each references an existing
`files/HUMAN_BLOCKERS.md` row; no new blocker id is minted.

| Rehber control domain | what is blocked | blocker |
|---|---|---|
| Veri yerelleştirme — legal residency claim | Whether the in-country / vendor-free posture is legally attestable under KVKK Art. 9 (physical vs legal residency; control-plane siting). The Genelge 2019/12 attestation renders only once this is answered and signed. | `awaiting-human` HB-L11 |
| Üçüncü taraf güvenliği — live connector destination | A live connector destination needs an executed processor DPA, a named recipient and OpenBao-held credentials before any push. | `awaiting-human` HB-A15 |
| İz kaydı bütünlüğü — dış çıpalama (external anchor) | The audit chain's head must be published to a second organisation's store or a Turkish TSP timestamp; no counterparty or TSP is named. | `awaiting-human` HB-I12 |
| Erişim yetki yönetimi — admin ağ sınırları | The admin console's permitted network ranges and the tenant→deployment map ship empty (an empty allow-list admits nobody, the correct shipping state). | `awaiting-human` HB-A16 |
| Aydınlatma / açık rıza metinleri | The Turkish legal and consent texts are authored and signed into `docs/legal/` by counsel; unsigned, they do not render. | `awaiting-human` HB-L27 |
| Güvenli yazılım geliştirme yaşam döngüsü — IEC 62304 sınıfı | The software safety class (B vs C) and the QMS work package it scopes are a regulatory/clinical/architecture decision. | `awaiting-human` HB-L17 |
| İş sürekliliği / yedekleme | The backup retention window and the second (DR) location in Türkiye are unset. | `awaiting-human` HB-I8 |

---

## How conformance is proven

- **Registry assertion + egress vendor-free:** `tests/legal/test_residency_attestation.py`, over `observability/registry.yaml` and `infra/security/egress-allowlist.yaml`, both checked and failing closed.
- **USVS conformance:** `tests/legal/test_usvs_conformance.py`.
- **Genelge 2019/12 attestation:** `docs/regulatory/genelge_2019_12_residency_attestation.md` — mechanism built, legal content empty, fail-closed (`awaiting-human` HB-L11).
