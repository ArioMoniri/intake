# INT-345 staging OpenBao: server mode, file storage. It starts sealed and
# uninitialised. init.sh initialises and unseals it once, and deploy.sh
# unseals it after every restart.
#
# Storage is a named volume, so the transit KEKs outlive the container. That
# is the property the restart test checks.
#
# No memory-locking setting: OpenBao 2.6 dropped mlock and refuses to load a
# config that sets it at all. Keeping keys out of swap is the host's job, and
# init.sh and deploy.sh refuse a host with unencrypted swap before this
# server starts (lib.sh require_no_unencrypted_swap).

ui       = false
api_addr = "http://openbao:8200"

storage "file" {
  path = "/openbao/file"
}

# Plain HTTP, on the compose-internal backend network only. No port is
# published, and the API is the only other container on that network that
# holds a token.
listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = true
}
