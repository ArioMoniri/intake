# INT-345: the staging API's OpenBao policy. It is the one policy the API
# token carries, besides OpenBao's built-in `default`, which lets a token look
# up and renew itself.
#
# intake_platform.envelope.TransitKekProvider keeps one Transit key per tenant,
# named tenant-<tenant_id>. It posts to transit/keys/<name> before every wrap:
# that is create the first time and update after. It never rotates, exports or
# destroys a key from the API, so no capability for those exists here.
# Outside transit/, two grants. INT-428 (ADR-035): the hosted-lane provider
# keys under secret/model-lanes/. The console writes a staged key, promotes it
# on approval and destroys the staged copy; the API reads a key to call the
# provider. INT-528: read on the SMS vendor's document, secret/api/netgsm,
# which netgsm_secrets.sh writes with the root token; the API can neither
# write nor list it. INT-578: read on the OTP pepper, secret/api/otp, which
# lib.sh's ensure_otp_pepper writes with the root token; the same, read only.
# No other KV path is reachable.
#
# Caveat: OpenBao's trailing glob also matches the key's sub-paths, such as
# /config. Tightening that needs a per-tenant path list, which the staging
# host does not have, because tenants are created at runtime.

path "transit/keys/tenant-*" {
  capabilities = ["create", "update"]
}

path "transit/encrypt/tenant-*" {
  capabilities = ["update"]
}

path "transit/decrypt/tenant-*" {
  capabilities = ["update"]
}

path "transit/rewrap/tenant-*" {
  capabilities = ["update"]
}

# INT-584 (owner decision D38): read on the phone-tokenization key,
# secret/api/tokenization, which tokenization_key.sh writes with the root
# token (moved from the env file with the same material, or made for a new
# host). The API can neither write, list nor delete it.
path "secret/data/api/tokenization" {
  capabilities = ["read"]
}

path "secret/data/model-lanes/*" {
  capabilities = ["create", "update", "read"]
}

path "secret/metadata/model-lanes/*" {
  capabilities = ["read", "list", "delete"]
}

path "secret/data/api/netgsm" {
  capabilities = ["read"]
}

path "secret/data/api/otp" {
  capabilities = ["read"]
}
