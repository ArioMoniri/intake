# Genelge 2019/12 — residency attestation pack (public-hospital / tr-residency)

**What this is.** The public-hospital pack's residency attestation: a formal
statement that a `tr-residency` tenant's health data is processed in-country and
reaches no external model or speech vendor on the PHI path, referenced to
Sağlık Bakanlığı **Genelge 2019/12**.

**What it is NOT, and why part of it is empty.** A legal attestation to the
Ministry is human content. CLAUDE.md makes consent and legal text a
stop-and-ask, and `files/HUMAN_BLOCKERS.md` Rule 1 forbids an agent inventing a
legal value or authoring a legal statement. So this pack ships as a **mechanism
with the legal content left empty and failing closed**: the machine-checkable
conformance below is derived from committed configuration, but the
**attestation statement and signatory block are unset**, and the attestation
**does not render** until a named human signs it.

> **Status: `awaiting-human` — HB-L11.**
> Whether the in-country, vendor-free posture is legally *attestable* under KVKK
> Art. 9 (physical vs legal residency; control-plane siting) is HB-L11's counsel
> question. The signature regime a signed attestation would ride is HB-L27
> (`docs/legal/`). Until HB-L11 is answered and the statement signed, the
> attestation cannot be produced — by design.

---

## 1. Machine-checkable conformance (derived, not attested)

These are proven by test over committed sources; they are **evidence for** an
attestation, never the attestation itself.

| control | statement | committed evidence |
|---|---|---|
| `registry_phi_path_self_hosted` | Every model and service on the PHI path declares `self_hostable: true`. | `observability/registry.yaml` |
| `egress_phi_path_vendor_free` | No anthropic/openai/google adapter is reachable on the PHI path. | `infra/security/egress-allowlist.yaml` |

Enforcement: `services/probes/src/intake_probes/residency.py`
(`attest_residency`), gated by `tests/legal/test_residency_attestation.py`.
Both checks fail closed — a violation raises `ResidencyViolation` rather than
degrading to a soft warning.

## 2. The legal attestation statement — EMPTY, awaiting-human

The following fields are the human content. They are recorded here as **unset**;
`intake_probes.residency.GenelgeResidencyAttestation` refuses to render while any
is empty (`AttestationUnsigned`, naming HB-L11).

- Attestation statement (Turkish): *unset — awaiting-human (HB-L11).*
- Named signatory: *unset — awaiting-human.*
- Signatory title / role: *unset — awaiting-human.*
- Signed on (date): *unset — awaiting-human.*
- Signed commit: *unset — awaiting-human.*

No agent may fill any of the above. When HB-L11 is answered, a human authors the
statement and records the signatory (the same discipline as `docs/legal/`
documents under HB-L27), and the gate opens.

## 3. Related controls in the DDO Rehber mapping

The residency attestation is one row of the public-hospital pack. The full
control mapping to the *Bilgi ve İletişim Güvenliği Rehberi* is in
`docs/regulatory/ddo_rehber_mapping.md`.
