# ADR-035 · Hosted model lanes for the synthetic deployment until the GPU lanes are healthy (relaxes invariant 19, temporarily)

Status: Accepted (owner decision, 2 Oct 2026, INT-428; narrowed the same day by the binding medical and AI/ML challenger reviews)

## Context

ADR-021 and CLAUDE.md invariant 19 settled that every model runs self-hosted on
open weights. The GPU quota those lanes need has not arrived. Today nothing
serves the LLM, ASR and TTS lanes outside the team GPU box's dev tunnel, so
the app cannot run end to end on the AWS host. On 2 Oct 2026 the product owner
decided, in chat, verbatim:

> "use openai or similar provider let api to be set from admin panel and let to switch for gpu models"

He then extended it: each lane picks a provider and a model. That is a
decision to reach a hosted model vendor. Invariant 19 forbids that on the PHI
path, and the vendor egress gate (INT-001) and the egress allow-list (INT-018,
ADR-025) exist to keep vendors out.

The AWS host is in us-east-1 and holds synthetic patients only (HB-I5,
HB-L11). Two challenger reviews were then made binding:
- **Medical review, finding 12:** hosted and mock lanes must be unrepresentable for real PHI; there is no DPA escape hatch; a swap is gated on red-flag extraction goldens for the exact model version; the model is frozen per session; the synthetic flag is immutable; synthetic or hosted runs never count as clinical evidence.
- **AI/ML review:** hosted lanes belong to a deployment, not a tenant; the resolver returns only attested registry components; an identity probe and a per-call model check; dated snapshots only; one outcome class for refusals; no "mock" in the console.

## Decision

A hosted provider (OpenAI, or a similar provider speaking the same wire shape)
may serve the `llm`, `asr` and `tts` lanes only in the **synthetic
deployment**. Its image alone carries the hosted adapters, and every other
deployment has none to route to.

**What enforces it:**

- **The deployment split.** The adapters are the `intake_hosted_lanes` package (`packages/hosted-lanes`).
  - `infra/staging/Dockerfile.api` is the synthetic image. It alone puts the package on the path, and it bakes `INTAKE_DEPLOYMENT_DATA_CLASS=synthetic`.
  - No package on the PHI closure imports or depends on the adapters.
  - The platform sees them only through a Protocol (`model_lanes.hosted`) and loads them by module name, only when the deployment is synthetic.
- **No PHI escape hatch.**
  - For `real_phi`, a hosted lane is refused by the guard, and neither a `HostedPermit` nor a hosted `ModelAssignment` can be constructed.
  - There is no transfer-basis branch.
  - `mock` is no route at all: the routes are `self_hosted` and `hosted:<provider>`, with an optional hosted fallback behind `self_hosted`.
- **The data class is declared, bound and immutable.**
  - Only the literal `synthetic` admits a hosted lane.
  - The first control write binds the class, and both stores refuse a write that moves it.
  - A declaration that disagrees with the bound class reads as `real_phi`.
- **Models, by role.**
  - Each lane, and each dotted role under it (`llm.council.chair`), picks a provider and a model.
  - Hosted models come from a per-provider allow-list of dated snapshots (`infra/model-lanes/providers.yaml`).
  - Self-hosted models come only from attested registry rows: `model_id@revision` + the weights manifest, and in a PHI deployment `jurisdiction: TR` + `phi_path`.
  - `ModelResolver.resolve(role, *, tenant_id) -> ModelAssignment` is the seam other services call (INT-430).
- **Identity, not address.**
  - A self-hosted lane is healthy only when `GET /identity` returns its attested model, revision and manifest. A loopback tunnel that merely answers is not healthy.
  - A hosted snapshot is probed by its own model record.
  - A per-call model check refuses an answer from another model and quarantines the lane.
  - A refusal, a truncation or an empty output is one outcome: `hosted_lane_no_answer`.
- **The swap gate.** A switch on a gated lane (`llm`, `asr`) needs green red-flag extraction goldens and a green negation set for the exact model version, recorded in `infra/model-lanes/qualifications.yaml`. A real-PHI lane serves only a qualified version.
- **Frozen per session.**
  - `SessionLanes` pins each role's first assignment.
  - A switch or a recovered GPU affects the next session only.
  - A pin that stops being admissible is a refusal (the session falls to typed mode), never another provider.
- **Keys.**
  - Keys live in OpenBao only (`secret/model-lanes/`). They are written through a four-eyes ceremony, or by the owner's terminal route (an SSM SecureString loaded on the host, and re-loaded on every deploy).
  - A key is never stored in the database, never logged and never echoed: the console shows set / not set and the last four characters.
  - A key cannot be entered outside the synthetic deployment.
- **Governance.** The console's "Model lanes" module uses the INT-188 change reasons, the INT-180 four eyes and the write-ahead hash-chained audit.
  - One key narrows: disable hosted, or the one-click switch to GPU. The switch to GPU is refused unless the identity is healthy and the model is qualified.
  - Two keys widen: a route-and-model switch, a key, or releasing the hosted kill switch.
  - An approval re-checks the ceremony's `config_hash` (setting, model pins, eval run ids).
  - The INT-182 voice kill switch also stops hosted lanes for its tenant.
- **Egress.**
  - There is one `dev`-tier allow-list row per provider, with purpose `hosted_model_inference` and `phi_allowed: false`. The catalogue reads the host from that row.
  - The allow-list is hook-protected, so a human applies the row under this ADR. The INT-001 vendor gate then needs the matching exception, which is a CI security gate change and the same human's call.
  - Until then every hosted lane reads `hosted_egress_not_listed`.
- **The model boundary is unchanged.**
  - Hosted adapters sit behind the existing interfaces (`ExtractionGateway`, `Transcriber`, `TtsGateway`).
  - Instructions and data are in separate roles under a strict JSON Schema (invariant 14).
  - RED/YELLOW come only from the rules engine (invariant 1).
  - PolicyGuard runs downstream as before (invariant 2).
  - Every TTS input is refused if it carries a numeral, on every lane (invariant 22).
  - Logs and traces carry ids only (invariant 6).
  - A synthetic or hosted run never counts as files/04 §8.3 evidence (`ModelAssignment.clinical_evidence`).

## Consequences

**What stays relaxed, and only here.** Invariant 19 is relaxed for the
synthetic deployment's hosted lanes, and nowhere else.
- The PHI path is still self-hosted end to end.
- `cascade_fast` and `s2s_cloud` still do not exist.
- Hosted providers are declared `self_hostable: false, phi_path: false` in their catalogue. The self-hosting registry stays a statement about what we host.

**When it reverts.** The relaxation reverts when the GPU lanes are healthy,
and that condition, not a date, is the trigger:
1. Each lane takes the one-click switch to GPU.
2. Each fallback is removed by a ceremony.
3. The key is left unset.
4. A reviewed change removes the allow-list row, the gate exception and the synthetic image's adapter path.

**What the tests hold.** `tests/platform/test_model_lane_*.py` and
`tests/admin/test_model_lanes_routes.py` cover:
- the decision table;
- `mock_hosted_unrepresentable_for_phi_tenant`;
- `synthetic_flag_immutable`;
- `model_pin_frozen_in_session`;
- `lane_swap_requires_green_rf_extraction_goldens`;
- the deployment split;
- identity mismatch;
- the key that is never echoed;
- the four-eyes switch and its audit chain;
- the fallback.

**Owner, legal and clinical items:**
- the allow-list row and the gate exception;
- the provider key;
- a second console human for approvals;
- unit prices and budgets;
- the golden set and the sensitivity floor a swap must clear (a physician's decision);
- a forward proxy giving the synthetic host a route to the provider.

**Not in this change; reported as split rows:**
- guarded transport for the self-hosted extraction clients;
- the identity endpoint on the GPU servers;
- a drift canary;
- recording keys carrying model@revision and decoding parameters;
- a schema-keyword lint.

## Amendment, 3 Oct 2026 — INT-442 and INT-443

**The forward proxy (INT-442).** The synthetic host's API has one route out: a default-deny squid (`egress-proxy` in `infra/staging/compose.yaml`). Its config is rendered from the allow-list's `hosted_model_inference` rows and nothing else. `INTAKE_EGRESS_PROXY_URL` is honoured only in the synthetic deployment; anywhere else the API refuses to boot.

**ElevenLabs as the synthetic host's TTS for scripted clips (INT-443).**
- **It is a clip vendor, not a model lane.** `ClipVendor.ELEVENLABS` sits beside `ProviderId` in the key vault, under the same OpenBao path. It has no catalogue row, no lane default and no console switch. It speaks only the server's scripted catalogue, through the George route and its pre-bake, in the v2 delivery profiles (INT-424). RED is never fetched (invariant 21), and numerals and markup are refused (invariant 22).
- **Where it is reached.** Only through the allow-list row `elevenlabs-api` (the owner's protected change), the in-process guard and the forward proxy, on `NON_PERSONAL` data. A vendor failure falls back to the self-hosted TTS when one is configured, and the lane is recorded per clip.
- **The dated-snapshot rule, stated rather than waived.** The AI/ML review's "dated snapshots only" binds the model-lane allow-list. ElevenLabs publishes no dated snapshots, so `eleven_multilingual_v2` cannot be a row of it, and the clip lane stays outside the console's model catalogue for that reason. What stands in for the snapshot pin:
  - every clip is content-addressed (`clip_text_hash`) under `delivery.<context>@v<version>`;
  - it is pre-baked once and kept on a persistent volume;
  - a vendor-side change to the model behind the name can only reach a cache miss.
  The AI/ML reviewer should confirm or refuse this before the lane serves anything beyond the synthetic stress tests. A change of model is ADR-034's question, not a profile edit.

**When it reverts.** With the rest of this ADR. The steps: remove `INTAKE_HOSTED_TTS` from the staging compose, the `elevenlabs-api` row and its gate exception, and the key.
