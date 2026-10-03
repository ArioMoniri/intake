# Runbook: signing the red rule set with the synthetic-only test key (INT-465)

**Scope: the synthetic AWS test host only** (`i-0e489e48739f5de98`, us-east-1, simulated patients only).

The owner decided on 3 Oct 2026, read with D18, that a test key signs the red rule set for this host. On this host the test-key signature stands in for the physician's sign-off (HB-C1). Every non-synthetic tenant rejects the key. A licensed physician's review is still required before any real patient. This runbook is not the production signing path: that is cosign keyless signing in CI (INT-058), and nothing here touches it.

## What is where

| item | where | secret? |
|---|---|---|
| test key `redset-synthetic-test` (ed25519) | OpenBao Transit on the host, created `exportable=false` and `allow_plaintext_backup=false`, so it is non-exportable | the private half never leaves OpenBao |
| signer policy `redset-synthetic-signer` | `infra/staging/openbao/redset-synthetic-signer-policy.hcl`: `sign` on that key, nothing else | no |
| scoped signing token | `/etc/intake-staging/redset-signer.token` on the host, root-only `0600` | yes; it never leaves the host |
| public half | `packages/protocols/signing/trusted_keys.yaml`, scope `synthetic_test` | no |
| signature envelope | `packages/protocols/signing/red_rule_set.synthetic.json` | no |

The signature covers three things:
- the exact bytes of `files/protocols/base.life_threat.yaml`;
- the exact bytes of `packages/protocols/generic/generic_red.yaml`;
- the sorted ids of the `active` rules, which are the only rules served. A draft is never served.

A change to any of the three voids the signature, and the host then serves nothing (503). The set must be re-signed.

## One-time setup (done 3 Oct 2026)

`infra/staging/redset_signer.sh setup`, run as root on the host. It is idempotent.

- It reads the OpenBao **root token** exactly once, inside the host's shell, from the root-only init file.
- It creates the key and writes the policy.
- It mints an orphan periodic token with only that policy. The token id is generated on the host and handed to OpenBao on stdin.
- It prints only the public half.

No token reaches argv, stdout or a log. Do not run it from a shell that echoes its commands.

## Re-signing after an edit

1. Locally: `uv run python scripts/protocols/red_rule_set_signature.py payload --out <tmp>/payload.json`. It prints the payload as base64.
2. On the host, as root, with the scoped token only: `infra/staging/redset_signer.sh sign <base64>`. It prints the Transit signature and the key version.
3. Locally: `uv run python scripts/protocols/red_rule_set_signature.py assemble --payload <tmp>/payload.json --key-id redset-synthetic-test@1 --transit '<signature>'`. It verifies the envelope against the committed public key under a synthetic tenant before it writes anything.
4. `... red_rule_set_signature.py verify --tenant-kind real` must exit 1 with `refused: key_scope_not_admitted_for_tenant`.

## How the API uses it

The synthetic host's compose sets three variables: `INTAKE_API_TRIAGE_TENANT_KIND=synthetic`, `INTAKE_API_TRIAGE_RULES` and `INTAKE_API_TRIAGE_SIGNATURE`.
- The API refuses to boot with a synthetic tenant in any `INTAKE_ENV` other than `dev` or `staging`.
- Any other tenant kind is real. A real tenant rejects the test key before any cryptography and keeps the HB-C1 interlock.
