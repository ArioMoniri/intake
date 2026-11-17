#!/usr/bin/env python3
"""INT-613: the App Review sign-in harness (D39), over the API's OTP flow.

App Review signs in to a release build with a reserved reviewer number and a
fixed code (D39, INT-488). This harness walks the same calls the app makes,
in the same order, with no Apple credential:

    POST /v1/auth/attest/challenge    a single-use nonce
    POST /v1/auth/otp/request         202; the attestation header rides along
    (the code)                        dev: the peek route; review: the env only
    POST /v1/auth/otp/verify          200, token_type DPoP, with a DPoP proof
    POST /v1/auth/token/refresh       200, with a fresh DPoP proof
    GET  /v1/me/profile               authenticated: anything but 401

With an SMS probe it also checks the D39 property that matters most to the
reviewer path: **the reserved number never sends an SMS**. The probe counts
deliveries before and after. Any increase fails the run.

The report carries step names, HTTP statuses and typed error codes only,
never the number, the code or a token (invariant 6; D39: the code never
reaches code, fixtures, logs or chat).

Two ways to run it, neither needing Apple:

* **in process** (tests/release/test_review_signin_harness.py): main's real
  API app, with the dev attestation tier and the dev peek route, a counting
  delivery adapter as the SMS probe, and synthetic numbers only;
* **against a host** (``--base-url``): ``--probe-unattested`` checks only that
  the public host refuses a sign-in without App Attest. That is the INT-348
  rule that INTAKE_DEV_ALLOW_UNATTESTED is never set on a public host. It
  sends one OTP request for SIGNIN_PROBE_NUMBER, a synthetic number that must
  not be the reviewer's, because every use of the reviewer number pages. The
  owner runs it. No agent does.

A full reviewer sign-in against the synthetic host needs a real App Attest
key, so it can only be proven on a device (INT-348). docs/release/
review-signin-test-plan.md lists exactly what is left for the device.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

#: The env var the owner sets for a review run. Never an argument: argv shows
#: in process listings and shell history.
ENV_REVIEW_CODE: Final[str] = "REVIEW_SIGNIN_CODE"
ENV_REVIEW_NUMBER: Final[str] = "REVIEW_SIGNIN_NUMBER"
ENV_PROBE_NUMBER: Final[str] = "SIGNIN_PROBE_NUMBER"


class Response(Protocol):
    status_code: int

    def json(self) -> Any: ...


class HttpClient(Protocol):
    """httpx.Client and fastapi.testclient.TestClient both satisfy this."""

    def post(
        self, url: str, *, json: Any = None, headers: Mapping[str, str] | None = None
    ) -> Response: ...

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Response: ...


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class DpopKey:
    """An RFC 9449 proof key, P-256, as the mobile client holds one."""

    def __init__(self) -> None:
        self._key = ec.generate_private_key(ec.SECP256R1())
        numbers = self._key.public_key().public_numbers()
        self._jwk = {
            "kty": "EC",
            "crv": "P-256",
            "x": _b64url(numbers.x.to_bytes(32, "big")),
            "y": _b64url(numbers.y.to_bytes(32, "big")),
        }

    def proof(self, method: str, url: str, *, iat: float, access_token: str | None = None) -> str:
        header = {"typ": "dpop+jwt", "alg": "ES256", "jwk": self._jwk}
        claims: dict[str, Any] = {
            "htm": method,
            "htu": url,
            "iat": int(iat),
            "jti": uuid.uuid4().hex,
        }
        if access_token is not None:
            claims["ath"] = _b64url(hashlib.sha256(access_token.encode("ascii")).digest())
        signing_input = (
            _b64url(json.dumps(header, separators=(",", ":")).encode())
            + "."
            + _b64url(json.dumps(claims, separators=(",", ":")).encode())
        )
        der = self._key.sign(signing_input.encode("ascii"), ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        return signing_input + "." + _b64url(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


#: Builds the X-Intake-Attestation payload for one call, from the challenge.
Attestor = Callable[[str], Mapping[str, str]]


def dev_unattested(device_id: str = "review-harness") -> Attestor:
    """The dev tier's self-declared payload. A public host must refuse it."""

    def attest(nonce: str) -> Mapping[str, str]:
        payload = {
            "platform": "ios",
            "mode": "dev-unattested",
            "token": _b64url(b"intake-review-harness"),
            "device_id": device_id,
            "nonce": nonce,
        }
        return {"X-Intake-Attestation": json.dumps(payload)}

    return attest


class CodeSource(Protocol):
    def code(self, client: HttpClient, phone: str) -> str | None: ...


@dataclass(frozen=True)
class DevPeek:
    """Dev tier only: the code from /v1/auth/dev/otp-peek (404 elsewhere)."""

    def code(self, client: HttpClient, phone: str) -> str | None:
        response = client.get("/v1/auth/dev/otp-peek", params={"phone": phone})
        if response.status_code != 200:
            return None
        value = response.json().get("code")
        return str(value) if value else None


@dataclass(frozen=True)
class EnvCode:
    """The review code, read from the environment when it is needed, and only then."""

    environ: Mapping[str, str] = field(default_factory=lambda: os.environ)
    name: str = ENV_REVIEW_CODE

    def code(self, client: HttpClient, phone: str) -> str | None:
        del client, phone
        value = self.environ.get(self.name)
        return value or None


@dataclass(frozen=True)
class Step:
    name: str
    status: int | None
    ok: bool
    error: str | None = None

    def render(self) -> str:
        mark = "ok  " if self.ok else "FAIL"
        code = "-" if self.status is None else str(self.status)
        tail = f" error={self.error}" if self.error else ""
        return f"{mark} {self.name:<18} http={code}{tail}"


@dataclass
class Report:
    steps: list[Step] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.steps) and all(step.ok for step in self.steps)

    def add(self, step: Step) -> bool:
        self.steps.append(step)
        return step.ok

    def render(self) -> str:
        lines = [step.render() for step in self.steps]
        lines.append("sign-in: PASS" if self.ok else "sign-in: FAIL")
        return "\n".join(lines)


def _error_code(response: Response) -> str | None:
    """The typed error code only (errors.py: codes, never narrative)."""
    try:
        body = response.json()
    except ValueError:
        return None
    if not isinstance(body, Mapping):
        return None
    detail = body.get("detail", body)
    if isinstance(detail, Mapping) and isinstance(detail.get("error"), str):
        return str(detail["error"])
    if isinstance(body.get("error"), str):
        return str(body["error"])
    return None


@dataclass
class SignInHarness:
    client: HttpClient
    base_url: str
    attestor: Attestor
    codes: CodeSource
    clock: Callable[[], float] = time.time
    #: Counts SMS deliveries. Set it for the reviewer number: D39 says it never sends.
    sms_probe: Callable[[], int] | None = None
    expect_no_sms: bool = False

    def _attestation(self, report: Report, name: str) -> Mapping[str, str] | None:
        response = self.client.post("/v1/auth/attest/challenge")
        if response.status_code != 201:
            report.add(Step(name, response.status_code, False, _error_code(response)))
            return None
        return self.attestor(str(response.json()["challenge"]))

    def run(self, phone: str) -> Report:
        report = Report()
        sent_before = self.sms_probe() if self.sms_probe else 0

        headers = self._attestation(report, "attest.challenge")
        if headers is None:
            return report
        response = self.client.post("/v1/auth/otp/request", json={"phone": phone}, headers=headers)
        if not report.add(
            Step(
                "otp.request",
                response.status_code,
                response.status_code == 202,
                _error_code(response),
            )
        ):
            return report

        if self.sms_probe is not None:
            sent = self.sms_probe() - sent_before
            if self.expect_no_sms:
                report.add(Step("sms.not_sent", None, sent == 0, None if sent == 0 else "sms_sent"))
            else:
                report.add(
                    Step("sms.sent_once", None, sent == 1, None if sent == 1 else "sms_count")
                )

        code = self.codes.code(self.client, phone)
        if code is None:
            report.add(Step("code.obtained", None, False, "no_code"))
            return report
        report.add(Step("code.obtained", None, True))

        dpop = DpopKey()
        headers = self._attestation(report, "attest.challenge")
        if headers is None:
            return report
        verify_url = f"{self.base_url}/v1/auth/otp/verify"
        response = self.client.post(
            "/v1/auth/otp/verify",
            json={"phone": phone, "code": code},
            headers={**headers, "DPoP": dpop.proof("POST", verify_url, iat=self.clock())},
        )
        bundle = response.json() if response.status_code == 200 else {}
        verified = response.status_code == 200 and bundle.get("token_type") == "DPoP"
        if not report.add(
            Step("otp.verify", response.status_code, verified, _error_code(response))
        ):
            return report

        refresh_url = f"{self.base_url}/v1/auth/token/refresh"
        response = self.client.post(
            "/v1/auth/token/refresh",
            json={"refresh_token": bundle["refresh_token"]},
            headers={"DPoP": dpop.proof("POST", refresh_url, iat=self.clock())},
        )
        refreshed = response.json() if response.status_code == 200 else {}
        if not report.add(
            Step(
                "token.refresh",
                response.status_code,
                response.status_code == 200,
                _error_code(response),
            )
        ):
            return report

        access = str(refreshed["access_token"])
        profile_url = f"{self.base_url}/v1/me/profile"
        response = self.client.get(
            "/v1/me/profile",
            headers={
                "Authorization": f"DPoP {access}",
                "DPoP": dpop.proof("GET", profile_url, iat=self.clock(), access_token=access),
            },
        )
        report.add(
            Step(
                "session.read",
                response.status_code,
                response.status_code != 401,
                _error_code(response),
            )
        )
        return report

    def probe_unattested(self, phone: str) -> Report:
        """A public host refuses the dev tier's self-declared payload."""
        report = Report()
        headers = self._attestation(report, "attest.challenge")
        if headers is None:
            return report
        response = self.client.post("/v1/auth/otp/request", json={"phone": phone}, headers=headers)
        refused = response.status_code in {400, 401, 403}
        report.add(Step("unattested.refused", response.status_code, refused, _error_code(response)))
        return report


def main(argv: Sequence[str] | None = None, *, environ: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", required=True, help="https://<host>, the API's origin")
    parser.add_argument(
        "--probe-unattested",
        action="store_true",
        help="only check that the host refuses a sign-in without App Attest",
    )
    args = parser.parse_args(argv)
    env = os.environ if environ is None else environ
    if not args.probe_unattested:
        print(
            "refused: a full reviewer sign-in on a public host needs a device's App Attest key "
            "(INT-348). Run --probe-unattested here, and the device steps of "
            "docs/release/review-signin-test-plan.md on a TestFlight build."
        )
        return 3
    phone = env.get(ENV_PROBE_NUMBER)
    if not phone:
        print(f"refused: set {ENV_PROBE_NUMBER} to a synthetic number")
        return 3
    if phone == env.get(ENV_REVIEW_NUMBER):
        print("refused: the probe never uses the reviewer number, because its every use pages")
        return 3
    import httpx

    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        harness = SignInHarness(
            client=client,
            base_url=args.base_url,
            attestor=dev_unattested(),
            codes=EnvCode(env),
        )
        report = harness.probe_unattested(phone)
    print(report.render())
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
