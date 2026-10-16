# INT-345: the staging API's OpenBao policy. It is the one policy the API
# token carries, besides OpenBao's built-in `default`, which lets a token look
# up and renew itself.
#
# intake_platform.envelope.TransitKekProvider keeps one Transit key per tenant,
# named tenant-<tenant_id>. It posts to transit/keys/<name> before every wrap:
# that is create the first time and update after. It never rotates, exports or
# destroys a key from the API, so no capability for those exists here.
# Outside transit/, one grant (INT-428, ADR-035): the hosted-lane provider
# keys under secret/model-lanes/. The console writes a staged key, promotes it
# on approval and destroys the staged copy; the API reads a key to call the
# provider. No other KV path is reachable.
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

path "secret/data/model-lanes/*" {
  capabilities = ["create", "update", "read"]
}

path "secret/metadata/model-lanes/*" {
  capabilities = ["read", "list", "delete"]
}
