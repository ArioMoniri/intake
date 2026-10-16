# Runbook: model lanes, self-hosted or hosted, provider and model (INT-428, ADR-035)

The admin console's **Model lanes** module (`/model-lanes`) decides which provider and model serve each lane (`llm`, `asr`, `tts`) and each role under a lane (for example `llm.council.chair`).

ADR-035 is the owner decision it implements, as narrowed by the binding reviews:
- Hosted providers exist only in the **synthetic deployment**. Its image alone carries the adapters and bakes `INTAKE_DEPLOYMENT_DATA_CLASS=synthetic`.
- In a real-PHI deployment a hosted lane is unrepresentable, and the console offers only TR-attested registry models.
- There is no `mock` route.

The alert for every action below is `admin_model_lane_changes_total`, labelled by `control` and `outcome`. Who acted is recorded on the hash-chained audit chain.

## Where the control lives

- **The control record**
  - Lives in Redis at `INTAKE_MODEL_LANES_REDIS_URL`, as one JSON record (`intake:model-lanes:v1:control`), written compare-and-set on its revision.
  - No record reads as every lane `self_hosted` on its default attested model, with no fallback.
  - The first write binds the deployment's data class, and both stores refuse a write that moves it.
- **Provider keys**
  - Live in OpenBao KV v2 only, at `secret/model-lanes/providers/<id>`, and only in the synthetic deployment.
  - The API's token holds `create, update, read` on `secret/data/model-lanes/*` and `read, list, delete` on `secret/metadata/model-lanes/*`, with a KV v2 engine at `secret/` (`configure_openbao`; `infra/staging/openbao/intake-api-policy.hcl`).
  - **The terminal route.** In a shell that holds the key, run `set -a; . ~/.intake-secrets.env; set +a; make put-key PROVIDER=openai` (or `elevenlabs`).
    - The key goes to the SSM SecureString `/intake/staging/<provider>_api_key`.
    - The host loads it into the same OpenBao record.
    - Only "set · …last4" is printed.
    - `deploy.sh` re-loads any such parameter on every deploy, so a parameter that exists wins. To rotate, run it again, or delete the parameter and use the console.
  - A key being approved is staged at `secret/model-lanes/staged/<ref>`. The staged copy is destroyed when its ceremony settles or expires.
  - The console shows set / not set and the last four characters, never more.
- **Models**
  - Hosted models are dated snapshots in `infra/model-lanes/providers.yaml`.
  - Self-hosted models are pinned rows of `observability/registry.yaml`. A PHI deployment also requires `jurisdiction: TR` and `phi_path: true`. Which rows serve which lane is set in `infra/model-lanes/self-hosted.yaml`.
- **Qualifications**
  - Live in `infra/model-lanes/qualifications.yaml`, one row per exact model version.
  - A row records green red-flag extraction goldens and a green negation-set run.
  - The file starts empty. A row is added only after a physician has signed off on the golden set and its runs have been made with `make eval-live`.
- **Identity**
  - Each GPU lane's `INTAKE_LANE_<LANE>_SELF_HOSTED_URL` must answer `GET /identity` with `{model_id, revision, weights_manifest_sha256}`.
  - An endpoint that answers as anything else, or answers nothing, is never healthy. This is how an SSH loopback tunnel is told apart from the attested model.
- **The provider's egress row**
  - Lives in `infra/security/egress-allowlist.yaml`, which is hook-protected.
  - Without the row, every hosted lane reads `hosted_egress_not_listed`.
- **The synthetic host's route out** (INT-442)
  - The API's networks are all internal. Its one way out is the `egress-proxy` service in `infra/staging/compose.yaml`, a default-deny squid named by `INTAKE_EGRESS_PROXY_URL=http://egress-proxy:3128`.
  - The proxy's config, `infra/staging/egress/squid.conf`, is rendered from the allow-list's `hosted_model_inference` rows and nothing else (`make egress-conf`). With no such row it admits nothing. The build proxy (`infra/security/squid/squid.conf`) never admits those rows.
  - The variable belongs to the synthetic deployment alone. The API refuses to boot when it is set anywhere else (`EgressProxyRefused`), and nothing but the staging compose sets it.
  - Every deploy proves it live: `smoke.sh` step 6 runs `infra/staging/egress_probe.py proxy` in the api container. It checks that there is no direct route, that an unlisted host and the metadata address get the proxy's 403, and that every hosted row is tunnelled.
  - Adding a provider is one protected change: the allow-list row, the removal of its purpose from the "awaiting the owner" test set, the regenerated `infra/staging/egress/squid.conf`, and the INT-001 vendor-gate exception for exactly those two files and that host.

## Stopping hosted lanes (narrowing: one key)

These actions can be taken by `sre_oncall`, `clinical_lead`, `platform_owner` or `platform_admin`:

- **Disable hosted** (`POST /admin/model-lanes/hosted/disable`)
  - Every hosted route and every hosted fallback stops on the next resolution, in every process.
  - A lane routed `hosted:<p>` switches over to `self_hosted` if the GPU identity is healthy. Otherwise it refuses with `hosted_disabled`.
- **The INT-182 voice kill switch.** Engaging it for a tenant also stops hosted lanes for that tenant, instantly.
- **Switch to GPU** (`POST /admin/model-lanes/self-hosted`, body `{"lanes": [...], "reason_class", "justification"}`)
  - Refuses with `model_lanes_self_hosted_not_healthy` unless a fresh identity probe of each named lane shows its attested model.
  - On a gated lane, also refuses with `model_not_qualified` if that model version is unqualified.

## Widening (two keys)

1. A requester (`platform_owner` or `platform_admin`) opens the ceremony.
2. A different human approves it within 15 minutes, on a distinct credential and session, with a fresh assertion id. The approver must be `platform_owner`, `qms_owner` or `compliance_officer`.

The ceremonies:

1. **Set the provider key** (synthetic deployment only)
   - Open: `PUT /admin/model-lanes/keys/<provider>` with `api_key`.
   - Approve: `POST /admin/model-lanes/keys/pending/<id>/approve`.
2. **Switch a lane or role**
   - Open: `PUT /admin/model-lanes/route/<role>`. The body carries `route` (`self_hosted` | `hosted:<provider>`), an optional `model` key, and an optional hosted `fallback` and `fallback_model` behind `self_hosted`.
   - Approve: `POST /admin/model-lanes/route/pending/<id>/approve`.
   - The brief shows the model's version, its pin, the qualifying eval run ids and a `config_hash`.
   - The approval refuses with `model_lanes_changed` if the control moved since the request. It refuses with `model_lanes_config_changed`, or `model_not_qualified`, if a model, pin or qualification moved.
3. **Release the hosted kill switch**
   - Open: `POST /admin/model-lanes/hosted/release`.
   - Approve: `.../hosted/release/<id>/approve`.

## Reading the module

- **The deployment:** the declared, bound and effective data class, and whether this image carries hosted lanes at all.
- **Each lane and configured role:**
  - its setting;
  - what is serving now: provider, model id, version and pin, plus the decision's reason code;
  - whether that version is qualified;
  - whether a run on it could count as clinical evidence (only a qualified self-hosted model on a real-PHI deployment can);
  - the self-hosted identity state.
- **Per lane:**
  - every selectable model with its identity probe and qualification;
  - p50 and p95 latency over 1 h, and calls and cost over 24 h, from Prometheus (`INTAKE_OPS_PROMETHEUS_URL`).
- **Cost** reads `price_not_configured` until the owner fills `infra/costs/unit-prices.yaml`. Self-hosted rows read `not_metered`.

## When a lane refuses

| code | meaning | what to do |
|---|---|---|
| `self_hosted_unhealthy` | the GPU lane is down, quarantined or not proving its identity | restore the GPU lane and its `/identity`; or, in the synthetic deployment, approve a hosted fallback |
| `model_not_qualified` | that exact model version has no green red-flag goldens and negation run | clinical sign-off on the golden set, then `make eval-live`, then a reviewed qualification row |
| `hosted_not_in_deployment` | this image carries no hosted adapters | expected in a PHI deployment; nothing to fix |
| `hosted_lane_real_phi_refused` | the deployment is (or reads as) real PHI | expected; hosted lanes do not exist here |
| `hosted_egress_not_listed` | the provider has no allow-list row | the protected allow-list change under ADR-035 |
| `hosted_key_not_set` / `hosted_key_store_unconfigured` | no key in OpenBao, or no key store | the key-set ceremony; check OpenBao is unsealed |
| `hosted_disabled` / `kill_switch_engaged` | a kill switch is engaged | release it only by its ceremony |
| `model_identity_mismatch` | a backend answered as another model | the lane is quarantined for the cooldown; check what is deployed behind it |
| `session_*` | a session's frozen model stopped being admissible | the session falls to typed mode; the next session resolves afresh |

## Reverting ADR-035

When every GPU lane is healthy and qualified:
1. Switch each lane to GPU.
2. Remove each fallback by a ceremony.
3. Leave the key unset.

A reviewed change then removes:
- the allow-list row;
- the gate exception;
- the synthetic image's adapter path.
