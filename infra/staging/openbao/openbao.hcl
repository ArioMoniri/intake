# INT-345 staging OpenBao: server mode, file storage. It starts sealed and
# uninitialised. init.sh initialises and unseals it once, and deploy.sh
# unseals it after every restart.
#
# Storage is a named volume, so the transit KEKs outlive the container. That
# is the property the restart test checks.

ui            = false
disable_mlock = false
api_addr      = "http://openbao:8200"

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
