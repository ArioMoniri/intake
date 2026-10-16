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
- **Signals convention.** Metric names quoted in backticks are the names files/10 gives;
  each signal says which issue lands it. The closed registry is
  `observability/metrics_catalog.yaml` (INT-025, CLAUDE.md invariant 13): a name is emitted
  today only where its entry says `status: live`, and a `planned` entry is a committed name,
  not a signal. (Until the INT-020 close-out this bullet said the catalogue did not exist
  yet; it has since INT-025.)
- **Tests convention.** Paths named without qualification exist in the repo today. Everything
  else says "lands with INT-nnn" — a guard cited for a property it does not yet test is worse
  than no guard (files/10 §3) — or, where no backlog row carries the guard at all, says
  "unowned" rather than naming an issue that does not exist.
- **No performance figures.** Per ADR-022 and CLAUDE.md invariant 20, this file carries no
  model-quality numbers of any kind; measurements live in docs/evidence/ with a date and a
  named corpus. `tests/security/test_threat_model.py` scans this file for claim language.
- **Invariant numbers** (`inv. N`) refer to the catalogue in files/10 §9.1 (12–49). Numbers
  50–65 are reserved and unspecified (files/10 §9.2) — nothing here cites them as enforced.

Incident handling for everything below: `docs/security/incident-runbook.md`.

## Seeding map: files/10 §9 features

Every row of the files/10 §9 matrix, by its first cell verbatim, and the section(s) that carry
it here. The anchor is a phrase the named section(s) must contain, so an entry cannot claim a
feature its section never discusses. `tests/docs/test_threat_model_rows.py` reads this table
against files/10 in both directions: a §9 feature with no entry fails, an entry for a feature
§9 no longer has fails, and an anchor absent from its sections fails. Added at the INT-020
close-out, when four §9 features (offline drafts, break-glass, the sealed research store, RED
acknowledgement) turned out to have no section carrying them.

| files/10 §9 feature | section(s) | anchor |
|---|---|---|
| Onboarding / OTP / profile | `onboarding` | `SMS pumping` |
| Consent layers | `consent` | `re-prompt` |
| Companion / guardian profiles | `companions` | `proxy` |
| Visit creation / SMS screenshot OCR | `visits` | `OCR` |
| Voice intake (runtime) | `intake-voice`, `voice-runtime` | `DTLS-SRTP` |
| Typed intake | `intake-typed` | `input limits` |
| Council verifier (`llm-boundary`; INT-430, ADR-036) | `llm-boundary` | `INT-430 (ADR-036): the council verifier` |
| Triage RED / YELLOW | `triage` | `set me green` |
| Wellbeing screening & observer lanes | `wellbeing`, `observer-lanes` | `biometric drift` |
| Records upload & ingestion | `records` | `ClamAV` |
| Review & send | `review-send` | `over-share` |
| Doctor Link | `doctor-link` | `watermark` |
| Clinician web / clinic console | `clinic-console` | `session hijack` |
| Share centre / issue / revoke / export / delete | `share-centre`, `dsar` | `INT-311` |
| Connectors (FHIR/HBYS/e-Nabız) | `connectors` | `SSRF` |
| Residency / self-hosting attestation (public-hospital, INT-221) | `self-hosting` | `Genelge 2019/12` |
| Partner embed / white-label launch (`embed`) | `embed` | `ADR-029` |
| Check-in / kiosk | `kiosk` | `ephemeral` |
| Notifications / reminders | `notifications` | `content-free` |
| Offline drafts + sync (`mobile`, INT-142) | `mobile` | `INT-142` |
| Protocol registry & clip cache | `protocol-registry` | `tampered clip` |
| Learning loops | `learning-loops` | `proposal_scope` |
| Admin console | `admin-console` | `IDOR` |
| Break-glass / access to patient content | `admin-console` | `POST /admin/break-glass` |
| Device mode & study lifecycle | `device-boundary` | `approval_valid_until` |
| Protocol pack lifecycle & safety strings | `clinical-content`, `protocol-registry` | `override_text` |
| Instrument licensing | `wellbeing`, `clinical-content` | `inv. 45` |
| Research store (sealed) | `device-boundary` | `sealed research store` |
| Clinician provisioning | `tenants` | `tenant_clinical_responsible` |
| RED acknowledgement (`02 §8`) | `triage` | `inv. 49` |
| Observability pipeline | `observability-pipeline` | `SafeError` |
| Backups / DR | `backups` | `restore` |
| Billing (later) | `billing` | `PAN` |

## Module map: services, apps and packages

Every top-level directory under `services/`, `apps/` and `packages/`, and the row(s) that own
its threats. A new module fails `tests/docs/test_threat_model_rows.py` until it has an entry
here, and an entry naming a module that no longer exists, or a row with no section, fails too.
The first row listed is the module's primary owner; the rest are rows whose controls live in
it or whose tests exercise it.

| module | row(s) | what it holds |
|---|---|---|
| `apps/admin-web` | `admin-console` | the rendered ops console |
| `apps/embed-sample-partner` | `embed` | a synthetic dev-tier partner over the real handshake |
| `apps/mobile` | `mobile`, `onboarding`, `intake-voice`, `records`, `share-centre`, `kiosk`, `notifications` | the patient app |
| `packages/clinical-schemas` | `clinical-core` | the clinical data model and mappers |
| `packages/connectors` | `connectors` | hospital-system adapters |
| `packages/embed-sdk` | `embed` | the partner launcher, holding no Vizite secret |
| `packages/hosted-lanes` | `llm-boundary`, `cloud-boundary` | the hosted model-lane adapters, shipped in the synthetic deployment's image only (ADR-035) |
| `packages/intake_platform` | `observability-pipeline`, `monitoring-contract`, `api`, `audit`, `secrets`, `identifiers`, `data-at-rest`, `cloud-boundary`, `consent`, `retention`, `admin-console` | the shared platform library: redaction and OTel, health contract, security middleware, audit chain, envelope and tokenization, egress, consent and retention engines, admin primitives |
| `packages/protocols` | `clinical-content`, `protocol-registry`, `triage` | the DSL, compiler and deterministic triage |
| `packages/voice-clips` | `protocol-registry`, `cloud-clipgen`, `voice-runtime` | the clip cache, its build and the agent-audio framing |
| `services/api` | `api`, `api-surface` | the FastAPI service |
| `services/learning` | `learning-loops` | proposal-only learning |
| `services/metrics` | `experience` | satisfaction and wait-time rollups |
| `services/probes` | `self-hosting`, `monitoring-contract`, `backups` | synthetic probes, the self-hosting registry, residency attestation |
| `services/voice-runtime` | `voice-runtime`, `observer-lanes`, `llm-boundary` | the agent worker, lanes and gateways |

---

### Platform, delivery and data plane

## `platform` — monorepo and dev tier baseline

- **Assets:** source tree, Makefile entry points, compose dev tier, developer credentials.
- **Trust boundaries:** developer workstation ↔ repo ↔ package registries ↔ container images.
- **Threats (STRIDE/LINDDUN):** [T] malicious dependency or lockfile drift entering the tree;
  [I] secret committed to the repo; [E] pre-commit/gate bypass normalising unreviewed change;
  [I] **an operator script putting a secret where others read it** (INT-538's staff-user
  command: a temporary password or the Keycloak bootstrap password in an argv, the SSM command
  history, a log or the terminal); [E] **a staff account created with the wrong role or org**.
- **Controls (files/10):** §8 pre-commit set (gitleaks, Semgrep+Bandit, dependency review,
  Renovate with lockfiles); CLAUDE.md invariant 14 (gates never skipped); Makefile as the only
  entry point so gates cannot be sidestepped by ad-hoc commands. **INT-538**
  (`scripts/ops/staff_user.sh` with `infra/staging/staff_user_host.sh`): the temporary password
  goes from openssl into an SSM SecureString through a 0600 request file, the bootstrap password
  stays on the host and reaches kcadm on stdin, kcadm's throwaway `--config` is deleted on every
  outcome, the send-command carries no secret, and output is `created` plus the reveal-once
  command. Only `platform_owner` and `qms_owner` are offered. A read-only probe decides the org:
  a new user joins the platform_owner's org and a differing org is refused; only the very first
  user, who must be the platform_owner, types it once as a slug. It is never invented. An instance
  role that may not read the staff_tmp parameters is named with the IAM statement to add. A failed
  step rolls the user back.
- **Signals:** vulnerability counts by severity and age (files/10 §7) land with INT-192 on the
  console and INT-205 in the SIEM.
- **Tests:** tests/smoke/test_make_check.py; tests/ci/test_no_placeholders.py;
  tests/ci/test_coverage_floors.py; tests/infra/test_staff_user.py;
  tests/infra/test_staff_user_host.py.

## `cicd` — pipeline, artefacts and gate integrity

- **Assets:** workflow definitions, runner credentials, build artefacts, SBOMs, signing
  identity, the gate set itself.
- **Trust boundaries:** GitHub-hosted runners ↔ repo ↔ registries; PR author ↔ required
  checks. INT-206 makes every self-hosted pool a *declared* boundary
  (`infra/ci/runners.yaml`). **INT-463 declares the one pool that exists, `intake-aws-ci`**:
  an ephemeral runner on the AWS us-east-1 host that also serves synthetic staging (owner
  order, 3 Oct 2026). Every Actions job runs there, so the boundary is now job code ↔ the
  staging host. The TR-DC pool is still undeclared. HB-I7 (spend) and HB-L11 (physical
  residency is not legal residency) own it — **not HB-I5, which is GPU supply and does not
  bind a CPU CI runner** — and no TR facility, provider or label is invented to close the gap.
- **Threats (STRIDE/LINDDUN):** [T] a repointed action tag or poisoned artefact (ci.yml pins
  actions to commit SHAs for exactly this reason); [E] workflow permission escalation;
  [R] unsigned artefacts with no provenance; [Nc] a skipped security gate (invariant 14);
  [I] **a patient-shaped value reaching a CI context** — a fixture CI reads, a job's `env`,
  the retained job log, an uploaded artefact, a restorable cache; [S/E] **a job running on
  an undeclared self-hosted runner**, which is a job executing somewhere nobody decided;
  [I/E] **a job on `intake-aws-ci` reaching staging** — its files, the OpenBao tokens, the
  staging containers, the instance role through the metadata service, or the host Docker
  socket — or **leaving state for the next job**; [I/T/D] **a job on one runner of the pool
  reaching another runner's job** — its tree, its Docker daemon and containers, or a port
  its containers publish — or **one runner's post-job wipe destroying another's live job**
  (INT-467: a user, daemon, egress chain and network namespace per runner; port driver
  `none`, so no published port reaches the host);
  [T] **a known-vulnerable pin left in a lockfile** because the scanners report only on what
  is already pinned and nothing proposes the fix; [E] **a dependency bot merging its own
  update** past review and the licence gate.
- **Controls (files/10):** §8 in full — OSV/Trivy/Checkov fail-on high, licence check, Syft
  SBOM, cosign keyless signing with SLSA provenance, schemathesis, MobSF; CI carries no
  secrets and never calls a vendor (ci.yml header; CLAUDE.md). **INT-206 adds the
  no-PHI-in-CI policy** (`intake_platform.ci`, declared in `infra/ci/no-phi-policy.yaml`,
  run by `make ci-policy`): every identifier-shaped value in a scanned tree must sit inside
  a synthetic corpus a human declared *and pinned by sha256*, so a new identifier can only
  arrive through a reviewed diff; env names as well as values are scanned; a declared
  corpus may not be printed into the job log, uploaded as an artefact or cached; every
  `runs-on` must resolve to a known hosted label or a declared pool, failing closed
  otherwise. The gate's own report carries digests, never values — it runs in a job whose
  stdout is retained 30 d hot / 1 y cold (files/10 §6). **INT-368 adds Renovate**
  (`.github/renovate.json`, runbook `docs/runbooks/dependency-updates.md`): every uv, pnpm,
  container-digest and Actions pin is watched, security updates open immediately outside
  the weekly schedule, and nothing auto-merges — each update is a PR through the same gates,
  carried under an `INT-` issue because the evidence and sec_row gates refuse a bot title.
- **Signals:** integrity failures — image and protocol signature — are §7 hard signals; land
  with INT-019 (security.yml) and INT-187/INT-192 (console surfaces). Runner liveness is the
  `ci-runners` registry row's `runner_heartbeat` probe (files/08 §6), reported as a typed
  Skipped naming HB-I7 while no pool is declared — never as healthy. **INT-187 adds the
  console surface** (`/cicd`, `GET /admin/cicd`): recent runs per workflow with failing jobs,
  every PR-triggered gate per ref on `main` and the open PRs, **whether GitHub itself enforces
  any of them** (today: no — branch protection off, no ruleset, read from the API rather than
  assumed), releases with the `sign-and-attest` job's outcome, and this deployment's stamped
  `/version`. The GitHub read is the ops collector's (read-only token from OpenBao, egress
  guard, purpose `issue_tracking`); run actors, commit messages, PR titles and users never
  become labels (`ops_cicd_*`, catalogued). **The deploy freeze** is a §8.2 pair — engage
  tier 1, lift tier 2 — kept out of Unleash (a CI-held token must not lift it), and enforced
  in `infra/staging/deploy.sh` by the release gate, which also refuses on an exhausted SLO
  error budget and on a freeze it cannot read; `admin.deploy_freeze_changes_total` is the
  alert. Argo CD and a deploy canary are shown as not deployed — none exists in `infra/`.
- **Tests:** tests/ci/test_evidence_check.py; tests/ci/test_no_placeholders.py;
  tests/security/test_threat_model.py (the sec_row linkage gate);
  tests/infra/test_ci_no_phi.py (INT-206: the six surfaces, the pool schema and the
  heartbeat probe); tests/ci/test_dependency_updates.py (INT-368: ecosystem coverage from
  the tree, unscheduled security updates, no auto-merge anywhere); full gate job lands
  with INT-019. INT-187: tests/admin/test_cicd_console.py, tests/admin/test_cicd_routes.py,
  tests/admin/test_deploy_freeze.py, tests/observability/test_ops_cicd.py,
  tests/infra/test_staging_release_freeze.py and apps/admin-web/e2e/cicd.spec.ts.

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
  tests/security/test_envelope_transit_unit.py; RLS exercise lands with INT-030;
  tests/data/test_sensitive_slot_categories.py (INT-349: an answer in any protocol data
  category but `general_health` is an envelope bound to its session and slot, never
  plaintext at rest).

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
  **[I/Dd] added INT-203, found by booting the tier:** the WAF itself is a PHI channel.
  CRS rules carry `logdata`, so a blocked request's log line quotes the matched argument
  back — on this API that argument is `ARGS:json.text_tr`, the patient's utterance, and
  `[uri …]` carries the query string. Shipping the line to the SIEM trades an injection
  attempt for a disclosure that succeeds, is durable, and looks like a control working.
  **[D] added INT-203:** the opposite failure is equally invisible from a config file —
  a WAF that refuses ordinary Turkish clinical prose (`Ali'nin`, `1x1 sabah/akşam`,
  `<acil>`) takes the product off the air while every dashboard reads "protected".
- **Controls (files/10):** §4 edge — Traefik/Envoy with Coraza (OWASP CRS), CrowdSec,
  egress proxy with allow-list where every call is logged with vendor, purpose and bytes
  (doubling as KVKK transfer evidence); allow-list as live console configuration.
  **INT-203:** one policy (`infra/security/edge/edge-policy.yaml`) renders Traefik's
  static and dynamic configuration, the CrowdSec scenarios and acquisition, and the
  cert-manager manifest, so the four enforcement points cannot drift; the schema refuses
  `DetectionOnly`, a threshold looser than the CRS default, an exclusion wider than one
  rule × one route × one parameter, and an exclusion past its expiry. `EdgeEvent` is a
  closed record with no field a sentence could occupy — the discipline `TransferRecord`
  already applies to the egress register. Traefik's access log is field-selected `drop`
  by default and the CrowdSec parser extracts exactly two values, neither a path.
  CrowdSec's central API is off: sending client addresses to a third-party reputation
  service is a §1 transfer nobody consented to.
- **Signals:** WAF/CrowdSec blocks and egress denials — a hard alert (§7);
  `sec.cert_expiry_days` for the renewal countdown. `sec.egress_denied_total` is live
  (INT-018); the WAF and certificate series are served by Traefik's own `/metrics` on a
  non-internet entry point and stay `planned` in the catalogue until a deployment scrapes
  them.
- **Tests:** `tests/infra/test_waf_rules.py` (the policy, the renders, the log boundary,
  the CrowdSec and certificate clauses); `tests/infra/test_edge_stack_integration.py` —
  the corpus in `tests/fixtures/waf/corpus.yaml` decided against the **booted** engine in
  both directions, seven CRS families refused and five ordinary Turkish clinical turns
  served; `tests/infra/test_edge_egress.py` (the prod proxy: denied ranges, rebinding,
  redirects, the denial metric). Mesh mTLS lands with INT-204.

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
- **Signals:** multiwindow burn-rate alerts for every SLO file (INT-021); probe registry with
  INT-022; the metrics catalogue itself with INT-025.
- **Controls added by INT-021 (close-out, 27 Sep 2026):** a blind spot is now a failing test
  rather than an absence. Every `docs/slo/*.yaml` generates its recording rules, its three
  burn lanes and its golden-signal dashboard, and a hand edit to either output fails. Every
  alert in every rule file Prometheus loads links a `docs/runbooks/` heading that resolves,
  and every series a rule reads is catalogued and `live`, so a rule over a series nothing
  emits cannot pass as coverage. `observability/slo_coverage.yaml` states, for every
  discovered service, app and job, its SLO file and probe rows or the recorded reason it has
  none. An HTTP SLI must have a `mount_http_metrics` emitter in its own service (services/probes
  had none). The daily audit-chain verification now pages when it fails
  (`AuditChainVerificationFailed`, files/08 §5).
- **Tests:** tests/platform/test_health_contract.py; tests/observability/test_metrics_catalog.py
  (INT-025); tests/observability/test_slo_generator.py, test_alert_rules.py and
  test_slo_coverage.py (INT-021).
- **Controls added by INT-481 (4 Oct 2026, staging telemetry tier and staff Grafana, ADR-041):**
  the [I] label threat is closed at ingestion, not only at the catalogue. One reviewed list of
  label keys (`intake_platform.observability.labels`) is held against the catalogue, every
  rule file and every dashboard. It refuses any key that names a person, a session or a
  device, carries free text, or is identifier-shaped, unless the key is a reviewed identifier
  with its reason. Every staging scrape job ends with a `labelkeep` of exactly that list and
  caps samples, labels and value lengths. New threats this tier adds, each closed by a test:
  [S/E] Grafana as a second console (files/08 §0b F1). It reads Prometheus only, sits on its
  own origin, client and cookie behind a staff session with an ops-console role, and has no
  password, admin account, Explore or anonymous access. It is linked from the console, never
  framed. [I] a Grafana or proxy log line with an email: Grafana logs errors only and the
  gate's request and auth logs are off. [Dd] egress from the tier: internal networks only,
  no published port, no receiver that sends anywhere, and no plugin or update traffic.
  [I] alert text in the console: `GET /admin/alerts` returns names, states and id labels
  only, never annotations or the generator URL. Signals: SyntheticProbeFailing,
  ScrapeTargetDown, the host disk and memory alerts and the deploy markers
  (infra/staging/observability/staging-rules.yaml). Tests:
  tests/observability/test_metric_labels.py, test_ops_dashboards.py,
  tests/infra/test_staging_obs_tier.py, tests/admin/test_alerts_console.py,
  apps/admin-web/e2e/alerts.spec.ts.

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
  **(INT-100)** `vendor_breaker_state` (one-hot per component), `vendor_breaker_transitions_total`
  and `vendor_failovers_total` (`to_component="typed"` when no speech lane is left), all
  catalogued live.
- **Tests:** chaos harness and fallback timing land with INT-024, INT-100, INT-207.
  **(INT-100)** `tests/chaos/test_vendor_failover.py` kills the primary TTS lane mid-turn (dead,
  dying in flight, hung) under a real Talker turn and proves the next lane or the screen within
  2 s of virtual time, with the Backend stalled underneath (invariant 9); the order is read from
  `observability/registry.yaml` and a cloud fallback on the PHI path is refused (invariant 19).
  Unit coverage in `tests/voice/test_vendor_resilience.py`.

## `self-hosting` — model supply chain and residency

- **Assets:** model weights, the model/self-hosting registry, GPU tier, licence records.
- **Trust boundaries:** internal registry ↔ upstream sources (no runtime downloads in prod);
  PHI path ↔ any vendor adapter.
- **Threats (STRIDE/LINDDUN):** [T] weight substitution where a revision is not pinned;
  [Nc] a non-commercial or unverified licence on the PHI path; [I/Dd] a dev-only cloud
  adapter reachable from production; [Nr] (INT-221) a `tr-residency` tenant's vendor-free
  posture asserted without proof, or a fabricated Genelge 2019/12 attestation authored by a
  process rather than counsel.
- **Controls (files/10):** §5 LLM03 — weights pinned by `model_id@revision + sha256`,
  mirrored internally, prompts versioned and signed; CLAUDE.md invariant 19 — licences
  verified from the raw LICENSE blob with `licence_verified_at`; the `anthropic|openai|google`
  adapters are mock/dev only and blocked on the PHI path by the egress allow-list. **(INT-221)**
  a residency attestation that cross-checks the two committed sources — every `phi_path` row
  `self_hostable: true` (registry) and `assert_dev_only_vendors` (egress) — and fails closed;
  the Genelge 2019/12 attestation ships with its legal statement empty and refusing to render
  until counsel signs (`awaiting-human` HB-L11), never authored by a process.
- **Signals:** per-model probe status (§6) lands with INT-022 and INT-183; egress denials and
  allow-list changes (INT-018/INT-192).
- **Tests:** registry and provenance checks land with INT-022/INT-183; egress blocking with
  INT-018; residency attestation + USVS conformance with INT-221
  (`tests/legal/test_residency_attestation.py`, `tests/legal/test_usvs_conformance.py`).

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
  caps), device attestation on OTP request and session start, rotating
  device-bound refresh tokens with family revocation on reuse, passkeys, biometric gate,
  generic error messages (§9 row 1). §2's `carrier/geo sanity` check runs on the request
  path as of INT-308, in two halves: **geo** is enforced by Turkish-mobile-only
  normalisation, so an international premium range never reaches a delivery adapter;
  **carrier** is `intake_api.carrier_geo` over `infra/security/msisdn_allocation.yaml`,
  which declares **zero allocated prefixes** and therefore admits every request. ⚠ Until
  a human supplies that list (docs/backlog/blockers.md — which 5XX prefixes the BTK has
  allocated, against a source that can be re-read), the request budgets below and the
  Turkish-only normalisation remain the whole of what enforces §2's SMS-pumping control.
- **The carrier/geo asymmetry, stated (INT-308):** a lookup that cannot be made **admits**
  — no authority, an unreadable table, an authority that raises or times out, a prefix the
  authority has no opinion about — and only a **positive** signal refuses: a prefix absent
  from a list that declares itself `exhaustive`. A carrier check that failed closed would
  lock a patient out of their own intake the first time a lookup timed out, which is a
  worse failure than the cost it prevents. The refusal reuses the generic `phone_invalid`
  code, so it is not an oracle for which numbers exist, and it sits **after** the abuse
  gate so a refused caller still spends its budget. The seam is handed a country code and
  an operator prefix, never the subscriber number: a vendor lookup that needs the whole
  MSISDN is a different control with its own lawful-basis and licence question, and is
  deliberately not built. Nothing is persisted, so no new inventory annotation is owed.
- **The request-budget bound, stated (INT-263):** the per-phone, per-IP and per-device
  budgets are counted in a **rolling** `OTP_WINDOW_S` window, not per fixed hour. No more
  than 3 requests per phone, 10 per IP and 3 per device are admitted in **any** 3600-second
  span — measured backwards from each request, so an hour boundary hands no budget back —
  and a refused caller is told the true wait for that bound (the instant enough of the
  admissions in its window have left it), never the time to the next boundary. INT-131
  shipped fixed hourly buckets, which enforced **2 x the limit inside a rolling hour** — six
  codes to one phone in about six minutes, floored only by the 60 s resend cooldown; INT-285
  measured that and left it, INT-263 narrowed it. Enforced in
  `services/api/src/intake_api/auth_store.py` (`otp_request_gate`), constant work per request
  over a key set of one sorted set per (dimension, identifier) holding at most that
  dimension's limit.
- **The device-attestation bound, stated (INT-344):** on iOS the OTP request and the
  session start each carry an Apple App Attest **assertion** from a Secure Enclave key the
  server registered once from an **attestation** (`POST /v1/auth/attest/key`). The
  attestation must chain to the Apple App Attestation Root CA committed at
  `services/api/src/intake_api/trust/` and pinned by SHA-256 in code and in a test; commit
  to SHA256(authData ‖ SHA256(clientData)) in credCert's extension
  1.2.840.113635.100.8.2; carry this app's rpIdHash (team id from
  `INTAKE_APP_ATTEST_TEAM_ID`, never a literal), counter 0 and the production aaguid
  (`appattestdevelop` only when development is configured explicitly); and name its own
  key. Each assertion must verify under the stored key, carry the rpIdHash, and move the
  counter strictly forward (an atomic compare-and-set). clientData binds the call's purpose
  and a single-use server challenge, which the service spends **before** any verifier runs —
  so a proof is good for one call, and a refused one still burns its challenge. Absent
  Apple config the verifier fails closed with `app_attest_not_configured`. **Android fails
  closed** (`play_integrity_not_configured`): the Play Integrity verdict policy exists, but
  no decoder can exist until the Play Console organisation account does (HB-A3). The
  stored record is a public key, a counter and an environment — the same class of datum as
  the DPoP thumbprint — kept 30 days rolling.
- **The SMS delivery bound, stated (INT-329):** outside dev the OTP tier is wired only when
  the egress policy admits `EgressPurpose.SMS_OTP_DELIVERY` to `api.twilio.com` **and** OpenBao
  holds `secret/api/twilio` (`account_sid`, `auth_token`, `from`). The `TWILIO_*` environment
  variables are never read. Anything missing leaves every `/v1/auth` route at 503, and the dev
  event logger is never the fallback (INT-325). The send is async, over the INT-018 guard's
  async twin, which runs the same admission step and pins and records exactly as the sync one
  does. The call is declared `DataClass.PHI`, so it can only reach a `phi_allowed` row that
  carries a recorded approval. **No such row ships.** Personal data to a processor abroad is
  the owner's DPA and cross-border decision (docs/evidence/INT-329.md), so today the tier
  stays at 503 outside dev, and the guard would refuse the call before a byte left anyway. A
  failed delivery is one generic `503 otp_delivery_unavailable`, never a claimed "sent". The
  log line carries the vendor message id, the HTTP status, a closed-vocabulary reason and
  Twilio's numeric error code, never the phone, the code, the token or a vendor body (its
  errors echo the number). No retry: a retried SMS would put a second code in flight.
- **Signals:** OTP request/fail rates by ASN, attestation failures, new-device logins (§9)
  land with INT-131 and the console with INT-192.
- **Tests:** abuse-path tests land with INT-131; the rolling bound over any span, the
  boundary-crossing refusal on all three dimensions, the true retry-after (including under a
  budget tightened while windows are live) and the bounded counter key set with INT-263
  (`tests/security/test_otp_abuse.py`); the carrier/geo asymmetry (a failing lookup admits,
  a positive signal refuses before any SMS), its near-miss controls (an allocated prefix
  under the same table still gets its SMS; a partial list has no opinion) and the
  no-new-storage assertion with INT-308 (same file); schemathesis with INT-019. App Attest
  with INT-344: every attestation and assertion check refusing on its own, Apple's
  published example verifying against the pinned root, the pin itself, the replayed and
  misbound challenge end to end, and the Play Integrity verdict policy
  (`tests/api/test_attestation_verifier.py`, `tests/api/test_attestation_otp_flow.py`,
  `apps/mobile/src/lib/auth/attestation.test.ts`). SMS delivery with INT-329: each vendor
  outcome mapped to one typed reason over MockTransport; no phone, code or token in any log
  record, error chain or transfer record; the event loop keeps running during a send; the
  wiring matrix for `prod` and `staging`; the route's generic 503
  (`tests/api/test_otp_twilio.py`, `tests/api/test_otp_twilio_wiring.py`). The async guard
  matches the sync one on a parity table (`tests/security/test_egress_async.py`), and the
  shipped allow-list refuses the SMS purpose on every tier
  (`tests/security/test_egress_allowlist.py`).

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
- **Signals:** access-review age and drill status (§7) land with INT-189. INT-215 binds each
  KVKK 2018/10 measure to a catalogued metric or a registered probe, and a control with no
  live signal must own that absence as a gap rather than read as done.
- **Tests:** schema-annotation completeness lands with INT-211; module tests with INT-189.
  `tests/legal/test_2018_10_mapping.py` (INT-215) answers [R] for the Board's adequate
  measures: every measure quoted verbatim from a committed snapshot of RG 30353, every cited
  path, test id and signal resolving, every gap naming an owner, and the auditor packet
  (`make evidence-2018-10`) exported through the invariant-47 guard.

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

### INT-407 — the visit lifecycle (files/02 §2b): a RED visit cannot silently move

- **Assets:** the visit's lifecycle state (`visit.lifecycle`, a plain slot on the session
  row — no new table or column), its datetime, the shares and Doctor Links hanging off its
  note, the queued T-24h confirm, the clinic Safety inbox.
- **Threats:** [D·safety] a RED-flagged visit rescheduled or cancelled with nobody told —
  *"invisible to everyone"*; [S·safety] a check-in that claims `ON_SITE` from a geofence in
  the car park or a QR scanned by a relative, turning a RED's 112 into "walk to the acil"
  for someone outside; [I] a cancelled visit's note still readable by the clinic or through
  a Doctor Link; [I] a Doctor Link that expires before (issue-time anchoring) or outlives
  (a stale anchor after a reschedule) the visit it serves; [T] a lost update re-planning a
  cancelled visit; [R] a move with no record of who made it.
- **Controls:** a typed machine refuses every move outside the table (409, nothing
  written) and audits each move by id (`visit:<id>/transition:<id>`); the row is locked
  `FOR UPDATE` for the move. A reschedule or cancel reads the INT-406 inbox **before**
  writing and writes its entry **before** committing — unwired or unreachable, the move is
  refused (503); no connector is on the path. The patient re-show is a pointer (rule,
  register, location) at the pre-positioned script, in the RED's recorded register, with
  location re-derived — `UNKNOWN` outside a session; a register never recorded is not
  guessed and `DEFERRED_CLINICIAN` is not shown. Check-in evidence is certain only on an
  affirmative signal; anything else is `UNKNOWN`, never `ON_SITE` (invariant 21). A cancel
  revokes every share and link (routing hints dropped) and withdraws the clinic's read;
  a reschedule re-pins live links (row and hint) to the new `visit_datetime + 72 h` and
  never revives a revoked or expired one. The T-24h confirm is queued transactional-only,
  has no `sent` state, and the dispatch seam refuses before any transport (no SMS vendor,
  INT-358; no reviewed body). The delta-session offer is behind a safety flag.
- **Signals:** every move and every hook is a hash-chained audit row by id
  (`api.visit.transition.*`, `api.note.share_revoked`, `api.doctor_link.revoked`,
  `api.visit.clinician_entry_withdrawn`, `api.doctor_link.expiry_repinned`); the RED moves
  land in the Safety queue and page on INT-406's clock.
- **Tests:** `tests/platform/test_visit_lifecycle_machine.py` (every (from, to) pair, the
  guards, location, the confirm gate), `tests/api/test_visit_lifecycle.py` (route, cancel,
  reschedule with the issue-time near-miss, staleness, check-in doubt, the queued confirm),
  `tests/safety/test_red_visit_transition.py` (RED move → entry with no connector on a fake
  clock, the re-show per register, near-miss controls, fail-closed inbox).

## `intake-voice` — the patient-facing voice session

- **Assets:** live audio, session tokens, the RED delivery path, patient trust in the voice.
- **Trust boundaries:** patient's room (who else is present?) ↔ the session; device ↔ SFU.
- **Threats (STRIDE/LINDDUN):** [I] eavesdropping and third-party presence during sensitive
  sections; [S] a different speaker answering for the patient; [D] network loss at the worst
  moment (during a RED); **[D] the patient cannot stop or correct the agent** — until
  INT-291 the only interrupts were a screen tap and a typed message, so a patient who
  needed to correct a question mid-sentence had no voice route at all.
- **Controls (files/10):** §5 voice transport — per-session room tokens with minimal grants
  and 10-min TTL, DTLS-SRTP, ephemeral rooms, no SFU recording; inv. 26 — on
  `third_party_present` before a sensitive section, typed/keypad is offered; CLAUDE.md
  invariant 21 — the RED script is pre-positioned on the device, data channel only, and a
  barge-in arriving while it plays is **refused** (INT-291), because inside RED ambiguity is
  the harm; the barge-in path carries no priority and never reaches the Work queue, so
  invariant 9's single preemption is unchanged; invariant 3 is untouched — the onset signal
  is an id and a timestamp, never frames.
- **Signals:** round-trip latency and vendor errors (§9 voice row) land with INT-135/INT-103;
  `voice.barge_in_stop_ms` (≤ 150 ms, files/08 §4 group B) is **live** with INT-291, and
  stays a separate series from `preempt.red_latency_ms` so one target is readable per cause.
- **Tests:** RT-01…RT-12 scenarios land with INT-094 and INT-102. The barge-in stop, its
  refusal under RED and its non-preemption are `tests/voice/test_barge_in.py` (INT-291) on
  the same virtual clock INT-093 uses; the onset rule itself is
  `apps/mobile/src/lib/dialogue/bargeIn.test.ts`, pure so that it is provable without a
  microphone.

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
- **Tests:** the Work queue's own half — FIFO, single state Work in flight, serialised
  engine writes, content-addressed dedupe and the derived-never-requested `preempt` — is
  `tests/voice/test_work_queue.py` (INT-092), which also covers RT-05 and the
  "[D] stalled Backend" threat by holding a handler open on one thread while `submit`
  returns on another. **INT-094 adds `tests/voice/test_invariants.py`**: files/03 §4.6
  invariants 1–11 asserted against the *composed* stack — one real `IntakeEngine`, one real
  `BackendAgent`, one real `TalkerSession` and one real `RedPreemption` on one virtual
  clock — plus RT-01…RT-08. Two things there are load-bearing for this row. (a) The
  "[D] stalled Backend" threat is now measured end to end rather than at the queue: ten
  seconds and one hour of Backend stall produce the *same* turn latency, and a permanent
  positive control shows the same interval on the turn's own path costing the full amount,
  so the assertion cannot pass against a clock that never moves. (b) The "[E] tool-list
  growth" threat gains a composed form: a whole turn against a watched engine touches
  `snapshot` and nothing else. Guards 12–19/27/28 land with INT-090, INT-110, INT-115.
- **Known-open joints (INT-094), closed by INT-095, and what the closing cost:** the three
  joints were an unregistered `extract_slots` handler, an uncalled `mark_asked`, and a
  `WorkRequest` with no transcript channel. Two are now wired and their assertions in
  `tests/voice/test_invariants.py` were rewritten to their positive form (the class is
  `TestTheLoopThatNowCloses`); the third is **deliberately unchanged**, and that is the
  security-relevant part.
  - **The transcript route (invariant 14, invariant 6).** The queue was PHI-free by
    construction and stays PHI-free by construction: a transcript is deposited into
    `intake_voice_runtime.transcript.SessionTranscripts`, a per-session in-memory vault keyed
    by the same `sha256` the request already carried in `input_hash`, and the state handler
    takes it back out by that digest. No `WorkRequest` field, no `WorkRecord` field, no log
    line and no metric label changed — `test_the_work_request_still_has_no_transcript_channel`
    is kept, not struck. The **boundary crossing moved earlier**: the vault stores
    `PatientData`, so INT-083's refusal of a planted control token now happens *before* a
    Work exists, and a handler cannot be handed a bare `str` at all. Three costs are recorded
    rather than hidden: a Work is no longer replayable from its record alone (a restart finds
    an empty vault and the Work fails `TranscriptNotHeld` instead of binding nothing); the
    vault is a bounded FIFO whose eviction turns Layer-B starvation into a *visible* failed
    Work; and it is process memory, so what applies is invariant 6 (nothing rendered, nothing
    logged — swept **decoded**, because JSON escaping hides an escaped Turkish sentence) and
    not invariant 3, which is about audio buffers.
  - **The ask ledger (invariant 9).** `mark_asked` is a Layer-B *write* and the Talker holds
    a read-only snapshot, so the fact travels rather than the lock: `AskLedger.note_asked`
    takes only the cheap queue lock, and `BackendAgent.run_pending` applies the notes under
    the engine lock *before* either lane runs. Taking the engine lock on the speech path
    would have made a turn wait on whatever handler was running — an LLM call — which is
    invariant 9's second clause broken inside the Talker. Measured against the live bridge:
    a real extraction that took **29 106 ms** left `submit` at **0.6 ms**.
  - **The composition root (invariant 19).** Registration lives in
    `intake_voice_runtime.composition` and nowhere else — a test pins the file list — so
    "which model is this session running?" is answered by reading one function rather than
    by grepping. `intake_voice_runtime.adapters.pins` resolves a files/03 §4.9.1 row to a
    registry pin and **refuses a PHI-path lane** whose licence has no dated blob reading;
    rows 1, 2 and 7 all refuse today (HB-M1, HB-M2).
  - **No public host reaches a speech lane (invariants 14, 19).** The ASR and TTS adapters
    refuse any endpoint that is not loopback, a private/link-local address or a
    cluster-internal name — default deny, deliberately **not** a vendor blocklist. A
    blocklist of the four deleted vendors is one a fifth vendor walks past, and writing those
    hostnames down is exactly what `scripts/ci/assert_no_vendor_calls.sh` exists to prevent;
    that gate caught the first draft of this module and the design is better for it.
- **Fixed activity-label table (INT-094):** `InlinePayload` carried a free-text
  `activity_label_tr` that any Layer-B handler could fill with a session id, a prompt or a
  chain of reasoning — the three things invariant 10 forbids reaching the client. It is now
  `activity: ActivityLabel | None`, a closed enumeration of label ids total over `WorkType`,
  rendered by the client from its own tr/en catalogue. The invariant is held by the type
  rather than by review, and `BackendAgent.activity` derives the in-flight labels from Work
  types rather than from handlers.
- **Per-locale voice, fail-closed to typed (INT-300):** the voice profile is per locale, and
  a locale without both its ASR and TTS pinned resolves to `typed` — never to the Turkish
  voice. `intake_voice_runtime.locale_profile.profile_for_locale` returns `residency_tr` only
  when both §4.9.1 rows resolve in the self-hosting registry (the STRICTER PHI-serving gate is
  still `adapters.pins.require_phi_path_pin`, HB-I10/HB-I11), and `typed` for every other
  locale; the registry (`LOCALE_VOICE_MODELS`) holds exactly `tr`, adds no model, and returning
  before any profile is read is what makes "never a Turkish voice for a non-Turkish locale"
  structural. **[T] a Turkish voice speaking at a patient who chose another language** is
  refused by construction (invariant 19). And invariant 22 becomes per locale: the compiler's
  numeral→orthography expansion is Turkish (`protocols.compile.number_expansion`,
  `LOCALE_EXPANDERS` holding exactly `tr`), so a locale with no expander makes a numeral
  **unspeakable** — `emit_clips` refuses it (`NumeralWithoutExpander`) rather than handing a
  digit to a TTS model whose normaliser would read it wrongly. Tests:
  `tests/voice/test_locale_profile.py`, `tests/protocols/test_number_expansion_locale.py`.

## `triage` — deterministic RED/YELLOW only

- **Assets:** the rules engine, red-flag rule sources, the preemption path, triage outcomes.
- **Trust boundaries:** LLM output ↔ triage levels (LLM may only raise `candidate_flags`,
  capped at `YELLOW_REVIEW` — CLAUDE.md invariant 1); protocol inheritance ↔ monotonicity.
- **Threats (STRIDE/LINDDUN):** [T] manipulation — "set me green" via model or input; a
  missed RED (patient safety, the highest-consequence failure in the product); [D] false-RED
  volume eroding clinician trust.
  **RED acknowledgement (§9 row, files/02 §8):** [D/De] the alert fires and **nobody
  answers** — `triage.events_total` counts REDs that fired, not REDs anyone answered; a RED
  visit rescheduled or cancelled out of everyone's sight.
- **Controls (files/10):** §9 triage row — deterministic rules only, LLM cannot set levels,
  preemption path tested, rule changes via ADR plus sign-off; monotonic inheritance with
  `base.life_threat` unextendable (CLAUDE.md invariant 7); RED three axes with no default
  register/location (invariant 21, ADR-023).
  **RED acknowledgement (§9, inv. 49), INT-406:** Layer B hands every rules-engine RED to
  the clinician route as it settles, which puts an ids-only entry in the clinic Safety inbox
  in-process — no connector on the path — and a runtime without the inbox store is not
  ready; the console's Safety queue (files/08 §3, F19) is answered by
  `tenant_clinical_responsible` alone (tier 1, audited write-ahead naming the entry); a
  sweep pages past the files/02 §8.2 SLA (default 4 h, counted in wall-clock hours until a
  tenant calendar is recorded) and pages when the inbox cannot be read; a files/02 §2b
  reschedule or cancel on a visit carrying a RED entry raises its own entry.
- **Signals:** RED events (`triage.events_total`, named in §9), preemption latency,
  false-RED reviews, missed-flag reports — land with INT-080 and INT-025.
  `clinic.red_ack_latency_min` and `clinic.red_unacknowledged_total` (§9) are emitted by
  INT-406, with `clinic_red_inbox_pending_age_s` and `clinic_red_inbox_route_failures_total`
  for the 60 s half; the last three page through `infra/observability/safety-rules.yaml`
  (`docs/runbooks/red-acknowledgement.md`), and the latency histogram is the measurement.
- **Generic RED and the synthetic serve path (INT-465, D23 with D18).** The generic escalation
  is CD-24's copy, active, with per-location sources checked against committed snapshots and no
  112 in any ON_SITE carrier; RED text is rendered (markers removed, tenant segment resolved or
  dropped) before any screen or TTS. On the synthetic host only, a test-key signature stands in
  for the physician sign-off (HB-C1 unchanged for every real tenant); draft rules are never
  served. Tests: `tests/safety/test_generic_red_goldens.py`, `tests/protocols/test_generic_red.py`.
- **Tests:** golden suite with near-miss negatives and mutation tests land with INT-059;
  preemption timing with INT-093. `red_acknowledgement_sla_guard` (inv. 49) is owned by
  INT-406: `tests/safety/test_red_acknowledgement_sla.py` (fake clocks: entry ≤ 60 s with no
  connector, page at SLA + 1 s and not at the SLA, a transition on a RED visit raises an
  entry; YELLOW, GREEN, an LLM candidate and an unpinned RED never create one).

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
  compiler (INT-040). The [Dd] clause — a screening output reaching a surface that did
  not ask for it — is held on the patient summary by INT-085:
  `tests/engine/test_patient_summary.py::TestWellbeingSignalsCannotReachTheSummary`,
  which asserts the note's fields are *partitioned* rather than filtered, so a scored
  note and an unscored one build the same summary.

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
- **Signals:** `lane.dropped_frames{lane}` is **live** with INT-110 — emitted by
  `intake_voice_runtime.observers.runtime` when a lane's bounded ring evicts a frame rather
  than making the audio path wait; a lane that was never admitted has no child series at all,
  which is how the exposition tells a refused lane from an idle one. Lane consent rates,
  `acoustic.window_yield` (a low yield is a correct outcome, not an incident — §9) and
  withdrawal-to-zeroization latency are still owed: the first belongs to the consent surface,
  the second to INT-115's diarization gate, and the third to the audio-buffer work. INT-112
  added **no** metric and the omission is deliberate: a `crisis_signposts_total` counter would
  increment exactly when a patient discloses suicidal ideation, which is re-identifying in a
  small tenant — the invariant-6 harm with a metric name on it. `crisis.path_completion` stays
  `planned` for INT-116, which owns path completion end to end.
- **Tests:** `tests/lanes/test_isolation.py` (INT-110) lands CLAUDE.md invariant 11 whole —
  read-only at type level, the fake-clock stall with a positive control, backpressure with its
  metric, per-lane consent through the one evaluator, and the `acoustic` study assertion
  (inv. 23) against the INT-230 study registry with no grace day and a protocol-amendment
  close. It also lands inv. 13's static half (no observer module imports an audio transport),
  inv. 29 (every lane declares a reviewed `intended_purpose`, one statement per module), the
  `ObserverState` half of inv. 22 (there is no `affect` field for a label to cross M1 in) and
  the ≤ 60 s / zeroize-on-every-trigger half of inv. 18 for lane windows.
  `tests/lanes/test_crisis_bypass.py` (INT-112) lands the first lane *model* and the crisis
  path's read-only half: the presence fact carries a family id and a count with no field,
  property or open map a level could occupy; the router port is declared and **unimplemented**,
  so the crisis path is absent rather than idle (HB-C8, HB-L2); the lane's declared input type
  has no `match_crisis`, so a crisis hit has no route into `ObserverState`; INT-110's AST gate
  is re-run with the triage names this issue could have reached for; the detection is not
  consent-gated (files/04 §4.2 defect 3) and still runs when `lane:linguistic` is refused; and
  the CLAUDE.md invariant 22 whole-token rule is carried into lexicon matching with `üre`/`üreme`
  and `sarı tebeşir`/`sarı tebeşirlik` as near-miss negative controls. It also re-runs the
  fake-clock latency proof with a real lane and 200 in-turn crisis scans (0.0 virtual ms) against
  the same positive control. `tests/protocols/test_lexicon.py` holds the content gate: five
  families, zero terms, and a compiler that refuses every `draft_needs_source` one.
  Invariants 12, 14, 15, 16, 17, 19, 20, 21, 24, 25, 26, 27 and 28 remain with INT-111, INT-115
  and the audio-buffer and consent-withdrawal issues.

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
- **Signals:** INT-032 landed the export tier and it emits **no metric**, because nothing runs
  it: the `ehrbase` registry row is `self_hosted_now: false` behind the compose `export`
  profile, and no service imports the client yet. What exists today is the `ehrbase` synthetic
  probe — wired only when `INTAKE_EHRBASE_HEALTH_URL` names a target, so an unrun tier reports
  SKIPPED rather than a false green — and the client's typed refusals:
  `EhrbaseTemplateRejectedError` for an OPT the CDR will not parse, `OpenEhrExportBlocked` for
  an answer with no leaf binding. A counter for [I] over-broad export lands with the issue that
  wires the tier into a service, not before.
- **Tests:** `tests/integration/test_ehrbase_roundtrip.py` (INT-032) — OPT upload → fetch →
  parse → archetype-root identity against the committed template; composition envelope write →
  read → identity; the CONTRIBUTION audit. Since INT-257 the upload is the committed, sha-pinned
  bytes with no fixture, and the wire status is asserted to be 201.
  `tests/protocols/test_opt_schema.py` (INT-257) validates that file offline against the
  digest-pinned openEHR OPT 1.4 schema (ITS-XML Release-1.0.2). It also refuses a node id the
  template's terminology does not define, which is a 500 in EHRbase that the schema cannot see. `tests/schemas/test_openehr_export.py` holds [T]
  shut from the other side: an answered slot with no leaf binding is refused, never dropped and
  never bound to an invented `atNNNN` (files/HUMAN_BLOCKERS.md HB-C12).
  `tests/platform/test_ehrbase_client.py` pins [I]: no clinical text reaches a log line or an
  exception message.
- **RED notification records (INT-475).** The app's triage hop and the patient's on-site
  location answer now write clinic Safety-inbox entries (a `red` entry per hop RED; a
  `red_on_site` staff notification under ON_SITE, files/04 §8.1 rule 7) through the INT-406
  outbox and store. [I] a clinical value or answer reaching the entry, an audit row or a log:
  control — every field is an id, a closed enum or an instant (`InboxEntry`, `extra="forbid"`
  request models, a 422 that echoes no value), pinned by `tests/api/test_red_notify.py`. [I] an
  identifier inside a device id (a synced hospital visit's id carries the hospital patient
  number): a server-minted UUID is kept as it is, any other id only as its keyed pseudonym, and
  with no tokenization key not at all — the RED is then counted and audited as unrouted, never
  stored raw (invariant 14; `red_notify.stored_ref`). [T] a patient raising entries for another
  tenant: the tenant is the principal's, never a request field, and the location route is
  patient-only (`require_patient`) under the core consent scope; it answers only a KIRMIZI rule
  of the served set. [T] residual, recorded: the session and visit ids are the device's (a device-local
  visit has no server row to check against), so a patient who knew another patient's server
  visit id in the same tenant could file a RED against it; that visit's files/02 §2b move would
  then raise an inbox entry and re-show a RED pointer to its owner. A server visit id is a
  random UUID the patient is never shown another's of, so this needs a leaked id; it adds
  alerts and never removes one. [D] the RED
  never waits on the store or the audit chain: the entry is an outbox append, the hop's audit
  rows follow the answer, and a failed route or append is counted
  (`clinic_red_inbox_route_failures_total`, which pages; `clinic_red_notification_unaudited_total`).
  Every share is audited by id (`api.triage.red_notified`, `api.triage.red_on_site_notified`,
  `api.triage.red_unrouted`, `api.triage.red_location.{on_site,remote}`). Tests:
  `tests/api/test_red_notify.py`, `tests/platform/test_safety_inbox.py`,
  `tests/voice/test_safety_inbox_notifier.py`, `apps/mobile/src/lib/red/locationReport.test.ts`.

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
- **Synthetic-only test key (INT-465, D23).** [S/E] a test signature trusted where a real
  patient may be. Control: the red rule set of the synthetic AWS host is signed by an ed25519
  key held non-exportable in OpenBao Transit there, used only through a sign-only token; the
  public half is the only key in `packages/protocols/signing/trusted_keys.yaml`, whose one scope
  is `synthetic_test`. `intake_platform.red_signature.admitted_scopes` is an allow-list keyed on
  the synthetic tenant kind alone and runs before any cryptography, and the API refuses to boot
  with a synthetic tenant unless `INTAKE_ENV` is explicitly `dev` or `staging`. The signature
  binds the exact bytes parsed (each document read once), the served rule list and the one host
  it is for (`deployment`, which a synthetic tenant config must name). This is not
  the production path (cosign, INT-058, untouched). Signal: a refusal logs its id-shaped code
  (`intake_api.triage_rules`). Tests: `tests/protocols/test_red_signature.py` (every
  non-synthetic tenant config rejects the key), `tests/api/test_triage_tenant_kind.py`,
  `tests/api/test_triage_hop.py`, `tests/infra/test_red_signing_infra.py`.

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
- **Signals:** `security.injection_suspected` (§5) is **live** — INT-083 emits
  `sec_injection_suspected_total` from `intake_voice_runtime.extraction.boundary` when a
  transcript carries the data-block control marker, and `injection_event()` builds the
  `SecurityV1` row (ids and closed enumerations only; the refused string is never
  recorded). **Budget exhaustion landed with INT-101**, and what it produces is narrower
  than "a signal" — `intake_voice_runtime.metering` counts every session's spend by
  component and refuses the *elective* model lane when a declared cap cannot afford it
  (and when no cap is declared at all, which is the state today: no file publishes a
  per-session limit). The obligatory lane is never refused, because a patient's answer
  that is never extracted is a red-flag phrase nobody evaluated. One series moves
  `planned` → `live`: `voice.tts_chars`. Two do **not**, and neither gap is closed by
  minting an id — Backend extraction tokens are files/08 §4 group J's id-less row, and
  `cost.per_session` has no price to multiply by (files/HUMAN_BLOCKERS.md HB-I4, HB-I5),
  so it stays `planned` and no `Gauge` is declared for it. PolicyGuard spikes still land
  with INT-102.
- **Tests:** schema-validation tests landed with INT-083 —
  `tests/ai/test_extraction_contract.py`, which pins the four structural facts this row
  turns on: the instruction region takes no transcript parameter, the transcript travels
  delimited in its own message role, the output schema has no property a triage level
  could occupy, and `ExtractionResult` has no `level` field at all (invariant 1 as a
  `TypeError` at the call site rather than a check). A planted Turkish injection —
  INT-175's symptom sentence with an instruction welded onto it — is refused without the
  refusal echoing a fragment of it. **INT-101 adds `tests/voice/test_budgets.py`**: the
  admission table for all three kinds, the cap refusing the elective lane *before* the
  endpoint is dialled, the exhausted cap still admitting obligatory work, the ledger
  holding running totals rather than a per-charge history (invariant 3 reaches a derived
  duration too), the label set proved free of `PHI_RISK_LABEL_NAMES`, a metered turn
  taking exactly the same virtual time as an unmetered one on the fake clock (invariant
  9), and the price book refusing rather than returning a zero. The adversarial suite
  RT-09…14 in `make safety` plus the nightly red-team job still land with INT-102.
- **INT-430 (ADR-036): the council verifier.** The owner asked for an agent council of
  self-hosted or API models. Two binding challenger reviews reduced it to a verifier, and
  this row now covers it. The verifier runs only after the primary single-pass extraction
  has bound the answer, so RED never waits on it.
  - **Scope.** It reads red-flag and numeric slots only. Tense anchors, `text_only`
    safeguarding slots, identity slots and instrument items are unreachable by type.
  - **What a member returns.** A closed schema: a verbatim evidence span for every reading,
    a Turkish hedge enum, and no confidence field.
  - **What it can do.** Adjudication is asymmetric. It may only *append* the slot's own
    scripted re-ask or confirm-back, compare-and-swapped on the slot revision. It never
    clears, skips, reorders or overwrites, and its candidate flags are add-only at
    YELLOW_REVIEW and go to the clinician alone.
  - **Excessive agency (LLM06)** is closed by that action set.
  - **Prompt injection (LLM01).** Every transcript crosses the INT-083 fence, and readings
    for any slot outside scope are dropped before adjudication.
  - **Unbounded consumption (LLM10).** Each verification is an *elective* charge, refused
    while HB-O8 is open. A process-wide admission gate sheds a verification when saturated,
    and stragglers abstain at a deadline set on the injected clock.
  - **Disclosure (LLM02).**
    - Every proposal is logged as an event of ids and closed codes.
    - Spans use the closed `LlmSpan` field set (`kind=verification`).
    - Each session carries its own `cache_salt` for the shared prefix cache.
    - A hosted member is unrepresentable on a real-PHI deployment, and an unset data class
      reads as real PHI.
  - **Signals:** `council_member_latency_ms`, `council_member_agreement_total`,
    `council_verifications_total`, `council_actions_total` and
    `council_readings_dropped_total`, all catalogued `live`.
  - **Tests:** the `tests/voice/test_council_*.py` suites, each must-have with a near-miss
    control. They cover a 30 s stall measured on the fake clock, the injection corpus, the
    Turkish negation set, permutation determinism, CAS on a mid-flight correction, replay
    with refusal of a wrong-lane recording, and the span PHI scan.

- **INT-428 — hosted model lanes (ADR-035).** The owner's decision of 2 Oct 2026 puts a hosted
  provider behind the `llm`, `asr` and `tts` lanes until the GPU lanes are healthy, narrowed by the
  binding medical and AI/ML reviews:
  - **Threats.** [I/Nc] patient speech or text egressing to a vendor; [S] an address that answers
    passing for a self-hosted model (a loopback tunnel); [T] a silent model or snapshot swap; [E] a
    console switch widening egress on one key; [Dd] a key echoed.
  - **Controls.**
    - The hosted adapters are a separate package that only the synthetic deployment's image
      carries. No PHI-closure package imports or depends on it, and a real-PHI hosted lane cannot
      be constructed (`HostedPermit`, `ModelAssignment`). There is no DPA branch and no mock route.
    - The data class is declared by the image, bound by the first write and immutable.
    - Only attested registry models are served (pinned, plus `jurisdiction: TR` and `phi_path` for
      PHI), proven by an identity probe. A per-call model check quarantines on mismatch.
    - Hosted models are dated snapshots only.
    - A swap on `llm`/`asr` is gated on green red-flag extraction goldens and the negation set for
      that exact version.
    - Assignments are frozen per session.
    - Widening is four eyes, approvals are bound to a `config_hash`, and narrowing is one key.
    - Keys live in OpenBao only and are never echoed.
    - Egress uses purpose `hosted_model_inference` on a `phi_allowed: false` row that a human
      applies.
    - Refusals, truncations and empty outputs collapse to one outcome (`hosted_lane_no_answer`).
    - Instructions and data stay in separate roles under a strict schema, every numeral is refused
      before any TTS, and RED/YELLOW stay with the rules engine.
  - **Signals.** `model_lane_calls_total`, `model_lane_latency_seconds`,
    `model_lane_refused_total{reason}`, `model_lane_fallback_total`, the token, audio-second and
    character usage series, and `admin_model_lane_changes_total`.
  - **Tests.** `tests/platform/test_model_lane_{routing,resolver,hosted_adapter,deployment,shims}.py`
    and `tests/admin/test_model_lanes_routes.py`:
    - `mock_hosted_unrepresentable_for_phi_tenant`, `synthetic_flag_immutable`,
      `model_pin_frozen_in_session` and `lane_swap_requires_green_rf_extraction_goldens`, each
      with a near miss;
    - the adapters against recorded fixtures behind the real egress guard;
    - the key never echoed.
  - **Open and split out.** Guarded transport for the self-hosted extraction clients, the
    `/identity` endpoint on the GPU servers, a drift canary, recording keys carrying
    model@revision, and a schema-keyword lint.

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
  agreement by CI. **Landed with INT-018 (ADR-025):** `infra/security/egress-allowlist.yaml`
  is the single source both enforcement points read —`intake_platform.egress` in process and
  the generated `infra/security/squid/squid.conf` at the dev forward proxy
  (`infra/docker-compose.egress.yml`, profile `egress`). Default deny; a row is bound to one
  `purpose_id` and the caller must declare a matching purpose and its `DataClass`, so an
  allow-listed host addressed for the wrong reason is refused; personal data — pseudonymous
  included — needs `phi_allowed` plus `INTAKE_ALLOW_PHI_EGRESS=explicit-yes`; an authorised
  host is resolved once, refused if any answer falls in `DENIED_RANGES`, and connected to by
  the pinned address with `Host`/SNI intact, so DNS rebinding has no second lookup to win;
  every redirect hop is re-authorised and `guarded_client` disables redirects by default.
  The `phi_path` tier is empty (00_STATE D11) and the compose topology says so in Docker's
  own terms — the `phi` network is `internal: true` and the proxy is not attached to it.
- **Signals:** egress denials — a hard alert (§7) — emitted as `sec.egress_denied_total`
  (catalogued `live`, `target: 0 (any increase pages)`) and as a `sec.egress_denied` log
  record, with `TransferRecord {ts, host, port, purpose, data_class, bytes_out, decision,
  reason, tier}` as the vendor-transfer register's feed. The register's auto-fill from that
  feed is INT-189 (Compliance module).
- **Tests:** tests/security/test_deid_ner.py; tests/security/test_deid_leak_rate.py (the
  measured results live in docs/evidence/ with date and corpus, per ADR-022);
  tests/security/test_egress_allowlist.py (the bypass lane: IP literals, answers inside
  denied ranges, DNS rebinding, redirects, right-host-wrong-purpose);
  tests/security/test_egress_policy.py (the policy shape); tests/infra/test_egress_proxy.py
  (the dev proxy topology, and an eleven-host table decided through both enforcement points
  so they cannot drift).

## `cloud-clipgen` — offline cloud pre-synthesis of the fixed clip set

- **Assets:** the offline clip cache (non-patient, verbatim scripted audio — the fixed set of
  protocol questions, red-flag scripts and instruments); the vendor TTS API key; the scripted
  `text_tr` handed to the vendor at BUILD time. INT-319 / ADR-028 reintroduces a cloud vendor
  for exactly this one offline job.
- **Trust boundaries:** build host ↔ cloud TTS vendor (a new external destination reached only
  at clip-generation time, never at runtime); runtime ↔ clip cache (playback only — the
  session never reaches the vendor, and the self-hosted speech seam
  `intake_voice_runtime.adapters.speech.refuse_external_host` refuses every public host, so it
  structurally cannot).
- **Threats (STRIDE/LINDDUN):** [I] the API key leaking into a source file, a log, a trace or
  an exception; [Nc] a cross-border transfer of scripted text with no recorded basis — the
  text is non-PHI protocol content, but it still leaves the country; [S/Td] the vendor's own
  text normaliser reintroducing a numeral and speaking a wrong dose (invariant 22); [T] a
  paraphrased or edited clip breaking the verbatim rule (invariant 10); [D] the vendor being
  unavailable — not a runtime failure, because the fixed set is cached and playback needs no
  vendor.
- **Controls (files/10):** ADR-028; OFFLINE ONLY — the vendor is on no runtime or PHI path and
  the runtime cannot reach it, so this does not weaken invariant 19; the key is read from the
  environment only (`TTS_ELEVENLABS_API_KEY`, never a source file or a log, files/10 §2) and is
  never placed in an exception message; the live paid call is spend-gated on `EVAL_BUDGET_USD`
  so a test and CI never take it (recorded fixtures there); the vendor normaliser is disabled
  (`apply_text_normalization: "off"`) and `assert_speakable_tr` refuses any numeral before the
  wire (invariant 22); the text is sent verbatim and a recorded clip that carries other text is
  refused (invariant 10); no vendor hostname is a literal anywhere in the tree
  (`scripts/ci/assert_no_vendor_calls.sh`); NO runtime egress-allow-list row is added, because
  the runtime never calls the vendor. Licence/terms and the KVKK Art. 9 transfer question are
  human blockers (docs/backlog/blockers.md). The DEV on-demand variant
  (`POST /dev/voice/george-clip`, `intake_api.dev_voice`) is the one place a running API may
  dial the vendor, so it carries four server-side doors (INT-326, audit F05): a patient
  principal (401/403 before anything else); a catalogue — `text_tr` is admitted only when its
  `clip_text_hash` is a row of a compiled clip manifest, else 422 with no dial, so arbitrary or
  patient text cannot reach the vendor through it; a per-principal Redis token bucket (429, and
  503 when the budget store is unreachable); and no mount and no wiring when `INTAKE_ENV` is
  prod, whatever the dev flags say. **Delivery profiles** (INT-415):
  - The request carries `voice_settings` from a server-side, versioned table
    (`voice_clips.delivery`).
  - The device sends only a context label, never a setting or a model; `extra="forbid"`
    refuses both.
  - A profile tuned for another model is refused before the wire.
  - The dev route refuses `red`, and refuses any compiled rule script under any label, because
    the catalogue pins it server-side (invariant 21).
  - An instrument item is served only as `instrument`.
  - The profile id and version are part of every clip key.

  **Render-time tags** (INT-449, D20; on the hosted lane INT-443). [T] A tag is words the
  protocol did not author, so a tag from anywhere but the table would change what is said:
  - The tags are a closed per-context table in `voice_clips.delivery` (one lowercase word in
    brackets, never `[pause]`); RED and instrument rows can carry none, by construction.
  - `voice_clips.gateway.wire_text` is the one composer: `text_tr` passes the numeral and
    markup gate first, so a tag inside the script is refused; then the row's tags go in front;
    then the composed text is checked for a numeral again. Both ElevenLabs paths use it, so the
    hosted request is field for field the request the bundled clips were rendered with.
  - The hosted lane refuses a profile that is not exactly the served row (tags, settings,
    version, voice) and a voice id that is not the row's, before the wire.
  - The cast moved every row to v4, so a v2-era (George) clip is another address and is never
    served or counted as cached.
- **Signals:** build-time tool, so its runtime evidence is a NEGATIVE — the per-session egress
  socket count for TTS stays zero (shared with `cloud-boundary`/`observer-lanes`) and the clip
  cache serves the fixed set (`voice.clip_cache_hit_ratio` high, no runtime synth for scripted
  lines). Generation cost/characters are recorded per run in docs/evidence/, never emitted as a
  series.
- **Tests:** tests/voice/test_elevenlabs_clipgen.py (the adapter: numeral refused, key never
  echoed on any failure, normaliser off, the key+budget selection gate); tests/voice/
  test_tts_latency.py (the harness: numeral-free corpus, the A/B reported blocked without the
  key); scripts/ci/assert_no_vendor_calls.sh (no vendor FQDN in the build); tests/voice/
  test_audio_retention_guard.py (no audio content-type strings leak into the package);
  tests/api/test_dev_voice_hardening.py (the dev route's four doors, each proven with the vendor
  fake at zero calls, near-miss catalogue controls included); tests/voice/
  test_delivery_profiles.py and tests/api/test_dev_voice_george.py (INT-415: the profile table,
  `voice_settings` in the body, the RED and instrument pins, the profile in the cache key);
  tests/platform/test_elevenlabs_hosted_tts.py and tests/api/test_hosted_clip_lane.py (INT-443
  with D20: each tagged context's tags on the wire and none for instrument or RED, a tag inside
  `text_tr` refused even when catalogued, a forged row or another voice refused, the hosted
  request equal to the offline one, a v2-era clip never served). The live
  small-run validation (7 Turkish questions, 229 characters) is recorded in
  docs/evidence/INT-319.md with its date and named corpus, described as a measurement (invariant
  20).

## `records` — patient document upload and ingestion

- **Assets:** uploaded documents, extracted structured data, pgvector record index.
- **Trust boundaries:** patient-supplied file ↔ parsers (sandboxed); document text ↔ model
  context (data, never instructions); patient namespace ↔ patient namespace in pgvector.
- **Threats (STRIDE/LINDDUN):** [T] malware in uploads; [S/T] injection payloads inside
  document text reaching a model; [I/L] embedding-store bleed across patients.
- **Controls (files/10):** §9 records row — ClamAV, file-type sniffing, sandboxed parsing
  (seccomp-isolated PDF rendering, §4), the data boundary, RLS on pgvector with per-patient
  namespaces, provenance on every extracted fact; ingestion unit rule (CLAUDE.md invariant
  22: magnitude outranks the printed unit token, disagreement flags). **No e-Nabız read
  path exists or may be added** (KSVY m.6, files/06 §1; files/03 §12 — m.6(2) as amended by
  RG 33096 is a closed list of *physician* access tiers with no category for an
  application): the record is entered by patient-exported documents only. Enforced rather
  than noted — the egress allow-list names no Ministry host so default-deny already refuses
  one, no file under `packages/`·`services/`·`apps/`·`infra/`·`scripts/` names one, and no
  module on the ingestion path imports an HTTP client or takes a locator (INT-122).
  No byte of an upload meets a document-reading engine unless files/03 §4.9.1 row 20
  (text layer — the MHRS screenshot) or row 21 (layout — the six-column lab table) is
  registered under a pin that row names, with a licence read from the raw blob, declared
  self-hostable on the PHI path, and served (§4.9.2(f)); neither row is registered, so
  both read paths refuse with a status before the engine runs, and an engine that reads
  nothing is a refusal, never an empty document (INT-122, `records/document_engine.py`).
  The one model on this path is files/03 §4.9.1 row 9, reached only through a gateway that
  refuses a vendor host and a pin that is not licence-verified, pinned and served; while no
  host serves it the PHI path refuses with no fallback (INT-124). Every lab value it returns
  passes the unit-resolution guard, which flags and never converts, and with no authored
  expectation table (HB-C24) flags every value.
- **Signals:** upload scan results and parse failures (§9) land with INT-120;
  `sec_injection_suspected_total` is shared with the `llm-boundary` row — INT-121's document
  fence and INT-083's transcript fence are one control in
  `intake_platform.data_boundary`, so one counter covers both.
- **Tests:** PDF fuzzing lands with INT-120; extraction, the document data boundary, the
  confirm gate and the two invariant-22 guards with INT-121
  (`tests/records/test_extraction_eval.py`); the two patient-supplied sources — the
  six-column lab table, the MHRS SMS screenshot's candidate visit fields, the printed-date
  guard and the three no-scraping checks — with INT-122
  (`tests/records/test_enabiz_pdf.py`), and the rows 20-21 engine gate, both byte-level
  read paths and the lab table's route through the unit guard to the confirm cards with
  INT-122's second pass (`tests/records/test_enabiz_mhrs_read_paths.py`); the unit-resolution guard, the row-9 adapter and
  its PHI gate with INT-124 (`tests/records/test_unit_resolution_guard.py`,
  `tests/records/test_labjson_eval.py`); the patient-facing half of the confirm gate,
  the client-side level-shaped-key refusal and the camera path with INT-138
  (`apps/mobile/e2e/records.spec.ts`, `apps/mobile/src/lib/records/{extraction,jpeg}.test.ts`);
  the pgvector index with INT-123 — a PERMISSIVE tenant and a RESTRICTIVE patient RLS
  policy checked against the model metadata, A-cannot-read-B live under the app role with
  the same probe shown red on a copy of the table without RLS, confirmed-only indexing, the
  `documents` consent refusal, erasure of vectors on both deletion paths and retrieval
  cited into the note with document, page, box and item id
  (`tests/records/test_vector_rls.py`, `tests/records/test_record_index.py`,
  `tests/voice/test_retrieve_records_work.py`). files/03 §4.9.1 names no embedding model,
  so indexing and retrieval refuse (`EmbeddingModelUnregistered`) with no fallback.
- **INT-138 addition — the capture is a second way in, and it carries metadata.** A
  photograph of a report taken in the app reaches the same object store as an uploaded
  file, so it goes through the same allow-list pre-check, size cap and digest. On the
  path this app takes (`quality: 1` → `RawImageExporter`, a straight `copyFile`) the
  camera's ENTIRE original EXIF would travel: the GPS family, maker notes and an
  embedded thumbnail that is a second copy of the document. So every JPEG loses its
  APP1 (EXIF/XMP) segment before the digest is computed, with the Orientation tag
  carried across in a 34-byte segment the app authors itself. Location is not a
  declared category in the inventory and is not persisted.
- ⚠️ **Two limits of that strip, named rather than quietly accepted — both are for a
  human to confirm or overturn, and neither was decided here.**
  1. **It fails OPEN.** `stripJpegMetadata` returns the bytes unchanged for any JPEG it
     cannot walk end to end — a truncated segment, a marker where none belongs — and a
     test codifies that, so such a file uploads with its EXIF intact. That is file
     integrity chosen over invariant 6: a partially rewritten JPEG is a corrupt document
     the patient believes is their report. Refusing the upload is the other option and
     is not obviously worse; it trades a lost document for a leaked coordinate.
  2. **PNG is on the allow-list and is not stripped.** PNG carries its own `eXIf` chunk
     and XMP, so it is a third metadata container beside the two the JPEG strip names.
     Reachable through the file picker only — the camera path produces JPEG — so the
     probability is lower, but the exposure is the same one.
- **INT-138 addition — the extraction reaches the patient, and the verdict comes back.**
  `GET /v1/visits/{visit_id}/documents/{doc_id}/extraction` publishes a scanned-clean
  document's items; `POST …/extraction/decisions` takes `{card_id, decision}`
  (`services/api/src/intake_api/record_items.py`). New boundary: extracted text ↔ the
  patient's screen. Threats and their controls: [I] another patient's items — the
  caller's own visit and document under the RLS tenant session, the `documents` consent
  scope enforced on both routes, clinic principals refused; [T] a caller asserting who
  confirmed, or restating the value — the body is closed to those two fields and
  `confirm_record_item` takes no `by=`, so the actor is read off INT-170's vocabulary;
  [T/S] document text shaped as a control — an item carrying the data-boundary control
  token, or a box pointing into another document, refuses the extraction whole (the one
  fence's own check, not a second one), and nothing on this path reaches a model; [T] a
  flagged magnitude tidied in transit — `summary` and `unit_conflict` are carried byte
  for byte, no parse, no conversion; [R] every read and verdict appends `doc:<id>` to the
  hash chain, ids only, before the verdict takes effect. Only a clean document is ever
  passed to a source. The production source (`NoExtractionSource`) answers *unread* for
  every document while every producer is shut.
- ⚠️ **One limit of that transport, named for a human.** A confirmed item is admitted to
  INT-121's `ConfirmedRecordStore`, which lives in process memory: a restart loses the
  verdict and the card returns to *pending*, which reaches no note — the safe direction.
  A durable store would persist a structured copy of patient health values, which needs
  its invariant-18 annotation and an owner's decision (CLAUDE.md, *when to stop and
  ask*); none was made here. Tests: `tests/records/test_extraction_transport.py`.

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
- **Controls added by INT-150:** the token is 128 bits from `secrets` and is persisted only as
  a SHA-256 fingerprint, compared in constant time — a database dump yields no access; it
  travels in a POST **body** on both redemption routes, so no path or query parameter in the
  package can carry it into an access log, a Referer header or a browser history entry (inv. 6,
  asserted over the live OpenAPI document). **Expiry is computed on the server** and anchored on
  the visit, never on issue time (files/02 §2b); the schema records a date and no time of day,
  so the anchor is the START of the visit day in Türkiye — never later than the appointment, so
  never later than the spec's `visit_datetime + 72 h` — and a visit with no recorded date is
  refused (`visit_date_unknown`) rather than given an invented clock. The **view budget is
  atomic**: one guarded UPDATE carries "not revoked, not expired, budget left" and the
  increment together, so two concurrent redemptions cannot both be admitted at the limit. The
  **OTP is the INT-131 gate**, not a second one, in its own `dlink` Redis namespace and counted
  against the LINK rather than the patient (two links never share a five-attempt budget, and
  the two request paths never share a request budget — otherwise a token holder could lock the
  patient out of their own link). It inherits that gate's stated non-atomicity (INT-263) rather
  than forking a differently-broken copy. **Revocation cascades**: revoking a share — which
  every note save does — revokes its links, and the row is the authority, so restoring the
  Redis routing hint does not resurrect a revoked link. **Consent is checked record-level**
  inside the redemption endpoint against the note's own patient (inv. 4), through the same
  evaluator the clinic-admin path uses, and BEFORE the view is spent, so a withdrawal costs the
  patient no view. The **watermark** carries the recipient the PATIENT named plus the instant of
  this opening plus the opaque grant ref, and nothing derived from the request — no IP, no user
  agent, no device fingerprint — so it cannot become a way to identify the reader beyond the
  consent given. `X-Robots-Tag: noindex, nofollow, noarchive, nosnippet, noimageindex` is set on
  every API response, including the ones an exception handler builds. **Not delivered:** the
  §2 channel ("the phone/e-mail the patient chose"). No destination is recorded anywhere in
  this repo and no messaging vendor is contracted, so the seam refuses (503) behind a live abuse
  gate; the code is minted over the patient's own authenticated session instead.
- **Signals:** `doctor_link_events_total{event}` — issued, revoked, otp_requested, otp_failed,
  otp_limited, opened, refused_expired, refused_revoked, refused_view_limit,
  refused_unknown_token — catalogued `live` and emitted by `intake_api.doctor_link.metrics`.
  That is §9's *opens, failed OTPs, revocations*. The fourth, *time-to-open*, is
  `wait.doctor_link_first_open_h` and stays `planned`: every open is written to the
  hash-chained audit log, which is evidence rather than an analytics source, and no
  share-access row exists — publishing the interval needs an unlabelled path through
  `publish_wait`/`roll_up_wait` that INT-241 did not build, so
  `intake_platform.wait_times.WAIT_SOURCES` records the gap instead of the catalogue status
  drifting from the writer (inv. 13). No tenant, clinic, link or recipient label on the counter:
  a per-link series would let a Prometheus scrape reconstruct one clinician's reading of one
  patient's note.
- **Tests:** `tests/clinician/test_doctor_link.py` — token entropy (128 bits, no repeats, and a
  source check that fails a `random`-based generator that passes every statistical assertion),
  expiry anchored on the visit and exact to the second on both sides, the (limit + 1)th view,
  a token used immediately after revocation both with the routing hint gone and with it forcibly
  restored, a token one character off a valid one, an OTP one digit off and the right code on the
  attempt after the five-attempt budget, the no-index header on every response including
  refusals, the watermark through the committed PDF renderer's bytes, and the audited open
  appearing in the patient's own access log with a role and no identity.

## `share-centre` — active shares, revocation, visibility

- **Assets:** active-share registry, revocation path, the patient-visible access log.
- **Trust boundaries:** granted access ↔ time (everything expires or can be revoked);
  staff reads ↔ patient visibility (every break-glass grant appears in the log — §3).
- **Threats (STRIDE/LINDDUN):** [I] stale access outliving intent; [Nc] incomplete deletion
  after revocation; [U] the patient unable to see who has access.
  **Issuing (§9 share row, INT-311):** [I] a bearer credential rendered on the patient's
  phone (screenshot, shoulder-surf); [U] copy implying a code was "sent" on a channel that
  does not exist (HB-O7).
- **Controls (files/10):** §9 share row — instant token revocation, crypto-shredding, signed
  export URLs, deletion SLA; §3 patient-visible access log covering shares and staff reads.
  **INT-139 adds the patient's surface for the first two**: the grants over a note, a stop
  control that is offered on every grant not already stopped, and the access log rendered as a
  category and a role. Three client controls carry the row's threats. *[I] stale access
  outliving intent* — the client never caches, never persists and never writes optimistically,
  so there is no copy for a revocation to have to invalidate and the screen cannot show a grant
  as stopped that the record does not. *[Nc] incomplete deletion after revocation* — the server's
  row is the only authority the client consults: `linkState` short-circuits on `spent` so no
  device clock can retire a live grant, and a revocation shows only once the returned row says
  so. *[U] the patient unable to see who has access* — the log is on the patient's own screen,
  and its footer states out loud that it carries a role and never a name, so a missing name reads
  as a design choice rather than as something withheld.
  **Issuing (§9, INT-311):** issuing is shown in-app only. The link and code are minted over
  the patient's authenticated session and never delivered (HB-O7 open); the copy names no
  channel; capture is blocked and the credential is held in memory only. Issuance is
  consent-gated and audited (`api.doctor_link.issued`) against a redemption path that checks
  the share consent scope and writes a hash-chained audit entry (`api.doctor_link.opened`).
- **Signals:** revocation latency and the deletion SLA (§9) are **still owed**. INT-139 does not
  emit one: the interval is a server-side property and a client metric measuring it on a phone
  would be measuring the wrong clock, while `observability/metrics_catalog.yaml` carries no entry
  for it — publishing without a catalogued series is the drift invariant 13 exists to prevent.
  The measurement taken for INT-139's acceptance is in `docs/evidence/INT-139.md` with its date
  and corpus; the series belongs to whichever issue lands the server-side publisher.
- **Tests:** landed with INT-139. The patient surface —
  `apps/mobile/e2e/shares.spec.ts`, `apps/mobile/src/lib/shares/links.test.ts` and
  `apps/mobile/src/lib/shares/store.test.ts` — including the control that a withdrawal of
  `share:previsit_note` cannot lock the stop path, checked against the router's own
  `require_scopes` decorators rather than claimed about the client. The cascade —
  `tests/clinician/test_share_revocation_budget.py` — bounds the interval between the revoking
  write returning and the redemption being refused, with the near-miss control that separates a
  row check from a store that expires on a timer, and a three-grant control for the plural in
  "cascades to tokens". That third one is worth reading: `redeem` checks the SHARE's `revoked_at`
  before the link's, so a cascade that stopped after the first row still refused every redemption,
  and the test had to assert the rows as well as the behaviour to catch it. Deletion-proof tests
  remain INT-037's. Issuing landed with INT-311: `apps/mobile/e2e/issueLink.spec.ts` (the
  issuing-surface spec §9 names) and `apps/mobile/src/lib/shares/issue.test.ts` (the transport,
  without a network).

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

## `connectors` — pushing to and ingesting from hospital systems

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
- **Signals:** `connector_push_total{endpoint,outcome}` carries success, failure, consent
  refusal and replay suppression off one label; `connector_push_duration_seconds{endpoint}`
  the endpoint-error latency; `connector_receipts_unresolved_total{endpoint}` the pushes
  whose delivery is unknown, which is the series that decides whether a retry is safe
  (INT-160; all three catalogued in `observability/metrics_catalog.yaml` — files/08 §4
  names no id for this row, so they enter the catalogue without one).
  `connector_token_exchange_total{endpoint,outcome}` (INT-161) separates a failed SMART
  token exchange from a failed push, because they have different fixes — a key, a client
  registration or an authorization-server outage rather than a bundle or a network — and
  its outcome label is a closed set of our own codes rather than the receiver's status, so
  a receiver cannot choose our cardinality.
  `admin.connector_endpoint_changed_total` stays `planned`: a destination is a reviewed
  commit to `infra/connectors/destinations.yaml`, not a runtime event, and it arrives with
  the console (INT-19x).
- **Tests:** `tests/connectors/test_framework.py` — the per-tenant registry (no URL field
  exists in the schema; a tenant naming another tenant's `endpoint_id` is refused, which is
  ADR-025's fifth bypass in the form it takes here), each of ADR-025's five bypasses driven
  through the connector path (metadata-range answer, split DNS answer fails closed, the
  request aimed at the pinned address, redirects not followed, wrong tenant), the
  write-ahead receipt with both hash-chained audit entries and the crash-in-between case,
  the derived idempotency key with its near-miss negatives (edited note, other endpoint,
  other tenant), the ambiguous-outcome parking for a receiver whose DPA does not declare
  the key honoured, and the no-PHI-no-credential sweep over logs, receipts and errors.
  `tests/connectors/test_credentials_and_tls.py` — OpenBao resolution that names no path in
  its failure, mTLS material that leaves no file behind on success or failure, the registry
  file refusing rather than loading empty, and the adapter-built path re-checked at send
  time. `tests/security/test_egress_allowlist.py` additionally asserts that a
  clinical-push purpose never appears in the vendor allow-list.
  `tests/connectors/test_fhir_push.py` (INT-161) — the FHIR adapter re-encodes nothing (a
  `Decimal` driven end to end proves the bytes are identical, so invariant 22's boundary is
  held by not having one), the `OperationOutcome` narrative is never read, and a failure is
  diagnosed from headers alone: the status, a closed-vocabulary OAuth error from
  `WWW-Authenticate`, and a `Content-Type` that says whether a FHIR server answered at all.
  `tests/connectors/test_smart_backend_services.py` — the second host and its own non-PHI
  purpose (ADR-027; one host serving both roles still needs both permissions, and each
  refuses the other's traffic), the token endpoint never discovered, the assertion's `exp`
  clamped by the share consent's expiry, one token per push with no cache, an unsupported
  key refused before anything leaves, and the framework headers an adapter cannot
  overwrite.

### INT-162 — the inbound direction (HBYS/SBYS → us): HL7v2 ORU, file drop, USVS mapping

- **Assets:** the inbound-source registry, inbound messages (HL7v2 ORU / dropped files
  carrying lab results — PHI), the USVS mapping tables, the KTS application pack.
- **Trust boundaries:** hospital LAN ↔ our PHI network (a feed is untrusted input on the
  PHI path); the sending HBYS ↔ our record store.
- **Threats (STRIDE/LINDDUN):** [E] a crafted HL7 segment used as a command or injection
  surface — the central inbound risk (invariant 14: a segment can never issue a command);
  [S] a spoofed or plaintext-LAN feed of special-category data; [T] an inbound message
  claiming a RED/YELLOW triage level (invariant 1: an inbound message may carry
  `candidate_flags` only, at most `YELLOW_REVIEW`, and only the rules engine yields
  RED/YELLOW); [I] a guessed or mis-bound USVS code silently entering a record; [Dd] a value
  from a malformed message reaching a log.
- **Controls (files/10):** parsing is a table lookup on the segment name — `OBX` is read and
  every other segment is inert text, so no name dispatches code; the delimiters are read from
  MSH-2 (the message's own declaration) and an escape *inside* a value is decoded to a
  literal character, never re-interpreted as structure; the byte cap is checked before the
  body is split; the parsed `InboundObservation` has no field a triage level could occupy;
  the USVS code bindings are `draft_needs_source` and the loader refuses to serve them, so an
  inbound lab resolves to an item with **no code** rather than a guessed one
  (`ExtractedRecordItem` already forbids a guessed code); a source is registered, bound to a
  DPA and an approval, and — for `lan_plaintext` — a **separate** recorded approval
  (invariant 14); ingest clears a consent scope and is audited as ids only (invariants 4, 6).
  `infra/connectors/inbound_sources.yaml` ships with zero rows, so every message refuses.
- **Signals:** `connector_inbound_messages_total{source,outcome}` — the inbound mirror of
  `connector_push_total`, by `ingested` / `refused`, both labels closed sets bounded by the
  registry and the module (catalogued in `observability/metrics_catalog.yaml`).
- **Tests:** `tests/connectors/test_inbound_channels.py` — the ORU parse, MSH-2-driven
  delimiters, an unknown segment proven inert, an escaped delimiter decoded as a character, a
  non-ORU message refused, the oversized-message refusal, the no-value-in-errors sweep, and
  the source registry (zero rows, cross-tenant refusal, the plaintext-approval requirement
  both ways). `tests/connectors/test_usvs_mapping.py` — a draft binding never becomes a code,
  the served map excludes drafts, the HBYS field bindings checked against their committed
  source with a near-miss negative, and the no-triage-field / `Decimal`-not-float guarantees.
  `tests/connectors/test_inbound_ingest.py` — consent cleared and audited (ids only) before a
  message is mapped, and refused otherwise. `tests/connectors/test_kts_and_dpa.py` — the KTS
  pack fails closed while the SBSGM list is uncommitted, and the processor-role DPA clause set
  anchors to real repo documents.

### INT-318 — the read direction: an on-premises appointments source and `/v1/visits/sync`

- **Assets:** the clinical read-source registry (`infra/connectors/sources.yaml`), the
  upstream directory of upcoming patients (names, mobile numbers, TC Kimlik — PHI), one
  patient's appointments, the verified phone the app submits.
- **Trust boundaries:** our server ↔ a hospital LAN host reached by a private IPv4 literal,
  possibly over plaintext; the signed-in patient ↔ another patient's record.
- **Threats (STRIDE/LINDDUN):** [E/I] a source row built in code so the read goes live on
  environment variables alone (audit 2026-09-26 F06); [I] patient A reading B's visits by
  submitting B's number; [I] a shared handset showing one patient's visits to the other; [I]
  a service consent standing in for a hospital-record read; [Dd] SSRF through the read
  guard; [D] an upstream blip breaking sign-in.
- **Controls (files/10):** the row is read from the registry and never built — the file
  ships with zero rows, so nothing is wired and the route answers `unavailable`; a row must
  name a signed DPA, a tier-3 approval, a purpose from the closed INT-038 registry and, for
  `http`, a separate recorded plaintext decision; `LanSourcePolicy` accepts only the
  registered RFC 1918 literal (the exact complement of the vendor allow-list), performs no
  DNS, disables redirects and needs `INTAKE_ALLOW_LAN_SOURCE=explicit-yes` at runtime; the
  credential is read from OpenBao by the row's reference; the row serves only its own
  tenant; the submitted phone must tokenize to the caller's own pseudonym before the feed is
  touched; identity is `resolve_identity` with a terminal ambiguous refusal; the read clears
  `core` at the door and the row's own purpose inside, and is audited (hash chain, ids
  only); an upstream failure is `upstream_unavailable`, 200, no visits.
- **Signals:** the egress decision lands in the KVKK transfer register, and a denial counts
  on `sec_egress_denied_total` — the same series and the same `EgressDenied` as the vendor guard.
  No new metric.
- **Tests:** `tests/connectors/test_acibadem.py` — the guard in both directions, the schema's
  refusals, identity resolution. `tests/api/test_visits_acibadem_sync.py` — the route's
  behaviour (own visits only, A-cannot-read-B with an untouched feed, the shared handset,
  consent at the door, the audit, upstream failures). `tests/api/test_visits_acibadem_registry.py`
  — zero rows wire nothing even with the int-demo environment set, no `intake_api` module
  builds a row or names a binding ref (derived from the schema), core alone does not unlock a
  row registered for another purpose, another tenant's row serves no one, the runtime gate,
  and an invalid, ambiguous or plaintext-without-decision registry wiring nothing.

## `embed` — the partner white-label launch handshake

- **Assets:** the tenant embed registry (branding + recorded human facts), per-tenant
  ticket signing keys (OpenBao), launch tickets in flight, the single-use nonce store.
- **Trust boundaries:** partner backend ↔ our mint endpoint; partner app/patient device ↔
  our launch endpoint; tenant ↔ tenant (a ticket must never cross); partner page ↔ the
  branded intake (must not be an injection surface).
- **Threats (STRIDE/LINDDUN):** [S] a forged or replayed launch ticket; [E] a ticket minted
  for tenant A launching tenant B (inv. 37: the tenant is data bound in the signature, never
  a request parameter); [T] tampered branding turning the embed into an XSS/injection surface;
  [I/Dd] a partner-supplied patient identifier becoming a cross-tenant PHI path or an
  unlawful new recipient; [Nc] a live partner served without a DPA, brand permission or
  authored consent texts; a device function reaching a tenant with no CE certificate.
- **Controls (files/10):** signed HS256 ticket over the `room_tokens` primitive with a
  **closed** claim set `{tenant_id, nonce, iat, exp≤120s, purpose}` and no clinical or
  personal value; tenant bound inside the signature and verified against the tenant whose
  OpenBao key verified it (ADR-029); single-use nonce consumed only after every other check
  (a tampered replay never burns a genuine nonce); branding is constrained data validated at
  load — hex colours, bounded display name, id-shaped refs, partner markup/URLs/schemes
  refused — so there is no injection surface; `device_functions` may not be enabled for an
  embed tenant (ADR-020); a `prod` tenant is refused without `dpa_ref` + `brand_permission_ref`
  (fail closed, zero prod rows, the ADR-026 shape); consent is collected by Vizite's own
  docs/legal-bound flow (inv. 4, inv. 18), never by the partner; the note flows back only
  through the existing connector path (ADR-026), so the embed adds no new outbound PHI path;
  refusals are id-shaped codes only (inv. 6). A partner-supplied patient identifier is **out
  of scope** — linking it is a new personal-data category and recipient awaiting human
  sign-off (docs/backlog/blockers.md INT-320), built as nothing rather than invented.
- **Signals:** `embed_launch_ticket_total{tenant,outcome}` and `embed_launch_total{tenant,outcome}`
  (planned — catalogued in `observability/metrics_catalog.yaml`, emitted when the embed
  console lands); the hash-chained audit carries `embed.ticket_minted` and `embed.launched`
  entries (ids only, `basis:embed-handshake`).
- **Tests:** `tests/embed/` — the ticket round-trip, the cross-tenant refusal, tamper/expiry/
  replay/purpose/ttl fail-closed paths, the constrained-branding and zero-prod-rows registry
  rules, the fail-closed 503s (no signing key, unconfigured surface), the admin-only mint,
  and the audit entries; the consent route-scan (`tests/legal/test_consent_guard.py`) proving
  both routes carry the `partner_embed` marker and nothing is left undeclared.

## `kiosk` — shared devices in clinics

- **Assets:** kiosk sessions, clinic PIN, the physical device.
- **Trust boundaries:** consecutive patients on one device (ephemeral sessions); device ↔
  physical access (MDM lockdown).
- **Threats (STRIDE/LINDDUN):** [T] physical tampering; [I] shoulder surfing and session
  residue; [S] a forged check-in.
- **Controls (files/10):** §4 kiosk mode — guided access, MDM enrolment, PIN per clinic,
  60 s idle auto-wipe, no local persistence, tamper alert on backgrounding, large-type
  privacy layout; signed, short-lived QR check-in payloads (INT-163,
  `intake_connectors.checkin`) verified fail-closed at the desk — [S] a forged check-in is
  refused by an HMAC that carries no PHI (invariant 6, 14).
- **Signals:** kiosk heartbeat and session wipe count (§9) are console (server-side)
  signals and do NOT land with INT-143 — an ephemeral, no-persistence kiosk makes no
  server round-trip to carry them, the same reason the offline-drafts row has "no server
  signal"; they land with the console/metrics work. `checkin_to_seen` landed with INT-163:
  the desk verification records a `wait.v1` observation (duration + tenant only), rolled up
  under the k >= 10 floor before it reaches a console.
- **Tests:** kiosk-mode behaviour landed with INT-143 —
  `apps/mobile/e2e/kiosk.spec.ts` and `apps/mobile/src/lib/kiosk/kioskState.test.ts`.
  The MDM lockdown detection and the clinic-PIN provisioning read are the dev-build
  native layer (HB-A3; files/10 §4.7), so both fail closed in the managed runtime: no
  provisioning ⇒ a normal phone, no confirmed lockdown ⇒ a tamper.

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
  **Offline drafts (§9 offline-drafts row, INT-142):** [I] a plaintext draft written to disk;
  [Dd] a draft outliving its session; [L/Dd] another account's draft surfacing on a shared
  device; [T] a tampered blob read as a sound draft; [D] silent data loss when a local edit
  meets a newer server copy.
- **Controls (files/10):** §4 mobile — SecureStore with biometrics, FLAG_SECURE, EAS Update
  code signing, MobSF on every build, jailbreak/root as a soft signal degrading to typed
  mode, native ATS/`network_security_config` pinning with a documented rotation recovery
  path, first-party attestation module (App Attest + Play Integrity + DPoP key) filed as its
  own issue; `include_local_variables=False` server-side (§3).
  **Offline drafts (§9, INT-142):** an AES-256-GCM envelope over the typed draft only, never
  audio (CLAUDE.md invariant 3), with the DEK in the Keychain/Keystore
  `WHEN_UNLOCKED_THIS_DEVICE_ONLY`; the GCM tag fails the open on tamper; a deterministic
  last-writer-wins rule that preserves the losing copy, so no loss is silent; account-scoped
  hydration; visit-id path sanitisation; crypto-shred of the blobs and the DEK on sign-out.
- **Signals:** attestation failures (§9 onboarding row) and crash-free-session tracking (§6)
  land with INT-145/INT-146. Offline drafts are device-local and have no server signal by
  design (§9); the crash-free rate covers them (INT-145).
- **Tests:** MobSF gate lands with INT-146; telemetry scrubbing tests with INT-145. Offline
  drafts landed with INT-142: `apps/mobile/e2e/offline.spec.ts` and
  `apps/mobile/src/lib/intake/offline/{envelope,reconcile,draftStore}.test.ts`.

## `experience` — satisfaction and wait-time measurement

- **Assets:** CSAT/NPS responses, clinician pulse data, wait-time rollups.
- **Trust boundaries:** survey responses ↔ clinical record (linkable only where consented);
  free-text feedback ↔ analytics pipelines (PHI can arrive uninvited).
- **Threats (STRIDE/LINDDUN):** [L] linking satisfaction data to clinical content beyond
  need; [I] patient-typed free text carrying identifiers into analytics; [U] respondents
  unaware of how feedback is used; **[U/E] an unsolicited survey invitation reaching a
  patient as a consent-free "service message"** — 6563 gives marketing-class messages a
  consent requirement, and a survey routed through the transactional dispatcher would
  bypass it (INT-242).
- **Controls (files/10):** invariant 6 (ids only in analytics); k-anonymity floor on
  aggregates (k ≥ 10, §9 admin row); redaction baseline (§3) applied to free-text ingestion;
  **invitations classified commercial and gated on İYS** (invariant 18) with the
  `satisfaction_prompts` safety flag shut, opt-out and quiet hours decided by INT-141's own
  evaluation, and no survey member in `ReminderKind` or template in the catalogue.
- **Signals:** `csat.score`, `csat.reason`, `nps.monthly`, `clinician.pulse` — catalogued
  `live` and emitted by `intake_metrics.metrics`, published only for a named cohort over a
  stated window and only at or above the k ≥ 10 floor. No tenant, clinic or clinician label
  on any of them, so no dashboard can re-slice a satisfaction series down to one person.
  Wait times (INT-241, files/08 §4 group G) join them on the same terms: `wait.records_processing_s`
  is `live` because both of its instants exist in this repo, its only label is the closed ingest
  content-type enumeration, and it is published from a rollup rather than observed raw — a
  histogram scraped after one observation would expose that patient's exact wait through `_sum`
  over `_count`. `wait.checkin_to_seen_min` is also `live` since INT-163: the connector signs the
  check-in instant into a short-lived payload and records the wait at desk verification, so both
  its instants exist in the repo. `wait.time_to_first_question_s`, `wait.note_ready_after_wrapup_s`
  and `wait.doctor_link_first_open_h` stay `planned`: each is missing one of its two instants, and
  `intake_platform.wait_times.WAIT_SOURCES` records which, so the catalogue status and the writer
  cannot drift from the truth (invariant 13).
- **Controls added by INT-241:** the aggregate excludes patients who refused
  `learning:service_improvement` (files/06 §2 — the de-identified-aggregate purpose), decided by
  the same platform evaluator the route guard uses; a per-`document_type` breakdown is suppressed
  **whole** when any cell falls below the floor, because a total plus all-but-one cell hands the
  reader the missing cell; the rollup type carries no minimum and no maximum at any cohort size;
  the SDS-01 style export (`GET /v1/admin/experience/wait-times.csv`) has no clinic, branch,
  clinician or patient column, carries the window bounds and measurement instant on every row,
  and runs every cell through the one committed injection guard,
  `intake_platform.export_safety.sanitise_cell` (invariant 47; files/08 §0c F13). Tenant scope on
  both admin reads comes from the principal — there is no `?tenant=` parameter to pass
  (files/08 §8, §0c F9).
  `survey_invitation_total{kind,channel,message_class,status}` (INT-242) is the scheduling
  side: closed enumerations only, and its `status` label is the standing record of why no
  invitation is sent — `blocked_iys_consent_absent` for the 6563 gate,
  `refused_schedule_unset` for the first-prompt value nobody has supplied.
- **Tests:** `tests/experience/test_csat_flow.py` (the split: scores to `events`, the sentence
  to the envelope-encrypted `csat_texts`; the §3 redaction baseline on ingestion; the response,
  the audit entry and the event payload all free of the patient's words; both FK cascades, so
  a DSAR erasure and the files/06 §3 `satisfaction` clock each reach the text) ·
  `tests/experience/test_rollups.py` (`test_a_rollup_of_adversarial_responses_exposes_none_of_it`
  — a symptom sentence, a phone number and a clinician's name forced into the very rows the
  rollup reads, exposed nowhere in the rollup or the exposition; k ≥ 10 suppression) ·
  `tests/experience/test_metrics_service.py` (invariant 15 for `services/metrics`; invariant 20:
  no CSAT/NPS figure in docs/regulatory/ or docs/legal/) ·
  `tests/experience/test_wait_metrics.py` (catalogue status held against the source registry in
  both directions; recording an unmeasurable kind fails closed; complementary breakdown
  suppression; no minimum or maximum on the rollup type; the opt-out honoured end to end; the
  export's column set, its suppressed-row marking and a formula lead neutralised in a registry
  note; the admin routes' declared scope, admin-only access and absent tenant parameter).
  `tests/experience/test_survey_cadence.py` (INT-242: the İYS gate blocks a patient NPS
  invitation and opening the safety flag does not unblock it; a stub registry that *does*
  answer clears it, so the gate is a real check and not a constant; no survey `ReminderKind`
  and no survey template; opt-out and quiet hours agree with `ReminderDispatcher` on a
  48-case grid; the only numeric literals in `intake_platform.surveys` are 1, 3 and 12,
  with a near-miss control module carrying a sampling rate, a 90-day cool-off and an
  invented send hour to prove the scan bites).

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
  **Break-glass (§9 break-glass row):** [I] four unmanaged read paths to patient content —
  Langfuse spans, Grafana Explore over Loki/Tempo, `replay(event_log)` and break-glass
  itself; [Nc] a "de-identified" claim that Turkish NLP cannot support; [U] the patient never
  informed that staff read their content.
- **Controls (files/10):** §9 admin row — server-rendered panels only, gated-capability
  service with tier-3 four-eyes and write-ahead audit, signed Study Registry with expiry and
  no grace, tenant scope from the OIDC claim with a per-request DB role, four-eyes as a
  server-side pending-action protocol (distinct AAGUID/credential id), asymmetric authority,
  k ≥ 10 on aggregates, nonce CSP with no `unsafe-*` (inv. 48), `DangerousAction` registry
  (inv. 33).
  **Break-glass (§9, inv. 38/39):** one path, `POST /admin/break-glass`, which §9 requires
  to be proven by an import-boundary test; a closed-category reason plus at least 20 characters; a distinct
  human and a distinct authenticator; a controller-instruction reference for processor
  tenants; one session id, TTL ≤ 60 min, single use; watermarked, no download, no bulk
  pagination, no adjacent-session navigation; audit **before** the read; a patient
  access-log entry within 24 h, whose window is counsel's question (HB-L6). INT-180 ships the
  ceremony with the tenant-to-deployment map empty, so break-glass refuses every tenant until
  files/08 §2.6's controller/processor question is answered per tenant; the operating steps
  are docs/runbooks/break-glass.md.
  - **Controls added by INT-190 (Cost module):** money has one source, the owner-filled
    `infra/costs/unit-prices.yaml`, and the schema refuses any price or budget limit without a
    `source` and an `as_of` date, so an invented rate cannot land without a visible diff (HB-O8).
    Every quantity is a catalogued series bound at load time (inv 13), read through a fixed
    PromQL table no request field reaches; a response carrying any label the query did not
    group by, a profile outside the closed pair or a non-quantity is refused as a source error
    (inv 6, 19). Per-session cost is a mean over `voice_sessions_metered_total`, so no session
    identifier exists on the surface. The console projection refuses a figure without a
    configured price or observed usage (`CostFigureWithoutPrice`, `CostFigureWithoutUsage` — the
    invented zero), a partial total (`PartialTotalRendered`), a budget declared kept on a lower
    bound (`UnsoundBudgetVerdict`), an unsourced value (`UnsourcedPrice`), a non-id identifier
    (`CostContentLeaked`) and a foreign currency. Budget alerts are generated rules
    (`infra/observability/cost-rules.yaml`, drift-gated); an unset budget fires
    `CostBudgetNotConfigured` rather than staying silent, and an overrun threshold is a sound
    lower bound (`or vector(0)` per term) with `CostBudgetIncomplete` naming what it cannot see.
  - **Controls added by INT-186 (Experience & Satisfaction module):** the console
    projection refuses a satisfaction figure shown for a cohort below the k ≥ 10 floor
    (`SuppressedCohortLeaked`), a distribution key that is not id-shaped (`SatisfactionFigureLeaked`,
    inv 6), a target rendered beside a measurement (`SatisfactionTargetRendered`, inv 20), a
    branch/profile/clinic filter asserted available (`ExperienceFilterEnabled` — the F9
    re-identification slice the aggregates cannot support; adding the dimension is an inv-18
    stop-and-ask), tenant scope taken from a query parameter (`TenantFromQuery`, the F9 IDOR),
    and an SDS-01 export column that would re-identify a cohort or a cell that would evaluate in
    a spreadsheet (`SdsColumnForbidden`, `UnsafeExportCell`, inv 47). The SDS-01 export is the
    committed `intake_metrics.sds01.SDS01_COLUMNS`, aggregate only.
  - **Controls added by INT-351 (the rendered ops console, audit F26):** `apps/admin-web`
    gains the Next.js App Router shell and its first page, `/ops`, server-rendered only. The
    page forwards the caller's bearer to `GET /admin/ops` and renders nothing else until that
    INT-180 gate answers 200 — no bearer means no call at all, and a refused caller does not
    reach the API's health endpoints either — so the OIDC verifier, the HB-A16 allow-list (empty
    admits nobody), the platform-scope role set and the audit wrapper are the one admission
    control, not a second verifier that could disagree with it. `/admin/ops` runs only the API's
    own fixed PromQL table (every series catalogued, test-held) plus the registry projection; no
    request field reaches a query (F1). A tile whose label set differs from its query's, or
    whose label value is not id-shaped, turns unknown instead of painting it (inv 6); unknown
    tiles carry no figure and the console refuses one that does (inv 17); CSAT and wait means
    are withheld below k = 10; no target is rendered (inv 20). GPU and CI facts come from an ops
    collector in `services/probes` that runs server-side — `nvidia-smi` beside the host, a
    read-only GitHub token read from OpenBao at collection time through the egress guard
    (`issue_tracking` purpose on the existing `api.github.com` row) — and exports only ids
    (actor and commit message are dropped). CSP: per-request nonce, `strict-dynamic`, no
    `unsafe-*` outside `next dev`, `frame-src`/`frame-ancestors 'none'`, `base-uri 'none'`, plus
    `no-referrer`, `nosniff` and `DENY` framing. **Known limit, owner decision:** the API sees the
    admin-web server, not the browser, as its transport peer, so HB-A16's ranges must name the
    admin-web host and the browser ranges move to the OIDC-terminating ingress in front of it.
  - **Controls added by INT-181 (the rendered overview: SLOs, probes, dependency health):**
    `/overview` is server-rendered through the same admission step as `/ops` (one shared
    `admit()`), forwarding the bearer to the new `GET /admin/reliability`
    (`admin.reliability.read`, platform-scope roles, audited like every route, RBAC matrix and
    drive derived from the served route table); a refused caller does not reach `/readyz`
    either. Every PromQL the composite runs is derived from the committed `docs/slo` files or
    is a fixed query, names catalogued series only (test-held) and takes no request field
    (F1); an SLI written outside the one grammar the console reads is refused rather than
    guessed. A label set other than the query's, or a value that is not id-shaped, turns the
    tile unknown (inv 6); the probe runner's free-text `detail` never leaves the API. Every
    tile fails closed on its own source (inv 17), and a probe result past three sweeps is
    flagged stale in the matrix and is *unknown* as a dependency's health — the last value is
    never shown as the current one. The view-model refuses a burn condition that is not exactly
    "both windows above the factor", a budget that does not follow from its SLI and objective,
    and a stale result rendered fresh, so neither a bent payload nor a stale tab can hide a
    burning budget.
  - **Controls added by INT-365 (staff second factor and session bounds, files/08 §2.3):**
    against [S] a phished approver. Every staff token reaches the console through
    `principal_from_claims`, which refuses it unless `amr` shows `pwd` plus a second factor
    (`otp` or `hwk`). A role whose §2.1 patient-content cell is not "no" needs `hwk`: TOTP is
    phishable. `platform_owner`, `tenant_clinical_responsible`, `clinical_lead`,
    `investigator`, `compliance_officer` and `support` therefore need it. The set is derived
    from `PatientContentPath` and never listed in code. `amr` must be a JSON array of exact,
    case-sensitive strings. An absent claim, a bare string, a mapping or a non-string member is
    no evidence, and `acr` alone never admits. The refusal is RFC 9470's 401
    `insufficient_user_authentication`, with one body for "no second factor" and "not
    WebAuthn", so the response does not reveal whether an account reaches patient content. It
    is audited under the verified subject id and nothing else. The committed realm configures
    the OTP policy (TOTP, 6 digits, 30 s, code not reusable) and the WebAuthn policy (user
    verification required). Its browser flow is a password and then WebAuthn or TOTP, each
    execution tagged with the `amr` reference the verifier accepts. The realm bounds every
    session to 8 h and 30 minutes idle, offline sessions included. The `amr` references expire
    at the same 8 h, so after that bound the API refuses a refreshed token too.
  - **Controls added by INT-182 (the Voice module: kill switch, profile switch, canary):**
    the per-tenant voice control lives in its own Redis record written **only** by
    `services/api/admin` — not in Unleash, whose tokens flip flags with no audit row (F1,
    inv 34) — and the runtime reads it at every session start and on a 1 s poll, so the kill
    switch takes effect without a deploy. **Asymmetric authority, from the `DangerousAction`
    registry:** pulling the kill switch (toward `typed`) is tier 1 — one `sre_oncall`,
    `clinical_lead` or `platform_owner`, audited, no approver (F17); releasing it, switching a
    tenant's default profile and setting a canary weight (toward voice) are tier-2 four-eyes
    ceremonies through the INT-180 pending-action protocol, `sre_oncall` on neither side. An
    approval binds to the record revision its brief showed and is refused if the control moved
    since — a kill switch pulled mid-ceremony cannot be undone by approving the stale request.
    Fail-closed in three places: a tenant with no record is `typed` (voice is opt-in by a
    tier-2 switch, and a store that loses its keys falls every tenant to the keyboard); a
    control the runtime cannot read starts the session `typed` and is counted; a speech worker
    without the store is not ready. Only `residency_tr` and `typed` parse (inv 19); weights are
    integers 0..100; bodies are closed and refused by field name; the change reason's free text
    never enters the record, the ceremony evidence, a label or a response (inv 6). The admin-web
    forms are script-free, same-origin only (`Sec-Fetch-Site`), and cannot approve — approval
    needs a fresh WebAuthn assertion the console does not mint yet. **Known limit, owner
    decision:** the tier-2 second key is still two accounts, not two proven humans (the
    INT-180 limit), and the step-up ceremony in the browser is unbuilt.
  - **Controls added by INT-373 (the realm emits the console's claims):** the committed realm's
    `admin-web` client carries an audience mapper naming `api` and attribute mappers for `org`
    and `tenant`. The realm's user profile declares both attributes admin-only (view and edit),
    single-valued, and pattern-bound to the console's id shape. A staff member therefore cannot
    move their own tenant scope ([E]), and a malformed value is refused when it is saved.
    `aaguid` and `credential_id` are mapped from user-session notes that no stock Keycloak
    26.1.4 authenticator writes, so every token lacks them and the console refuses it (fail
    closed) until the WebAuthn provider in `docs/runbooks/keycloak-realm.md` §3 exists. Test:
    `tests/admin/test_realm_claim_mappers.py`.
  - **Controls added by INT-378 (the WebAuthn provider writes the two notes):** the staff flow
    runs `intake-webauthn-session-notes`, which is Keycloak's own WebAuthn authenticator
    unchanged. Only after that authenticator returns SUCCESS does it write the asserted
    credential's stored AAGUID and its base64url id as the two notes, so neither value can
    come from anything but a verified assertion ([S] against a forged actor block). Any other
    outcome writes nothing, and the token is refused. The values are identifiers, never
    personal data, and nothing is logged (inv 6). Supply chain (inv 14): Keycloak is compiled
    against and not bundled. The Maven distribution is pinned by sha256, and so is every
    artefact Maven resolves (the build fails on a missing or different hash). The jar is
    reproducible and pinned (`infra/keycloak/providers/webauthn-session-notes.sha256`), and
    the required CI job `check-py` rebuilds it against the pin. The committed realm also now
    imports: Keycloak keeps a flow description in NVARCHAR(255), and a longer one had failed
    the import. Tests: the provider's Java suite (`make keycloak-provider`) and
    `tests/admin/test_webauthn_session_notes_provider.py`, which replays a recorded real
    Keycloak login (26.7.4, the composed version). Open: the owner's TOTP decision (INT-389, #644).
  - **Controls added by INT-366 (quarterly access review, one-action offboarding, 60-day
    auto-disable; files/08 §2.4, §2.7):** against [E] access that outlives its need and a
    departure that leaves one identity store open. `GET /admin/access/review` is generated
    from the Keycloak admin API (effective realm roles, enabled flag, last login from LOGIN
    events) and the audit chain (last console action; each section's last countersignature) —
    ids only: Keycloak's names and mail are never copied, a non-id username is dropped, and
    the section digest is 128 bits so nothing on the page is chain-hash-shaped (HB-I12).
    Signing a section is a tier-2 ceremony (it lifts the read-only downgrade, so it is the
    dangerous direction): the §2.7 reviewer signs the population's digest, a second person
    countersigns with a fresh single-use assertion, `platform_owner` needs the countersigner
    from another organisation, and a grant between the two keys voids the signature. The
    countersignature is an `admin.access_review.signed` row on the chain, so the review state
    has no second store to forge and every replica reads it back. **Enforced by the router,
    not the page:** past 100 days, or with no review, every write reached only through
    `platform_owner` or `tenant_admin` is refused (`access_review_overdue`) and audited; an
    unread chain counts as no review (fail closed). Offboarding is tier 1 (the safe direction;
    §8.2 "token revoke"): Keycloak account disabled before its sessions are ended, the OpenBao
    entity disabled and each of its tokens revoked (with their leases), the person's pending
    four-eyes requests expired, and every other console system from
    `infra/admin/console-accounts.yaml` listed — a system without a programmatic adapter is a
    manual step that keeps the offboarding incomplete until an audited confirmation; the loader
    refuses a file that would skip one. Each step is write-ahead on the chain; a failed step is
    reported and the rest still run. The subject is path-shape-checked before it reaches a
    Keycloak or OpenBao URL. The 60-day job offboards through the same pipeline under
    `svc:access-hygiene` and refuses to disable anyone when the realm keeps under 60 days of
    login history (an expired login must not read as "never logged in"). **Known limits, owner
    decisions:** the admin client, the OpenBao offboarding policy (which needs `sudo` to list
    token accessors), the scheduler and the first countersigned review are unwired, so the
    console is read-only for `platform_owner`/`tenant_admin` until the owner acts; Grafana,
    Langfuse and Unleash stay manual steps; access tokens already issued live until their
    expiry (INT-365's session bounds).
  - **Controls added by INT-391 (the credential id is WebAuthn's, not a generic id):**
    `principal_from_claims` decodes `credential_id` instead of matching the 128-character id
    shape. It admits exactly the ids WebAuthn Level 3 lets an authenticator mint: unpadded
    base64url (§3), 16 to 1023 bytes once decoded (§4). The old shape refused a valid staff key
    at random (an id starting with `-` or `_`, about 2 in 64, or longer than 96 bytes). It also
    admitted strings that are no credential id (`/`, `.`, `:` or `@` inside, fewer than 16
    bytes). A padded id, the standard alphabet, a dangling character and a second spelling of
    the same bytes (pad bits set) are refused. Each credential therefore has one spelling, and
    four-eyes' distinct-credential check, which compares strings, compares credentials. The
    refusal is the generic 403 every malformed claim gets, audited as `admin:unresolved`; it
    names the claim and never its value (inv 6). `aaguid` keeps its shape: the provider writes
    UUID text, which that shape always admits.
  - **Controls added by INT-390 (the identity provider's own patch level):** against [E] an
    identity provider with published advisories. Compose runs Keycloak 26.7.4 pinned by
    index digest (26.1.4 carried 64 OSV advisories on the artefacts INT-378 compiles against).
    The committed realm is held to the columns 26.7.4's import writes, derived from that
    tag's changelogs and measured in UTF-16 units, and every string field must be classified,
    so a realm that cannot load fails CI rather than `make obs`. The realm is mounted under
    the file name 26.7.4's directory import requires. **Known limit:** three OSV records
    still match 26.7.4 through open-ended ranges whose GitHub source bounds them below it
    (docs/evidence/INT-390.md); a scanner that reads the Keycloak artefacts reports them.
  - **Controls added by INT-485 (the console's login gate writes no staff identity):**
    against [L] staff identities in the host's container logs. oauth2-proxy's request and
    auth logs are on by default, and each line names the signed-in email and the client IP,
    so every console request wrote both into the json-file logs (inv. 6). The admin
    `oauth2-proxy` service turns both off, the same as INT-481's Grafana gate; start-up and
    error lines are still written.
- **Signals:** group O (§7): device-flag and study-assertion changes, break-glass rate and
  patient-log lag, pack promote/quarantine, connector and allow-list changes, privileged
  role grants, `admin.four_eyes_self_approval_attempt_total` (an intrusion signal),
  audit `seq` gaps, external-anchor age, access-review age; `sec.admin_actions_total` and
  `sec.break_glass_total` with alerts actually attached — land with INT-180…INT-192.
- **Tests:** invariants 31–34, 36–40, 47–48 land with the console issues (INT-180 onward);
  the role × tenant matrix with INT-180; the second factor, the realm flow and the session
  bounds in `tests/admin/test_staff_second_factor.py` (INT-365); the credential id shape in
  the same file, with property tests over generated ids (INT-391); the realm-import column
  limits, the image digest and the import file name in
  `tests/infra/test_keycloak_realm_import.py` (INT-390); the login gate's logs off, with the
  default as a near-miss, in `tests/infra/test_staging_admin_tier.py` (INT-485); the
  WebAuthn session-notes provider in its Java suite and `tests/admin/test_webauthn_session_notes_provider.py`
  (INT-378). Break-glass (INT-180):
  the ceremony — reason floor, distinct principal, controller instruction, TTL ceiling — in
  `tests/admin/test_four_eyes.py`; the intent row written before the outcome on both
  break-glass routes in `tests/admin/test_admin_audit.py`; only break-glass roles carrying the
  path in `tests/admin/test_rbac_matrix.py`. Inv. 38's import-graph half and inv. 39 (replay
  is not a read channel) are not tests yet and land with the console issues.

## `device-boundary` — MDSW mode and the study lifecycle

- **Assets:** the `device_functions` capability, the Study Registry, the research store
  clock.
- **Trust boundaries:** certified ↔ uncertified functionality (gate INT-117); study approval
  window ↔ the calendar (expiry de-asserts with no grace).
- **Threats (STRIDE/LINDDUN):** [Nc] an uncertified Class IIb device function placed into
  service; [T] a stale study assertion outliving its approval — the default outcome rather
  than an attack (§9); [R] a device-mode change with no attributable record.
  **Research store (§9 research-store row):** the sealed research store is the **only** place
  raw patient audio persists (files/06 §3's one exception), so [Dd/Nc] a store with no role,
  no surface and no clock becomes an unbounded audio archive; [E] an investigator reaching
  production clinical data from it.
- **Controls (files/10):** §9 device row — gated-capability service as the sole write path,
  `clinical_lead` + `qms_owner` from different organisations, server-side study-reference
  validation, write-ahead audit, immediate page, 60 s reconciliation probe failing closed,
  signed registry with `approval_valid_until`, daily fail-closed probe, weekly reconciliation
  against the enrolment log, study-close runbook; inv. 34/35.
  **Research store (§9):** `investigator` scoped to one `study_id` and no production clinical
  data; its own key custody and access log; automated destruction at the ≤ 12-month ceiling
  with destruction records kept ≥ 3 years (DEST-2017, RG 30224). It is a separately audited
  exception outside the retention engine: `retention_policy.yaml` carries no audio class and
  its loader refuses one (the policy half of inv. 27), so the exception cannot leak into the
  general engine.
- **Signals:** `admin.device_functions_changed_total{direction}`,
  `admin.study_assertion_changed_total`, `acoustic.assertion_expiry_days`,
  `admin.study_registry_probe_status` (named in §9) — land with INT-117 and the console
  issues. The research store's per-file retention countdown, destruction evidence and access
  log (§9) land with the store itself.
- **Tests:** the INT-117 gate test (INT-117's acceptance); inv. 34/35 extend it to the
  registration side with the console issues. The engine-side refusal is
  `tests/legal/test_retention_engine.py::test_loader_refuses_an_audio_retention_class`
  (INT-036). The store itself lands with INT-115, its only writer (the `acoustic` lane's
  ordinal band), and the study-close runbook drill (§9) with it.

## `learning-loops` — proposal-only learning

- **Assets:** evidence bundles, proposal PRs, de-identified analytics views, PatientOverlay
  facts, **research extracts and the register that records them (INT-230)**.
- **Trust boundaries:** learning agent ↔ everything it may not touch (red-flag levels,
  instruments, consent texts, the Talker tool list, PolicyGuard, profile routing — CLAUDE.md
  invariant 12); aggregates ↔ individuals (k ≥ 10); **the consented clinical context ↔ a
  research recipient outside it (INT-230: a separate consent purpose, a separate ethics
  approval, a separate retention clock)**.
- **Threats (STRIDE/LINDDUN):** [T] poisoning through crafted proposals; [Dd/L]
  de-anonymisation of small cohorts; [E] agent over-reach past the proposal boundary;
  **[Nc/L] an export taken under a care consent rather than the `research` one, or under an
  approval that has lapsed; [I] a direct identifier riding out inside an id-shaped field;
  [Dd] linkage of two studies' extracts by an investigator holding both; [Dd] a second
  extract of the same study+spec over an OVERLAPPING window differenced against the first to
  recover the cells in the difference, at any k (INT-262)**; **[T/Nr] an
  unconfirmed model output entering a patient's overlay and, from there, a session or a
  rule; [I] a fact value leaking through the store, a log or a metric label; [Nc] an erasure
  that sweeps the notes and leaves the learning object standing (INT-170)**.
- **Controls (files/10):** §9 learning row — proposal-only with evidence bundles, k ≥ 10,
  sandboxed agent with read-only credentials, PR bot least privilege, canary and rollback;
  PatientOverlay facts require patient or clinician confirmation at type level. **INT-230
  adds: the `research` scope evaluated through the one consent evaluator with a refuser
  DROPPED rather than flagged; a signed-off study registry with no grace day past
  `approval_valid_until` (invariant 35); a closed per-dimension vocabulary with the INT-015
  pattern tier adding refusals on top; a study-scoped keyed pseudonym so two extracts do not
  join; the `research_extracts` retention row gating creation; and an append-only register
  carrying the ethics id and the content hash and no patient reference.** **INT-262 adds the
  differencing gate: before an extract is emitted, the gate reads the register for prior
  extracts of the same study+spec and refuses a window that OVERLAPS one — half-open
  `[start, end)`, so an adjacent window does not — UNLESS the study's registry row states an
  explicit `query_budget`. That budget has NO default and an absent one FAILS CLOSED (a study
  stating none refuses every overlapping window); how much overlap and how many requests a
  study may make is an ethics-committee decision (HB-R1), never one an agent picks. The check
  runs on the window alone, before any patient row is read.** **INT-170 adds:
  the confirmation as a type rather than a check — `FactCandidate` has no `source` and no
  `confirmed_at` field, `confirm()` is the only producer of a `LearnedFact`, and
  `OverlayStore` has no write path that accepts one; no table for unconfirmed candidates at
  all, so an unconfirmed value has nowhere to be written and nothing to read it back; the
  fact value under field-level envelope encryption (invariant 14) with `fact_key` in the
  clear like `slots.slot_id`; `/v1/me/learned` behind the one `ensure_consent` path under
  `core`, patient-only, with every read and change on the hash chain carrying ids only; and
  the DSAR erasure extended to crypto-shred and remove both overlay tables.**
- **Signals:** k-anonymity refusals landed with INT-171 —
  `analytics_view_refused_total{view,reason}` and `analytics_view_materialised_total{view}`,
  whose labels carry a view name and a reason class only, because a refusal labelled with
  the branch or the week it withheld would publish that cell to Prometheus. Proposals and
  rejections landed with INT-172 — `learning_findings_total{signal}`,
  `learning_proposals_total{signal,target}`,
  `learning_proposals_refused_total{signal,reason}` and
  `learning_evidence_bundles_total{view,status}`, labelled the same way and for the same
  reason: `target` is one of ten class names and `reason` is a refusal class, never a pack,
  a clinic or a cohort. **Rollbacks landed with INT-173 —
  `learning_rollbacks_total{guardrail,stage}`, whose labels carry the closed
  `intake_learning.canary.Guardrail` set (acceptance, safety_blocks, completion, csat,
  missing_input) and one of 5/25/100, never a pack, a clinic or a cohort.** **INT-170 adds
  `overlay_facts_confirmed_total{source}` and `overlay_facts_withdrawn_total{action}` on the
  same terms: `source` is one of three closed provenance classes and `action` one of two
  verbs, never a fact key, a patient or a tenant.** **INT-262 surfaces the differencing
  refusals as two new reason classes on INT-230's existing
  `research_extract_refused_total{spec,reason}` — `overlapping_window_unbudgeted` and
  `query_budget_exhausted` — with the audit action `research.extract.refused.<reason>` and no
  window, cohort size or count in either.**
- **Tests:** `k_anonymity` landed with INT-171 (`tests/learning/test_k_anonymity.py`, plus
  `tests/learning/test_analytics_views.py` and its integration lane, which proves the
  `svc_learning_reader` grant reaches the `analytics` views and no base table);
  `proposal_scope` landed with INT-172 (`tests/learning/test_proposal_scope.py`, plus
  `tests/learning/test_inspector_architect.py` and
  `tests/learning/test_evidence_bundle.py`); `learned_fact_provenance` landed with INT-170
  (`tests/learning/test_overlay_provenance.py`, plus `tests/api/test_learned.py` for the
  consent gate, the audit entries, the erasure path and the PHI sweep); overlay
  monotonicity property test with INT-056. **The differencing gate lands with INT-262
  (`tests/research/test_differencing_gate.py`): a golden that serves one extract then
  differences a second over an overlapping window and proves it refused, plus the budgeted
  path, the spec- and study-scoping, the half-open adjacency boundary, and the audit/no-echo
  checks.** **`canary_rollback` landed with INT-173
  (`tests/learning/test_canary_rollback.py`): the simulated dip drives each of the four
  guardrails past its files/09 §4 threshold and asserts a rollback within one evaluation
  window; the healthy stream promotes through every canary stage to completion; a near-miss
  just under a threshold promotes; and a missing or non-finite KPI fails closed rather than
  promoting (invariant 17). The thresholds themselves live in files/09 §4 and
  `intake_learning.canary`, not restated here.**
- **Rollback is a decision, not an application (INT-173):** `intake_learning.canary` is pure
  rule — guardrail snapshots in, a promote/complete/rollback decision out — like
  `intake_learning.publisher` and `intake_platform.admin.flag_governance`. It reverts a
  rollout's exposure but touches no red-flag level, instrument, consent text, Talker tool,
  PolicyGuard or profile routing; `proposal_scope`'s import-closure, no-writer and no-SQL
  gates cover the new module with the rest of the package, so the canary controller cannot
  reach a clinical value any more than the Architect can (invariant 12).
- **Over-reach is unreachable, not rejected (INT-172):** `proposal_scope` walks the
  *transitive* first-party import closure of `services/learning` with `ast` and asserts it
  reaches none of `packages/protocols`, `services/voice-runtime`, `intake_platform.legal`,
  `intake_platform.consent`, `intake_platform.profiles`, `services/api` or
  `packages/voice-clips` — so the [E] threat has no code path rather than a guard on one.
  Three further gates make the rest structural: the pipeline's own imports are allow-listed
  (no HTTP client, no process spawner, no filesystem module — files/09 §7's "no egress" as a
  property of the source, with the sandbox as the second layer rather than the only one); no
  module in the package holds a write-capable call, which is why keeping a proposal out of a
  protocol pack needs no path allow-list; and the proposal vocabulary is a closed tuple of
  ten frozen dataclasses in which no field can carry a triage level or a path.
  `CandidateRedFlag` has no `level` field at all — invariant 1's YELLOW_REVIEW cap as a
  class constant rather than a validator, the same move `LlmCandidateTriage` makes in
  `clinical_schemas.triage`.
- **What a bundle carries, and the one thing refused (INT-172):** ids, counts and
  citations. Citations are members of a closed enumeration; every id arrived through
  INT-171's id-shape gate, and `EvidenceBundle.build` re-runs `materialise` on the way in
  rather than trusting a `Measurement` handed to it, so the k floor and the shape check
  apply again to the artefact that leaves the sandbox. The only prose is the analytics
  registry's own committed `cohort_description`, byte for byte — an attacker-supplied cohort
  is refused without being echoed. files/09 §4's "de-identified exemplars" are **absent, not
  empty**: that is the claim HB-L6 records as one Turkish NLP cannot support, and the
  evidence bundle is the last place to re-make it. Signing is HMAC-SHA256 over the canonical
  digest — the primitive and the canonical form the audit chain and `room_tokens` already
  use — with the key handed in rather than fetched, so the package holds no secrets client
  either.
  the branch or the week it withheld would publish that cell to Prometheus. **INT-230 adds
  `research_extract_refused_total{spec,reason}` and `research_extract_served_total{spec}` on
  the same rule — a spec name and a reason class, never a study id, a recipient, a window or
  a subject count.** Proposals and rejections landed with INT-172; rollbacks with INT-173
  (`learning_rollbacks_total{guardrail,stage}`).
- **Tests:** `k_anonymity` landed with INT-171 (`tests/learning/test_k_anonymity.py`, plus
  `tests/learning/test_analytics_views.py` and its integration lane, which proves the
  `svc_learning_reader` grant reaches the `analytics` views and no base table);
  **`export_gates` landed with INT-230 (`tests/research/test_export_gates.py`), including
  the corpus lane that drives every INT-015 fixture sentence AND every bare fixture
  identifier through the export value check**; `proposal_scope` lands with INT-172; overlay
  monotonicity property test with INT-056.
- **Named for what it is (INT-230): pseudonymisation, not anonymisation.** KSVY m.16(1)
  permits scientific work on health data *anonim hâle getirilen* by the controller, under
  the KVKK m.28/1(b) exemption. A keyed HMAC pseudonym is re-derivable by whoever holds the
  key and is therefore personal data, so that route is unavailable and the pipeline takes
  the other one files/06 §75 states in the same sentence — consent plus a recorded ethics
  id. No type, function or constant in `intake_platform.research` carries the word
  "anonymised", and a test asserts it. Whether KSVY m.16(2)'s separate limb (scientific
  processing under KVKK m.28/1(c)) would additionally apply is a counsel question and is
  asserted nowhere.
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
