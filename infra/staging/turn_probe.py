"""INT-515: TURN over TLS on 443, checked from outside the way a phone reaches it.

smoke.sh runs this on the staging host against the public name:

    python3 turn_probe.py --connect <STAGING_HOSTNAME> --port 443 --sni turn.<STAGING_HOSTNAME>

It opens TCP to 443, does a verified TLS handshake for the TURN name (so the
certificate Caddy obtained for it is checked, not assumed), and sends one STUN
Binding request (RFC 8489 §5) over the stream. A Binding success with the same
transaction id can only come from the SFU's TURN server, through Caddy's
layer-4 wrapper and the PROXY header it adds: the API behind the same port
would answer HTTP, and an unrouted name would fail the handshake. No
credential is needed and no relay is allocated.

Standard library only: it runs on the host's python3, beside docker.
"""

from __future__ import annotations

import argparse
import os
import socket
import ssl
import struct
import sys
from typing import Protocol

#: RFC 8489 §5: the fixed magic cookie, the Binding request and success types.
MAGIC_COOKIE = 0x2112A442
BINDING_REQUEST = 0x0001
BINDING_SUCCESS = 0x0101
HEADER_LEN = 20


class Stream(Protocol):
    def sendall(self, data: bytes, /) -> None: ...

    def recv(self, size: int, /) -> bytes: ...


def binding_request(transaction: bytes) -> bytes:
    """A Binding request with no attributes: type, length 0, cookie, transaction."""
    if len(transaction) != 12:
        raise ValueError("a STUN transaction id is 12 bytes")
    return struct.pack("!HHI", BINDING_REQUEST, 0, MAGIC_COOKIE) + transaction


def is_binding_success(response: bytes, transaction: bytes) -> bool:
    """Only a Binding success for this transaction, carrying the cookie."""
    if len(response) < HEADER_LEN:
        return False
    kind, _length, cookie = struct.unpack("!HHI", response[:8])
    return kind == BINDING_SUCCESS and cookie == MAGIC_COOKIE and response[8:20] == transaction


def _read_exactly(stream: Stream, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = stream.recv(size - len(data))
        if not chunk:
            break
        data += chunk
    return data


def stun_binding(stream: Stream, *, transaction: bytes) -> bool:
    """One Binding exchange over a stream (STUN over TCP/TLS is self-delimiting)."""
    stream.sendall(binding_request(transaction))
    header = _read_exactly(stream, HEADER_LEN)
    if not is_binding_success(header, transaction):
        return False
    (length,) = struct.unpack("!H", header[2:4])
    return len(_read_exactly(stream, length)) == length


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--connect", required=True, help="the address to dial")
    parser.add_argument("--port", type=int, default=443)
    parser.add_argument("--sni", required=True, help="the TURN name, turn.<host>")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)
    transaction = os.urandom(12)
    context = ssl.create_default_context()
    try:
        with (
            socket.create_connection((args.connect, args.port), timeout=args.timeout) as raw,
            context.wrap_socket(raw, server_hostname=args.sni) as tls,
        ):
            ok = stun_binding(tls, transaction=transaction)
    except (OSError, ssl.SSLError) as err:
        # the class names the failure: refused, timed out, certificate, reset
        print(f"TURN over TLS to {args.sni}:{args.port} failed: {type(err).__name__}")
        return 1
    if not ok:
        print(f"TURN over TLS to {args.sni}:{args.port}: no STUN Binding success came back")
        return 1
    print(f"TURN over TLS to {args.sni}:{args.port}: STUN Binding success")
    return 0


if __name__ == "__main__":
    sys.exit(main())
