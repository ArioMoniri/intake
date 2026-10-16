# INT-465: the policy of the one token that signs the red rule set on the
# synthetic AWS host. Owner decision, 3 Oct 2026, read with D18: a test key
# signs that rule set for the synthetic test server only.
#
# It allows exactly one thing: sign with the synthetic-only test key. It cannot
# read, export, back up, rotate, configure or delete the key, and it cannot
# touch any tenant KEK. The key itself is ed25519, created non-exportable by
# redset_signer.sh setup. Its public half is committed in
# packages/protocols/signing/trusted_keys.yaml.

path "transit/sign/redset-synthetic-test" {
  capabilities = ["update"]
}
