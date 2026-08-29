# INTAKE threat model — STRIDE/LINDDUN working model (INT-020)

files/10 is the canonical security spec; its §5 header says the full STRIDE/LINDDUN model
lives here, and its §9 matrix ("present in every feature") is what this file expands. Nothing
below is invented beside files/10 — every control cites the files/10 section that names it,
and where this file and files/10 disagree, files/10 wins and this file is the defect.

## How to read this file

- **One section per backlog `sec_row`.** `docs/backlog/issues.yaml` tags issues with
  `sec_row:` values; files/10 §8 says those fields point at the §9 rows "so every feature PR
  links its threat row by construction". `scripts/ci/check_sec_row_linkage.py` enforces the
  construction: a PR whose issue carries a `sec_row` must declare `Sec-Row: <row>` in its body,
  and that row must have a section heading here. `tests/docs/test_threat_model_rows.py` keeps
  this file and the backlog in lock-step.
- **Threat tags.** STRIDE: `S` spoofing · `T` tampering · `R` repudiation · `I` information
  disclosure · `D` denial of service · `E` elevation of privilege. LINDDUN: `L` linking ·
  `Id` identifying · `Nr` non-repudiation · `De` detecting · `Dd` data disclosure ·
  `U` unawareness · `Nc` non-compliance. Tags appear as `[T/Dd]` on each threat.
- **Adversaries** (files/10 §1): opportunistic internet attackers; malicious or careless
  insiders (support, hospital IT, contractors); a compromised vendor or dependency; a
  malicious patient or companion (voice/document injection, impersonation, triage
  manipulation); a hostile network; an attacker with physical access to a kiosk or lost phone.
- **Signals convention.** No `observability/metrics_catalog.yaml` exists in the repo yet
  (CLAUDE.md invariant 13; the catalogue itself lands with INT-025), so no section cites a
  catalogued metric as if it were already emitted. Metric names quoted in backticks are the
  names files/10 gives; each signal says which issue lands it.
- **Tests convention.** Paths named without qualification exist in the repo today. Everything
  else says "lands with INT-nnn" — a guard cited for a property it does not yet test is worse
  than no guard (files/10 §3).
- **No performance figures.** Per ADR-022 and CLAUDE.md invariant 20, this file carries no
  model-quality numbers of any kind; measurements live in docs/evidence/ with a date and a
  named corpus. `tests/security/test_threat_model.py` scans this file for claim language.
- **Invariant numbers** (`inv. N`) refer to the catalogue in files/10 §9.1 (12–49). Numbers
  50–65 are reserved and unspecified (files/10 §9.2) — nothing here cites them as enforced.

Incident handling for everything below: `docs/security/incident-runbook.md`.

---

### Platform, delivery and data plane

## `platform` — monorepo and dev tier baseline

- **Assets:** source tree, Makefile entry points, compose dev tier, developer credentials.
- **Trust boundaries:** developer workstation ↔ repo ↔ package registries ↔ container images.
- **Threats (STRIDE/LINDDUN):** [T] malicious dependency or lockfile drift entering the tree;
  [I] secret committed to the repo; [E] pre-commit/gate bypass normalising unreviewed change.
- **Controls (files/10):** §8 pre-commit set (gitleaks, Semgrep+Bandit, dependency review,
  Renovate with lockfiles); CLAUDE.md invariant 14 (gates never skipped); Makefile as the only
  entry point so gates cannot be sidestepped by ad-hoc commands.
- **Signals:** vulnerability counts by severity and age (files/10 §7) land with INT-192 on the
  console and INT-205 in the SIEM.
- **Tests:** tests/smoke/test_make_check.py; tests/ci/test_no_placeholders.py;
  tests/ci/test_coverage_floors.py.

## `cicd` — pipeline, artefacts and gate integrity

- **Assets:** workflow definitions, runner credentials, build artefacts, SBOMs, signing
  identity, the gate set itself.
- **Trust boundaries:** GitHub-hosted (later TR self-hosted, INT-206) runners ↔ repo ↔
  registries; PR author ↔ required checks.
- **Threats (STRIDE/LINDDUN):** [T] a repointed action tag or poisoned artefact (ci.yml pins
  actions to commit SHAs for exactly this reason); [E] workflow permission escalation;
  [R] unsigned artefacts with no provenance; [Nc] a skipped security gate (invariant 14).
- **Controls (files/10):** §8 in full — OSV/Trivy/Checkov fail-on high, licence check, Syft
  SBOM, cosign keyless signing with SLSA provenance, schemathesis, MobSF; CI carries no
  secrets and never calls a vendor (ci.yml header; CLAUDE.md).
- **Signals:** integrity failures — image and protocol signature — are §7 hard signals; land
  with INT-019 (security.yml) and INT-187/INT-192 (console surfaces).
- **Tests:** tests/ci/test_evidence_check.py; tests/ci/test_no_placeholders.py;
  tests/security/test_threat_model.py (the sec_row linkage gate); full gate job lands with
  INT-019.

## `secrets` — OpenBao and service credentials

- **Assets:** OpenBao root/unseal material, per-service tokens, dynamic Postgres credentials,
  Transit key material.
- **Trust boundaries:** every service ↔ OpenBao; dev mode ↔ prod mode (fail-closed boot).
- **Threats (STRIDE/LINDDUN):** [I] secret in env file, image or log; [E] over-broad policy
  letting one service read another's subtree; [S] service impersonation without workload
  identity; [D] sealed vault taking the platform down.
- **Controls (files/10):** §2 services — dynamic DB creds TTL 24 h, least-privilege per-service
  policies, workload identity; §8 deploy — secrets injected from OpenBao, none in env files or
  images; CLAUDE.md invariant 14 (secrets only from OpenBao).
- **Signals:** OpenBao seal-status probe (§6 synthetic probes) lands with INT-022;
  secret-rotation countdowns (§7) land with INT-192.
- **Tests:** tests/security/test_openbao_wiring.py (fail-closed prod boot, dev-token refusal,
  minted creds exercised against Postgres).

## `identifiers` — tokenization of TC Kimlik and phone

- **Assets:** TC Kimlik numbers, phone numbers, the HMAC pseudonym key, the vault table.
- **Trust boundaries:** application tables ↔ tokenization service ↔ identity vault.
- **Threats (STRIDE/LINDDUN):** [Id/L] re-identification by joining pseudonyms across
  contexts; [I] clear identifier reaching an application table or log; [T] pseudonym-key
  compromise making pseudonyms forgeable or reversible.
- **Controls (files/10):** §3 tokenization — keyed pseudonym (HMAC-SHA-256, rotated key),
  encrypted value in a separate vault table, logs and analytics see only the hash prefix.
- **Signals:** redaction hits (§9 observability row) land with INT-023; catalogue entry with
  INT-025.
- **Tests:** tests/security/test_tokenization_roundtrip.py.

## `data-at-rest` — envelope encryption and RLS

- **Assets:** transcripts, notes, learned facts, per-tenant data keys, volume snapshots.
- **Trust boundaries:** application ↔ OpenBao Transit (key wrap); tenant ↔ tenant (RLS).
- **Threats (STRIDE/LINDDUN):** [I] database theft or snapshot exfiltration; [E] cross-tenant
  read where RLS is configured but not exercised; [Nc] hard-delete promised but not
  cryptographically performed.
- **Controls (files/10):** §3 — field-level envelope encryption (AES-256-GCM) with per-tenant
  keys wrapped in OpenBao Transit, quarterly rotation, crypto-shredding as the hard-delete
  mechanism; §2 — RLS per tenant with the GUC from the OIDC claim and a per-request DB role.
- **Signals:** key-rotation countdowns (§7) land with INT-192.
- **Tests:** tests/security/test_envelope_encryption.py;
  tests/security/test_envelope_transit_unit.py; RLS exercise lands with INT-030.

## `api` — API security baseline

- **Assets:** session tokens, PHI-bearing routes, idempotency state, error output.
- **Trust boundaries:** public internet ↔ ingress ↔ services/api; caller identity ↔ consent
  scope on every route.
- **Threats (STRIDE/LINDDUN):** [S] token theft/replay; [D] rate exhaustion; [T] write replay
  through idempotency-key abuse; [I] verbose errors echoing patient input (§3 SafeError).
- **Controls (files/10):** §4 API — strict Pydantic schemas, input and request-size limits,
  per-route `consent_guard`, idempotency keys on writes, rate limits per user/IP/tenant,
  security headers, CSRF-safe token auth; §3 — `SafeError` boundary before any logger.
- **Signals:** consent-scope denials and rate-limit refusals (§7) land with INT-038/INT-023.
- **Tests:** tests/platform/test_rate_limit.py; tests/platform/test_idempotency.py;
  schemathesis fuzzing lands with INT-019.

## `api-surface` — hardening findings on the shipped middleware

- **Assets:** the idempotency and rate-limiting primitives every route inherits.
- **Trust boundaries:** authenticated principal ↔ principal; app clock ↔ store clock.
- **Threats (STRIDE/LINDDUN):** [S/I] cross-principal idempotency replay disclosing another
  user's cached response (INT-176); [D] limiter bypass through per-process clock skew
  (INT-177).
- **Controls (files/10):** §4 baseline as above; keys scoped by authenticated principal and
  tenant; the limiter takes time from Redis TIME inside the Lua script.
- **Signals:** as `api`; anomaly review lands with INT-192.
- **Tests:** tests/platform/test_idempotency.py; tests/platform/test_rate_limit.py.

## `edge` — ingress, WAF and the egress proxy

- **Assets:** ingress configuration, WAF rule set, the egress allow-list, transfer logs.
- **Trust boundaries:** internet ↔ edge; PHI network ↔ every outbound destination.
- **Threats (STRIDE/LINDDUN):** [D] volumetric and bot traffic; [I/Dd] exfiltration to a
  non-allow-listed host; [T] allow-list drift between CI assertion and live configuration
  (inv. 25 runs in CI, "the wrong place to notice that production diverged" — §4).
- **Controls (files/10):** §4 edge — Traefik/Envoy with Coraza (OWASP CRS), CrowdSec,
  egress proxy with allow-list where every call is logged with vendor, purpose and bytes
  (doubling as KVKK transfer evidence); allow-list as live console configuration.
- **Signals:** WAF/CrowdSec blocks and egress denials — a hard alert (§7); land with
  INT-203 and INT-018.
- **Tests:** egress policy tests land with INT-018; edge stack tests with INT-203/INT-204.

## `monitoring-contract` — health, metrics, SLOs

- **Assets:** `/healthz` `/readyz` `/metrics` `/version` surfaces, SLO definitions, probe
  registry.
- **Trust boundaries:** service ↔ collector; metrics consumers ↔ PHI (labels must carry ids
  only).
- **Threats (STRIDE/LINDDUN):** [I] PHI smuggled into metric labels or version output;
  [D/De] blind spots — a service without probes fails invisibly; [R] no build provenance on
  `/version`.
- **Controls (files/10):** §6 in full — the shared health package, OTel propagation with
  hashed session ids, golden-signal dashboards, synthetic probes every 60 s; CLAUDE.md
  invariant 15 (a new service without the contract fails `make check`).
- **Signals:** burn-rate alerts land with INT-021; probe registry with INT-022; the metrics
  catalogue itself with INT-025.
- **Tests:** tests/platform/test_health_contract.py; catalogue completeness test lands with
  INT-025.

## `observability-pipeline` — logs, traces, errors are not a side channel

- **Assets:** logs, traces, crash reports, Langfuse content, the OTel collector path.
- **Trust boundaries:** application exceptions ↔ every exporter; ops tooling ↔ patient
  content.
- **Threats (STRIDE/LINDDUN):** [I/Dd] PHI via `ValidationError` messages, Celery task
  kwargs, or crash-reporter local variables (§3 names all three); [T] insider who edits a log
  row and repairs the chain; [Dd] Langfuse storing transcripts verbatim.
- **Controls (files/10):** §3 — redaction processor, `SafeError` boundary before any logger,
  Pydantic configured to omit input, `include_local_variables=False` plus `before_send`;
  §9 row — hashed-content Langfuse, WORM audit copies, INSERT-only `svc-audit-writer`,
  externally anchored chain head; runtime PHI scan (inv. 36) replaces fixture-only scanning.
- **Signals:** redaction hits, chain verification, `admin.audit_seq_gaps_total`,
  `admin.audit_external_anchor_age_min` (files/10 §9) — land with INT-016, INT-023, INT-025.
- **Tests:** tests/platform/test_redaction.py; tests/security/test_trace_redaction.py;
  inv. 36 and the flip-and-repair test (inv. 40) land with INT-016 and the console issues.

## `audit` — the hash-chained audit log

- **Assets:** the audit table, chain head, WORM export copies, `seq` counters.
- **Trust boundaries:** every writer ↔ `svc-audit-writer` (sole INSERT); `platform_admin`
  blast radius ↔ the external anchor.
- **Threats (STRIDE/LINDDUN):** [T] row edit with the chain recomputed forward (the attack
  INT-016's one-row flip does not cover — §3); [R/Nr] clean deletion leaving a valid chain
  (caught by per-actor, per-tenant `seq` gaps); [I] audit rows carrying PHI instead of ids.
- **Controls (files/10):** §3 audit-log corrections (a)–(d): sole INSERT grant, hourly
  external chain-head publication, monotonic `seq`, WORM object-lock copies (with the
  MinIO/Garage caveat §3 records); §2 — UPDATE/DELETE granted to no principal; write-ahead
  ordering (§9 admin row).
- **Signals:** chain verification, `admin.audit_seq_gaps_total`,
  `admin.audit_external_anchor_age_min` (files/10 §9) — land with INT-016.
- **Tests:** land with INT-016 (one-row flip) and inv. 40 (flip-and-repair, strictly
  stronger).

## `backups` — backups and disaster recovery

- **Assets:** PITR archives, MinIO/object-store copies, backup encryption keys, drill
  evidence.
- **Trust boundaries:** production ↔ second location in Türkiye; backup keys ↔ data keys
  (separate on purpose).
- **Threats (STRIDE/LINDDUN):** [I] backup theft; [T/D] ransomware reaching the backup tier;
  [Nc] restores never exercised, discovered during the incident.
- **Controls (files/10):** §3 backups & DR — encrypted PITR to a second in-country location,
  immutable copies, RPO 15 min / RTO 4 h, quarterly restore drills with console evidence.
  INT-202 lands the repository configuration (`infra/backup/pgbackrest.conf`,
  `repo1-cipher-type=aes-256-cbc`, passphrase from OpenBao and never from a file), the
  replication plan (`infra/backup/minio-replication.yaml` — object-lock preserved on the
  audit replica, deletions never propagated, which is the ransomware defence) and the drill
  itself. The **second location is not named anywhere in files/**, so
  `INTAKE_DR_S3_ENDPOINT` has no default and the DR object store has no registry row —
  HB-I8(b), and HB-I5 for why no in-country provider is contracted.
- **Signals:** backup freshness (`services/probes` `backup_freshness` over
  `INTAKE_BACKUP_DIR`, bounded at `INTAKE_BACKUP_MAX_AGE_S=900` — the 15-min RPO) and
  last-drill age. `sec.backup_age_min` and `sec.restore_drill_age_days` stay `planned` in
  the catalogue: nothing emits them yet, and a `live` entry nothing emits is the dishonest
  direction the INT-025 gate exists to catch.
- **Tests:** `tests/infra/test_restore_drill.py` (INT-202) — the repository is encrypted,
  no credential literal is committed, replication keeps object-lock and propagates no
  deletion, the drill refuses a restore target inside the workspace, and its evidence record
  has no field an identifier could occupy. The **execution** half (`make backup-drill`) is
  scripted, wired and unexercised on the recorded host: HB-I1 (disk) and HB-I2 (container
  memory) block it, and the retention window the expire step needs is HB-I8(a). The drill
  refuses rather than shrinking to fit.

## `resilience` — degradation without harm

- **Assets:** queue depth, vendor adapters, the typed-fallback path, the RED delivery path.
- **Trust boundaries:** media transport ↔ safety path (the RED script is pre-positioned on
  the device and triggered over the data channel — CLAUDE.md invariant 21).
- **Threats (STRIDE/LINDDUN):** [D] vendor or model outage cascading into intake loss;
  [D] queue saturation delaying Backend speech; patient-safety availability — a degraded
  session must still reach a safe state.
- **Controls (files/10):** §5 LLM10 budgets and circuit breakers; §6 capacity — autoscaling
  on queue depth, monthly chaos experiments; typed fallback within 2 s (backlog INT-100).
- **Signals:** budget exhaustion and vendor errors (§9 voice row) land with INT-024/INT-100.
- **Tests:** chaos harness and fallback timing land with INT-024, INT-100, INT-207.

## `self-hosting` — model supply chain and residency

- **Assets:** model weights, the model/self-hosting registry, GPU tier, licence records.
- **Trust boundaries:** internal registry ↔ upstream sources (no runtime downloads in prod);
  PHI path ↔ any vendor adapter.
- **Threats (STRIDE/LINDDUN):** [T] weight substitution where a revision is not pinned;
  [Nc] a non-commercial or unverified licence on the PHI path; [I/Dd] a dev-only cloud
  adapter reachable from production.
- **Controls (files/10):** §5 LLM03 — weights pinned by `model_id@revision + sha256`,
  mirrored internally, prompts versioned and signed; CLAUDE.md invariant 19 — licences
  verified from the raw LICENSE blob with `licence_verified_at`; the `anthropic|openai|google`
  adapters are mock/dev only and blocked on the PHI path by the egress allow-list.
- **Signals:** per-model probe status (§6) lands with INT-022 and INT-183.
- **Tests:** registry and provenance checks land with INT-022/INT-183; egress blocking with
  INT-018.

## `tenants` — tenant isolation and provisioning

- **Assets:** tenant boundary (RLS), tenant configuration, DPA state, clinician accounts.
- **Trust boundaries:** tenant ↔ tenant; hospital IT ↔ clinical approval authority.
- **Threats (STRIDE/LINDDUN):** [E] cross-tenant read via a forged `tenant_id` parameter
  (inv. 37: RLS protects the row, not the parameter); [S] hospital IT provisioning an account
  for a person who does not exist, every read indistinguishable from care (§9 clinician
  provisioning); [Nc] a tenant serving patients without a signed DPA.
- **Controls (files/10):** §2 — RBAC/ABAC by tenant, tenant GUC from the OIDC claim, never
  the request; §9 clinician provisioning — verified professional identifier, approval by
  `tenant_clinical_responsible` never IT, KEP/e-imza-signed quarterly review, 60-day
  auto-disable, notes-viewed vs appointment-list anomaly signal.
- **Signals:** notes-viewed vs appointments, dormant accounts, review age (§9) land with
  INT-250 and INT-192.
- **Tests:** role × tenant matrix (inv. 37) lands with INT-180 and INT-030.

---

### Identity, consent and patient rights

## `onboarding` — patient OTP, attestation, sessions

- **Assets:** phone OTP flow, refresh-token families, attestation verdicts, session state.
- **Trust boundaries:** unauthenticated caller ↔ account; device ↔ token (DPoP binding).
- **Threats (STRIDE/LINDDUN):** [S] account takeover through OTP abuse; [D] SMS pumping
  (cost and lockout); [I/Id] account enumeration through response differences.
- **Controls (files/10):** §2 patients — OTP limits (TTL, attempt and per-phone/IP request
  caps, carrier/geo sanity), device attestation on OTP request and session start, rotating
  device-bound refresh tokens with family revocation on reuse, passkeys, biometric gate,
  generic error messages (§9 row 1).
- **Signals:** OTP request/fail rates by ASN, attestation failures, new-device logins (§9)
  land with INT-131 and the console with INT-192.
- **Tests:** abuse-path tests land with INT-131; schemathesis with INT-019.

## `consent` — layered consent and scope enforcement

- **Assets:** versioned consent objects, scope-check middleware, consent texts (docs/legal/).
- **Trust boundaries:** every read/share ↔ a consent scope (CLAUDE.md invariant 4); consent
  text ↔ what the system actually does (inv. 25 parity).
- **Threats (STRIDE/LINDDUN):** [Nc] processing beyond the granted scope or on a stale
  version; [U] the patient not understanding what a scope permits; [T] consent-record edits
  after the fact.
- **Controls (files/10):** §9 consent row — versioned objects, server-side enforcement on
  every read, re-prompt on change; CLAUDE.md invariant 18 — texts render only from
  docs/legal/ with hash binding; `consent_vendor_parity` (inv. 25) ties named vendors to the
  egress allow-list.
- **Signals:** `consent_guard` denials and re-prompt rates (§9) land with INT-038.
- **Tests:** route-table scan proving every clinical route checks a scope lands with INT-038.

## `companions` — proxy, guardian and minor flows

- **Assets:** proxy relationships, guardian consent state, minor records.
- **Trust boundaries:** speaking companion ↔ patient of record; guardian authority ↔
  adolescent privacy policy.
- **Threats (STRIDE/LINDDUN):** [S] impersonation — companion answering as the patient;
  [U/Nc] proxy access beyond what the minor-policy allows; [L] linking guardian and patient
  profiles beyond need.
- **Controls (files/10):** §9 companions row — proxy flag on every proxy-sourced record,
  explicit acknowledgement, hospital desk verification for kiosk, separate consent; the
  minor/guardian rules engine as code (backlog INT-223).
- **Signals:** share of proxy-reported content and desk verification rate (§9) land with
  INT-133.
- **Tests:** scenario IM-14 (files/04 §6) lands with INT-133/INT-223.

## `dsar` — data-subject rights: export, delete, rectify

- **Assets:** export bundles, deletion machinery, the 30-day SLA clock.
- **Trust boundaries:** requester identity ↔ subject identity; export content ↔ the
  compliance officer's spreadsheet application (inv. 47's injection vehicle).
- **Threats (STRIDE/LINDDUN):** [I/T] export injection — attacker-authored content that
  evaluates when the KVKK m.13 export is opened (inv. 47); [S] DSAR filed by an impostor;
  [Nc] missed SLA or a deletion that leaves derived copies.
- **Controls (files/10):** §4 (b) — every export serialiser fuzzed for formula,
  control-character and CRLF payloads, text-typed cells; §3 — crypto-shredding with 30-day
  grace; the SLA tracker (backlog INT-037).
- **Signals:** `admin.dsar_delete_total{subject_count}`, emitted once per erasure run by
  `intake_api.dsar.shred.execute_due_shreds` (INT-037). The tenant-wide queue over the
  same rows, and the alerting on a subject count above one, are the compliance console's
  (INT-189).
- **Tests:** `tests/legal/test_dsar_flows.py` — `export_injection_guard` (inv. 47: formula
  leads neutralised, control characters and CRLF collapsed), the export failing closed
  while `docs/legal/strings.yaml` is unauthored, share cancellation on erasure, the
  30-day grace, and the crypto-shred proof (a shredded field can never be decrypted
  again). `tests/security/test_crypto_shred.py` pins the envelope operation itself.

## `retention` — retention and destruction automation

- **Assets:** retention policy as code, destruction jobs, destruction records.
- **Trust boundaries:** policy (files/06 §3 matrix) ↔ what jobs actually delete.
- **Threats (STRIDE/LINDDUN):** [Nc] data outliving its row in the retention matrix;
  [I] hot logs kept past 30 d; [De] destruction jobs failing silently.
- **Controls (files/10):** §3 retention automation — jobs enforce files/06 §3 (raw audio
  never written; lane windows zeroed; logs 30 d hot / 1 y cold; 30-day deletion grace), job
  success as a tracked metric; DEST-2017 destruction records (§9 research-store row).
- **Signals:** retention-job success (§3) lands with INT-036.
- **Tests:** land with INT-036 and INT-212 (policy document bound to the engine).

## `compliance-evidence` — the evidence trail itself

- **Assets:** consent registers, vendor/transfer register, DPIA, VERBİS inventory, audit
  exports, drill records.
- **Trust boundaries:** claimed control ↔ recorded evidence; evidence exports ↔ PHI.
- **Threats (STRIDE/LINDDUN):** [R] a control asserted with no record behind it; [Nc] a DPIA
  stale after a vendor or consent-text change; [I] evidence exports carrying patient content
  instead of ids.
- **Controls (files/10):** §10 — evidence accumulates automatically from the console; §8 —
  DPIA delta check when vendors or consent texts change; CLAUDE.md invariant 18 — every new
  data field carries its inventory annotation.
- **Signals:** access-review age and drill status (§7) land with INT-189.
- **Tests:** schema-annotation completeness lands with INT-211; module tests with INT-189.

---

### Intake, clinical content and AI boundaries

## `visits` — visit creation and MHRS SMS screenshot OCR

- **Assets:** visit records, branch selection, uploaded screenshots.
- **Trust boundaries:** patient-supplied image ↔ OCR worker ↔ structured visit data.
- **Threats (STRIDE/LINDDUN):** [T] malicious image attacking the OCR stack; [I] PII from
  screenshots landing in OCR logs; [S] a forged screenshot creating misleading visit context.
- **Controls (files/10):** §9 visit row — sandboxed OCR, size/type limits, no OCR text in
  logs; upload baseline in §4 (sniffing, sandboxed parsing).
- **Signals:** OCR failures and processing time (§9) land with INT-134.
- **Tests:** image fuzzing lands with INT-134 and INT-122.

## `intake-voice` — the patient-facing voice session

- **Assets:** live audio, session tokens, the RED delivery path, patient trust in the voice.
- **Trust boundaries:** patient's room (who else is present?) ↔ the session; device ↔ SFU.
- **Threats (STRIDE/LINDDUN):** [I] eavesdropping and third-party presence during sensitive
  sections; [S] a different speaker answering for the patient; [D] network loss at the worst
  moment (during a RED).
- **Controls (files/10):** §5 voice transport — per-session room tokens with minimal grants
  and 10-min TTL, DTLS-SRTP, ephemeral rooms, no SFU recording; inv. 26 — on
  `third_party_present` before a sensitive section, typed/keypad is offered; CLAUDE.md
  invariant 21 — the RED script is pre-positioned on the device, data channel only.
- **Signals:** round-trip latency and vendor errors (§9 voice row) land with INT-135/INT-103.
- **Tests:** RT-01…RT-12 scenarios land with INT-094 and INT-102.

## `intake-typed` — the typed parity path

- **Assets:** typed session content, the same clinical state machine minus audio.
- **Trust boundaries:** patient text ↔ model context (data, never instructions).
- **Threats (STRIDE/LINDDUN):** [S/T] prompt injection by typed text; [D] pathological input
  sizes; [I] PolicyGuard bypass in a less-exercised path.
- **Controls (files/10):** §9 typed row — the same data boundary, input limits; PolicyGuard
  on every patient-facing string (CLAUDE.md invariant 2).
- **Signals:** latency and PolicyGuard blocks (§9) land with INT-096.
- **Tests:** simulator coverage lands with INT-096 and INT-136.

## `voice-runtime` — the agent worker and its hard boundaries

- **Assets:** in-memory audio buffers, the six-tool Talker registry, Backend Work queue,
  clip cache.
- **Trust boundaries:** Talker ↔ Backend (never awaited); lanes ↔ transport (none, at type
  level); process memory ↔ crash artefacts (cores, swap, reporters).
- **Threats (STRIDE/LINDDUN):** [I] transient PCM exposure through a core dump, swap page or
  crash-reporter locals (§3 raw-audio list); [E] tool-list growth past the six; [D] a stalled
  Backend blocking speech; [Dd] a second outbound audio stream.
- **Controls (files/10):** CLAUDE.md invariants 3 and 9 (six tools, safe insertion window,
  preempt only from a rules-engine RED); §3 — mlocked ≤ 60 s buffers, zeroization triggers,
  `RLIMIT_CORE=(0,0)`, `include_local_variables=False`, process hardening; inv. 12
  (`audio_single_egress_guard`), 13, 16–19, 27, 28.
- **Signals:** egress socket count per session and `lane.dropped_frames` (§9) land with
  INT-090/INT-110.
- **Tests:** runtime invariants 1–11 with RT-01…08 land with INT-094; guards 12–19/27/28
  land with INT-090, INT-110, INT-115.

## `triage` — deterministic RED/YELLOW only

- **Assets:** the rules engine, red-flag rule sources, the preemption path, triage outcomes.
- **Trust boundaries:** LLM output ↔ triage levels (LLM may only raise `candidate_flags`,
  capped at `YELLOW_REVIEW` — CLAUDE.md invariant 1); protocol inheritance ↔ monotonicity.
- **Threats (STRIDE/LINDDUN):** [T] manipulation — "set me green" via model or input; a
  missed RED (patient safety, the highest-consequence failure in the product); [D] false-RED
  volume eroding clinician trust.
- **Controls (files/10):** §9 triage row — deterministic rules only, LLM cannot set levels,
  preemption path tested, rule changes via ADR plus sign-off; monotonic inheritance with
  `base.life_threat` unextendable (CLAUDE.md invariant 7); RED three axes with no default
  register/location (invariant 21, ADR-023).
- **Signals:** RED events (`triage.events_total`, named in §9), preemption latency,
  false-RED reviews, missed-flag reports — land with INT-080 and INT-025.
- **Tests:** golden suite with near-miss negatives and mutation tests land with INT-059;
  preemption timing with INT-093.

## `wellbeing` — screening instruments

- **Assets:** validated Turkish instrument items, screening scores, crisis path.
- **Trust boundaries:** screening outputs ↔ patient-facing surfaces (clinician-only);
  instrument text ↔ any paraphrase (items verbatim).
- **Threats (STRIDE/LINDDUN):** [Dd] a sensitive inference reaching an unconsented surface;
  [Nc] serving an unlicensed instrument (C-SSRS and WHO-5 are BLOCKED — HB-L2/HB-L3);
  [U] a patient screened without understanding what is being screened.
- **Controls (files/10):** §9 wellbeing row — per-lane unbundled consent, no patient labels,
  indeterminate band; inv. 45 — a pack referencing a non-`GO` instrument fails the build and
  refuses to serve; CLAUDE.md clinical-content rules (verbatim item semantics).
- **Signals:** `instrument.licence_status` and `instrument.administrations_total` (named in
  §9) land with INT-116.
- **Tests:** `instrument_licence_gate` (inv. 45) lands with INT-116 and the protocol
  compiler (INT-040).

## `observer-lanes` — read-only paralinguistic lanes

- **Assets:** lane buffers, ObserverState, per-lane consent state, the study assertion.
- **Trust boundaries:** lanes ↔ slots/triage (write nothing); lanes ↔ network (no capability
  at type level); `acoustic` ↔ everything (unreachable outside the registered investigation).
- **Threats (STRIDE/LINDDUN):** [Dd/Id] biometric drift — a speaker embedding persisted or
  compared across sessions (inv. 15); [I] crash-artefact PCM exposure (applies to every lane
  buffer, not just `acoustic` — §3); [Nc] `acoustic` scoring outside a valid
  {study_id, protocol_version, ICF_version, approval_date} assertion; [E] a lane writing
  clinical state.
- **Controls (files/10):** CLAUDE.md invariant 11 (read-only, off the speech critical path,
  fail-closed study gate); inv. 12–29 as catalogued in §9.1 — single egress, no lane
  transport, diarization gate, ephemeral embeddings, zeroization incl. consent withdrawal,
  closed InteractionState at M1.
- **Signals:** lane consent rates, `lane.dropped_frames`, `acoustic.window_yield` (a low
  yield is a correct outcome, not an incident — §9), withdrawal-to-zeroization latency — land
  with INT-110/INT-115.
- **Tests:** invariants 12–29 land with INT-110, INT-111, INT-112, INT-115.

## `clinical-content` — packs, rules and safety strings

- **Assets:** protocol packs, red-flag rules with sources, `text_tr` scripts, the 112
  sentence, instrument references.
- **Trust boundaries:** hospital `override_text` ↔ safety strings (pointer allow-list);
  authored rule ↔ committed guideline snapshot (every rule carries `source:`).
- **Threats (STRIDE/LINDDUN):** [T] an override rewriting `action_tr` — the protected rule,
  the unprotected sentence (§9 pack-lifecycle row); patient safety — an unsourced or
  paraphrased clinical value; [Nc] an unlicensed instrument compiled into a pack.
- **Controls (files/10):** inv. 42 (pointer allow-list at every layer), inv. 43 (clip
  round-trip fidelity, blocking), inv. 45 (licence gate); CLAUDE.md invariants 10 (verbatim
  `text_tr`) and 17's sole permitted form (`draft_needs_source` never compiles into a served
  pack); golden tests with near-miss negatives, `make safety`, CODEOWNER review.
- **Signals:** pack versions in use and signature failures (§9) land with INT-058/INT-184.
- **Tests:** golden suite lands with INT-059; compiler validation with INT-040;
  `safety_string_override_guard` with the pack-lifecycle issues.

## `clinical-core` — clinical data model and export tier

- **Assets:** typed clinical schemas, mappers, EHRbase/openEHR export path.
- **Trust boundaries:** internal representation ↔ export formats; numbers ↔ any
  representation boundary (CLAUDE.md invariant 22).
- **Threats (STRIDE/LINDDUN):** [T] a mapping defect silently altering a clinical value;
  [I] over-broad export; [Nc] a unit/magnitude disagreement converted silently instead of
  flagged (the inv. 53 prose in files/10 §9.2 — a specification, not yet a test; not reported
  as enforced).
- **Controls (files/10):** typed schemas with the mapper coverage floor (CLAUDE.md invariant
  8); roundtrip tests; magnitude-outranks-unit with a flag on disagreement (§9.2 rule 1).
- **Signals:** land with INT-032.
- **Tests:** OPT template roundtrip lands with INT-032.

## `protocol-registry` — signed bundles and the clip cache

- **Assets:** pack bundles, signatures, per-session hash pins, clip manifests.
- **Trust boundaries:** authoring ↔ serving (signature + CODEOWNER between them); published
  version ↔ any later mutation (byte-immutable once served).
- **Threats (STRIDE/LINDDUN):** [T] a poisoned pack or tampered clip; [R] an unsigned bundle
  with no provenance; [D] no emergency un-publish path when a bad pack is live.
- **Controls (files/10):** §8 — cosign-signed bundles, hash pinned per session, unsigned or
  tampered packs fail to load; inv. 41 (byte-immutability), inv. 43 (clip manifest verified
  at load), inv. 44 (quarantine with a stated RTO, `known_good` fallback, re-triage sweep).
- **Signals:** signature failures, `admin.pack_promoted_total{to}`,
  `admin.pack_quarantined_total`, `admin.pack_quarantine_rto_s`,
  `admin.retriage_sweep_findings_total{new_level}` (named in §9) — land with
  INT-058/INT-184.
- **Tests:** load-time signature verification lands with INT-058; quarantine drill with the
  pack-lifecycle issues.

## `llm-boundary` — model calls behind gateways

- **Assets:** prompts, model context, extraction outputs, session budgets.
- **Trust boundaries:** speech/documents/records ↔ instructions (data, never instructions —
  CLAUDE.md invariant 14); model output ↔ anything that executes or renders.
- **Threats (STRIDE/LINDDUN):** [S/T] LLM01 prompt injection via speech, documents or record
  snippets; [I/Dd] LLM02 disclosure across patients or of system internals; [E] LLM06
  excessive agency; [D] LLM10 unbounded consumption.
- **Controls (files/10):** §5 table in full — delimited data with schema-constrained
  outputs, six non-clinical Talker tools, deterministic triage, PolicyGuard, no cross-patient
  context, output validated and never rendered as HTML, per-session budgets and circuit
  breakers.
- **Signals:** `security.injection_suspected` events (§5), PolicyGuard spikes, budget
  exhaustion (§7) — land with INT-083, INT-101, INT-102.
- **Tests:** adversarial suite RT-09…14 in `make safety` plus the nightly red-team job land
  with INT-102; schema-validation tests with INT-083.

## `cloud-boundary` — what may leave, and in what form

- **Assets:** outbound text (extraction, Loop 2 exports), the de-identification engine, the
  transfer register.
- **Trust boundaries:** PHI path ↔ every external destination; de-id output ↔ residual
  identifiers (Turkish morphology makes this genuinely hard — §3 says so plainly).
- **Threats (STRIDE/LINDDUN):** [Dd] residual identifiers in text egress; [Nc] a transfer
  outside the contracted, allow-listed set; [I] any audio egress — removed by design: under
  D-self-hosting there is no vendor socket, and the production voice profile is
  `residency_tr` (CLAUDE.md invariant 19).
- **Controls (files/10):** §3 — Presidio with Turkish recognizers (TC Kimlik checksum,
  phone, IBAN, addresses, date shifting) before any text egress; §4 — egress allow-list with
  per-call logging as transfer evidence; inv. 25 — consent texts and allow-list held in
  agreement by CI.
- **Signals:** egress denials — a hard alert (§7) — land with INT-018.
- **Tests:** tests/security/test_deid_ner.py; tests/security/test_deid_leak_rate.py (the
  measured results live in docs/evidence/ with date and corpus, per ADR-022); egress policy
  tests land with INT-018.

## `records` — patient document upload and ingestion

- **Assets:** uploaded documents, extracted structured data, pgvector record index.
- **Trust boundaries:** patient-supplied file ↔ parsers (sandboxed); document text ↔ model
  context (data, never instructions); patient namespace ↔ patient namespace in pgvector.
- **Threats (STRIDE/LINDDUN):** [T] malware in uploads; [S/T] injection payloads inside
  document text reaching a model; [I/L] embedding-store bleed across patients.
- **Controls (files/10):** §9 records row — ClamAV, file-type sniffing, sandboxed parsing
  (seccomp-isolated PDF rendering, §4), the data boundary, RLS on pgvector with per-patient
  namespaces, provenance on every extracted fact; ingestion unit rule (CLAUDE.md invariant
  22: magnitude outranks the printed unit token, disagreement flags).
- **Signals:** upload scan results and parse failures (§9) land with INT-120.
- **Tests:** PDF fuzzing lands with INT-120; RLS namespace tests with INT-123.

## `documents` — the object store

- **Assets:** stored documents, signed URLs, the WORM audit bucket.
- **Trust boundaries:** object store ↔ every caller (signed URLs only, short TTL); audit
  copies ↔ any writer (object lock).
- **Threats (STRIDE/LINDDUN):** [I] leaked or long-lived signed URLs, direct object
  references; [T] a WORM configuration that does not actually lock (the Garage caveat §3
  records — Garage does not implement S3 Object Lock); [D] store outage blocking intake.
- **Controls (files/10):** §4 — signed URLs with short TTL, no direct object references,
  antivirus on upload; §3 — object-lock WORM for audit copies, with the MinIO/Garage
  decision closing before P1.
- **Signals:** land with INT-034.
- **Tests:** land with INT-034.

## `notes` — the clinician-ready note

- **Assets:** composed notes, provenance links, rendered PDF/FHIR outputs.
- **Trust boundaries:** model-drafted text ↔ rendering surfaces (never as HTML); note ↔
  recipient (consent-scoped delivery).
- **Threats (STRIDE/LINDDUN):** [T] XSS through note rendering (LLM05); [I] a note reaching
  the wrong recipient; [R] a fact in the note with no provenance; LLM09 misinformation
  presented without review.
- **Controls (files/10):** §5 LLM05/LLM09 — schema-validated output, never executed, never
  rendered as HTML; provenance on every fact, "not a diagnosis" labelling, clinician review;
  watermark-ready PDF rendering (§2 Doctor Link).
- **Signals:** land with INT-084; annotation queues (note_quality, hallucination_audit) with
  INT-175.
- **Tests:** XSS tests on note rendering land with INT-084.

---

### Sharing and clinician surfaces

## `review-send` — patient review before sharing

- **Assets:** the share decision, section-level scope selections.
- **Trust boundaries:** patient intent ↔ what is actually shared (server-side enforcement).
- **Threats (STRIDE/LINDDUN):** [U/I] accidental over-share — the patient not realising what
  a section contains; [T] client-side scope tampering.
- **Controls (files/10):** §9 review row — section-level scope, consent summary, explicit
  confirm step; scopes enforced server-side per §4 consent checks.
- **Signals:** share scope distribution (§9) lands with INT-137.
- **Tests:** UI flow tests land with INT-137.

## `doctor-link` — tokenized clinician access

- **Assets:** link tokens, OTP delivery channel, view counters, the access log.
- **Trust boundaries:** anyone holding the link ↔ the note (OTP + token together); recipient
  ↔ onward disclosure (watermark).
- **Threats (STRIDE/LINDDUN):** [S] brute force on the OTP or token; [I] link leakage and
  screenshots; [R] a clinician denying they viewed the note.
- **Controls (files/10):** §2 clinicians — OTP to the patient-chosen channel, 128-bit random
  token, 72 h default expiry, view limit, instant revoke, watermarked PDFs, no indexing,
  access log (visible to the patient — §3).
- **Signals:** opens, failed OTPs, revocations, time-to-open (§9) land with INT-150.
- **Tests:** token entropy and expiry tests land with INT-150.

## `share-centre` — active shares, revocation, visibility

- **Assets:** active-share registry, revocation path, the patient-visible access log.
- **Trust boundaries:** granted access ↔ time (everything expires or can be revoked);
  staff reads ↔ patient visibility (every break-glass grant appears in the log — §3).
- **Threats (STRIDE/LINDDUN):** [I] stale access outliving intent; [Nc] incomplete deletion
  after revocation; [U] the patient unable to see who has access.
- **Controls (files/10):** §9 share row — instant token revocation, crypto-shredding, signed
  export URLs, deletion SLA; §3 patient-visible access log covering shares and staff reads.
- **Signals:** revocation latency and deletion SLA (§9) land with INT-139/INT-037.
- **Tests:** revocation and deletion-proof tests land with INT-139/INT-037.

## `clinic-console` — the clinician web surface

- **Assets:** clinician sessions, today-list data, read receipts.
- **Trust boundaries:** clinician ↔ tenant (RLS); session ↔ browser environment (CSP, short
  sessions).
- **Threats (STRIDE/LINDDUN):** [S] session hijack; [I] insider browsing beyond the care
  relationship; [E] cross-tenant reads.
- **Controls (files/10):** §4 clinician web — SSO, SameSite cookies, no PHI in URLs, short
  sessions, audit on every view, download watermarking; §2 RBAC/ABAC and RLS per tenant.
- **Signals:** views per user and anomaly review (§9) land with INT-152 and INT-192.
- **Tests:** RBAC matrix tests land with INT-152 and INT-180.

## `connectors` — pushing to hospital systems

- **Assets:** connector credentials, endpoint registry, push payloads (full clinical notes),
  receipts.
- **Trust boundaries:** our server ↔ tenant-configured destinations (SSRF surface — §4);
  PHI network ↔ hospital network; `tenant_admin` (an adversary in §1) ↔ endpoint
  configuration.
- **Threats (STRIDE/LINDDUN):** [I/Dd] SSRF and mass PHI redirection through a free-text
  endpoint (§9 connectors row: the quiet version receives every `push_previsit`
  indefinitely, looking exactly like normal operation); [S] credential theft; [T] replay;
  [D] over-push.
- **Controls (files/10):** §9 connectors row + inv. 46 — destinations registered
  out-of-band, bound to the signed DPA, rendered as a select (free text does not exist in
  the schema); literal IPs and private/link-local/metadata ranges denied;
  resolve-once-and-pin with re-validation; redirects disabled; endpoint change is tier-2 by
  `platform_owner` and pages; OpenBao-held credentials, scoped consent token per push,
  idempotency keys, mTLS/SMART backend services.
- **Signals:** push success/failure, receipts, endpoint errors, connector-endpoint change
  events (§7/§9) land with INT-160.
- **Tests:** contract and replay tests plus `connector_endpoint_allowlist_guard` (inv. 46,
  incl. the DNS-rebinding fail-closed case) land with INT-160.

## `kiosk` — shared devices in clinics

- **Assets:** kiosk sessions, clinic PIN, the physical device.
- **Trust boundaries:** consecutive patients on one device (ephemeral sessions); device ↔
  physical access (MDM lockdown).
- **Threats (STRIDE/LINDDUN):** [T] physical tampering; [I] shoulder surfing and session
  residue; [S] a forged check-in.
- **Controls (files/10):** §4 kiosk mode — guided access, MDM enrolment, PIN per clinic,
  60 s idle auto-wipe, no local persistence, tamper alert on backgrounding, large-type
  privacy layout; signed QR check-in payloads (backlog INT-163).
- **Signals:** kiosk heartbeat and session wipe count (§9) land with INT-143;
  `checkin_to_seen` with INT-163.
- **Tests:** kiosk-mode behaviour tests land with INT-143.

## `notifications` — reminders without PHI

- **Assets:** push/SMS content, delivery schedules, opt-out state.
- **Trust boundaries:** notification content ↔ lock screens and carrier infrastructure
  (content-free by design); transactional ↔ marketing (İYS gate).
- **Threats (STRIDE/LINDDUN):** [I] PHI in a push or deep link; [Nc] marketing without an
  İYS consent record (CLAUDE.md invariant 18); [D] reminder volume driving opt-outs.
- **Controls (files/10):** §9 notifications row — content-free pushes, quiet hours, opt-out;
  §4 mobile — no PHI in push or deep links; transactional-only default.
- **Signals:** `notification_dispatch_total{channel,message_class,status}` carries both
  the delivery rate and the opt-out rate off one status label, and
  `notification_preference_changed_total{change}` the opt-out flow (INT-141; both
  catalogued in `observability/metrics_catalog.yaml` — files/08 §4 names no id for this
  row, so they enter the catalogue without one).
- **Tests:** `tests/legal/test_notifications.py` — content-freedom as vocabulary closure
  (every token of a payload must already be in the committed template corpus, so any
  interpolation at all fails) plus an adversarial patient whose branch label shares a
  word with the generic copy; the four İYS locks (no commercial template; an abstract
  `IysConsentRecord` with no concrete subclass in the tree; a registry that refuses; the
  `commercial_messaging` safety flag); quiet hours with no invented default; opt-out.
  `tests/api/test_notification_prefs.py` — the persisted register, its route declaration
  and its survival across a restart. `apps/mobile/e2e/notifications.spec.ts` — the app
  never assembles a body and grows no marketing switch.

## `mobile` — the patient app (MASVS)

- **Assets:** tokens in SecureStore, clinical screens, OTA update channel, crash telemetry.
- **Trust boundaries:** app ↔ compromised OS (attestation as a soft signal); app ↔ update
  channel (signed OTA); app ↔ crash reporter (no locals).
- **Threats (STRIDE/LINDDUN):** [I] token theft on a rooted device, screenshots of clinical
  screens, crash reports serialising local variables; [S/T] OTA supply-chain substitution or
  a repackaged app; [I] transport interception where pinning does not cover a path (§4: a
  fetch-patching shim does not pin WebRTC/DTLS or file uploads — pin natively).
- **Controls (files/10):** §4 mobile — SecureStore with biometrics, FLAG_SECURE, EAS Update
  code signing, MobSF on every build, jailbreak/root as a soft signal degrading to typed
  mode, native ATS/`network_security_config` pinning with a documented rotation recovery
  path, first-party attestation module (App Attest + Play Integrity + DPoP key) filed as its
  own issue; `include_local_variables=False` server-side (§3).
- **Signals:** attestation failures (§9 onboarding row) and crash-free-session tracking (§6)
  land with INT-145/INT-146.
- **Tests:** MobSF gate lands with INT-146; telemetry scrubbing tests with INT-145.

## `experience` — satisfaction and wait-time measurement

- **Assets:** CSAT/NPS responses, clinician pulse data, wait-time rollups.
- **Trust boundaries:** survey responses ↔ clinical record (linkable only where consented);
  free-text feedback ↔ analytics pipelines (PHI can arrive uninvited).
- **Threats (STRIDE/LINDDUN):** [L] linking satisfaction data to clinical content beyond
  need; [I] patient-typed free text carrying identifiers into analytics; [U] respondents
  unaware of how feedback is used.
- **Controls (files/10):** invariant 6 (ids only in analytics); k-anonymity floor on
  aggregates (k ≥ 10, §9 admin row); redaction baseline (§3) applied to free-text ingestion.
- **Signals:** `csat.score`, `csat.reason`, `nps.monthly`, `clinician.pulse` — catalogued
  `live` and emitted by `intake_metrics.metrics`, published only for a named cohort over a
  stated window and only at or above the k ≥ 10 floor. No tenant, clinic or clinician label
  on any of them, so no dashboard can re-slice a satisfaction series down to one person.
- **Tests:** `tests/experience/test_csat_flow.py` (the split: scores to `events`, the sentence
  to the envelope-encrypted `csat_texts`; the §3 redaction baseline on ingestion; the response,
  the audit entry and the event payload all free of the patient's words; both FK cascades, so
  a DSAR erasure and the files/06 §3 `satisfaction` clock each reach the text) ·
  `tests/experience/test_rollups.py` (`test_a_rollup_of_adversarial_responses_exposes_none_of_it`
  — a symptom sentence, a phone number and a clinician's name forced into the very rows the
  rollup reads, exposed nowhere in the rollup or the exposition; k ≥ 10 suppression) ·
  `tests/experience/test_metrics_service.py` (invariant 15 for `services/metrics`; invariant 20:
  no CSAT/NPS figure in docs/regulatory/ or docs/legal/).

---

### Governance and operations

## `admin-console` — the control plane

- **Assets:** admin sessions, `DangerousAction` registry, feature flags, embedded
  observability, every mutation path the console exposes.
- **Trust boundaries:** browser origin ↔ PHI stores (nothing reachable that did not transit
  `services/api/admin`); actor ↔ approver (distinct human, authenticator, session, org for
  tier-3); safe direction ↔ dangerous direction (asymmetric authority).
- **Threats (STRIDE/LINDDUN):** framed by §9 as "not privilege misuse — a patient-safety
  event, a device-classification breach, or unlawful Art. 9 processing": [E] the parallel
  authorization plane (Grafana/Langfuse/Unleash reached directly); [T] an unrecorded
  `device_functions` flip or a forged four-eyes ceremony; [I/L] IDOR via `?tenant=` and
  single-patient aggregates; [S] a phished approver.
- **Controls (files/10):** §9 admin row — server-rendered panels only, gated-capability
  service with tier-3 four-eyes and write-ahead audit, signed Study Registry with expiry and
  no grace, tenant scope from the OIDC claim with a per-request DB role, four-eyes as a
  server-side pending-action protocol (distinct AAGUID/credential id), asymmetric authority,
  k ≥ 10 on aggregates, nonce CSP with no `unsafe-*` (inv. 48), `DangerousAction` registry
  (inv. 33).
- **Signals:** group O (§7): device-flag and study-assertion changes, break-glass rate and
  patient-log lag, pack promote/quarantine, connector and allow-list changes, privileged
  role grants, `admin.four_eyes_self_approval_attempt_total` (an intrusion signal),
  audit `seq` gaps, external-anchor age, access-review age; `sec.admin_actions_total` and
  `sec.break_glass_total` with alerts actually attached — land with INT-180…INT-192.
- **Tests:** invariants 31–34, 36–40, 47–48 land with the console issues (INT-180 onward);
  the role × tenant matrix with INT-180.

## `device-boundary` — MDSW mode and the study lifecycle

- **Assets:** the `device_functions` capability, the Study Registry, the research store
  clock.
- **Trust boundaries:** certified ↔ uncertified functionality (gate INT-117); study approval
  window ↔ the calendar (expiry de-asserts with no grace).
- **Threats (STRIDE/LINDDUN):** [Nc] an uncertified Class IIb device function placed into
  service; [T] a stale study assertion outliving its approval — the default outcome rather
  than an attack (§9); [R] a device-mode change with no attributable record.
- **Controls (files/10):** §9 device row — gated-capability service as the sole write path,
  `clinical_lead` + `qms_owner` from different organisations, server-side study-reference
  validation, write-ahead audit, immediate page, 60 s reconciliation probe failing closed,
  signed registry with `approval_valid_until`, daily fail-closed probe, weekly reconciliation
  against the enrolment log, study-close runbook; inv. 34/35.
- **Signals:** `admin.device_functions_changed_total{direction}`,
  `admin.study_assertion_changed_total`, `acoustic.assertion_expiry_days`,
  `admin.study_registry_probe_status` (named in §9) — land with INT-117 and the console
  issues.
- **Tests:** the INT-117 gate test (INT-117's acceptance); inv. 34/35 extend it to the
  registration side with the console issues.

## `learning-loops` — proposal-only learning

- **Assets:** evidence bundles, proposal PRs, de-identified analytics views, PatientOverlay
  facts.
- **Trust boundaries:** learning agent ↔ everything it may not touch (red-flag levels,
  instruments, consent texts, the Talker tool list, PolicyGuard, profile routing — CLAUDE.md
  invariant 12); aggregates ↔ individuals (k ≥ 10).
- **Threats (STRIDE/LINDDUN):** [T] poisoning through crafted proposals; [Dd/L]
  de-anonymisation of small cohorts; [E] agent over-reach past the proposal boundary.
- **Controls (files/10):** §9 learning row — proposal-only with evidence bundles, k ≥ 10,
  sandboxed agent with read-only credentials, PR bot least privilege, canary and rollback;
  PatientOverlay facts require patient or clinician confirmation at type level.
- **Signals:** k-anonymity refusals landed with INT-171 —
  `analytics_view_refused_total{view,reason}` and `analytics_view_materialised_total{view}`,
  whose labels carry a view name and a reason class only, because a refusal labelled with
  the branch or the week it withheld would publish that cell to Prometheus. Proposals,
  rejections and rollbacks land with INT-172/INT-173.
- **Tests:** `k_anonymity` landed with INT-171 (`tests/learning/test_k_anonymity.py`, plus
  `tests/learning/test_analytics_views.py` and its integration lane, which proves the
  `svc_learning_reader` grant reaches the `analytics` views and no base table);
  `proposal_scope` lands with INT-172; overlay monotonicity property test with INT-056.
- **Stated narrowly, because the wide claim is false (INT-171):** the views are aggregate
  and structured — protocol pack and version, slot id, attribution, ISO week, and counts of
  sessions, subjects and tenants. They carry no narrative, redacted or otherwise, and no
  pseudonym survives the `GROUP BY`. Turkish clinical free text is not de-identifiable to a
  standard this repo will assert (files/10 §3 on realistic Turkish recall; HB-L6 on the
  claim itself), so narrative is **excluded rather than scrubbed**. The grant is the
  narrative boundary; the k ≥ 10 gate at the query layer is the small-cell boundary; and
  the gate refuses the whole artefact rather than suppressing a cell, because a reader
  holding every cell but one recovers it by subtraction.

## `incident-response` — detect, contain, notify, learn

- **Assets:** the detection stack, the audit chain, notification clocks (KVKK 72 h, 7545
  without delay, DPA notice to the controller), incident records.
- **Trust boundaries:** incident communications ↔ PHI (ids only, always); internal timeline
  ↔ regulator-facing packet (built only from preserved evidence).
- **Threats (STRIDE/LINDDUN):** [De/D] a P1 signal with no pager attached (files/10 §7 names
  the metric-without-an-alert failure mode); [R/Nr] evidence not preserved before
  containment destroys it; [Nc] a missed Board or USOM clock; [I] PHI pasted into tickets or
  chat during the response.
- **Controls (files/10):** §7 — Wazuh + Falco + CrowdSec + OTel security events; the
  runbook at docs/security/incident-runbook.md (this issue): severity ladder, first-15-minute
  checklist, containment in the safe direction with one-actor authority (§2), forensics on
  immutable logs, notification pointers to the INT-214 machinery; quarterly tabletop and the
  twice-yearly breach drill (files/06 §1 KVKK-12-breach).
- **Signals:** the §7 signal list end-to-end; pager wiring lands with INT-205 and INT-021.
- **Tests:** tests/security/test_threat_model.py (runbook shape and claim scan);
  tests/docs/test_threat_model_rows.py (this file tracks the backlog); the 72 h drill test
  lands with INT-214.

## `billing` — payments, later

- **Assets:** subscription state, invoices; never card numbers.
- **Trust boundaries:** our systems ↔ the PSP (PAN stays with the PCI-compliant provider).
- **Threats (STRIDE/LINDDUN):** [I] card-data exposure through scope creep; [Nc] PCI scope
  accepted by accident; [S] payment-flow spoofing toward patients.
- **Controls (files/10):** §9 billing row — delegate to a PCI-compliant PSP (iyzico/PayTR),
  never store PAN; e-Fatura via provider (backlog INT-251).
- **Signals:** files/10 §9 leaves this row's signal column empty until the feature exists;
  they land with INT-251.
- **Tests:** land with INT-251 and INT-222.
