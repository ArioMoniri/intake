"""INT-563 (ADR-043) — the four-eyes step-up: a fresh WebAuthn re-authentication
at Keycloak, proven by its ID token, spent once on one approval.

files/08 §2.3: *"Step-up is a fresh, single-use WebAuthn assertion at the
moment of the action."* Before this issue an approval carried an
``assertion_id`` the API never checked. This suite holds the replacement to
its contract, and most of it is near misses: each one is the honest ceremony
with exactly one thing changed, and each must be refused with its own code —
fail closed, never a fallback.

No test dials Keycloak (``step_up_fakes.RecordedKeycloak`` plays both hops
over the committed realm's mappers) and no key material is committed.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from intake_platform.admin.four_eyes import ActorBlock
from intake_platform.admin.roles import AdminRole
from intake_platform.admin.step_up import (
    CEREMONY_TTL,
    ENV_STEP_UP_EXCHANGE_URL,
    ENV_STEP_UP_REDIRECT_URI,
    GRANT_TTL,
    STEP_UP_CLIENT_ID,
    HttpTokenExchange,
    StepUpExchangeFailed,
    StepUpNotFresh,
    StepUpReplayed,
    StepUpService,
    StepUpTokenRefused,
    StepUpUnknown,
    StepUpWithoutWebAuthn,
    step_up_config_from_env,
    step_up_service_from_env,
)
from step_up_fakes import (
    CONFIG,
    ISSUER,
    Clock,
    Login,
    RecordedKeycloak,
    build_step_up,
)

REPO = Path(__file__).resolve().parents[2]
REALMS = {
    "dev": REPO / "infra" / "keycloak" / "dev-realm.json",
    "staging": REPO / "infra" / "staging" / "keycloak" / "intake-realm.json",
}
ACTION = "a" * 32
OTHER_ACTION = "b" * 32
SUBJECT = "kc-sub-qms-owner"
SESSION = "sid-qms-owner-1"
FRESH_CREDENTIAL = "c3RlcC11cC1jcmVkLTAwMDAwMQ"  # 19 bytes, base64url, no padding


def _login(**changes: Any) -> Login:
    values: dict[str, Any] = {
        "subject": SUBJECT,
        "session_id": SESSION,
        "credential_id": FRESH_CREDENTIAL,
    }
    values.update(changes)
    return Login(**values)


@pytest.fixture()
def clock() -> Clock:
    return Clock()


@pytest.fixture()
def pair(clock: Clock) -> tuple[StepUpService, RecordedKeycloak]:
    return build_step_up(clock)


def _ceremony(
    pair: tuple[StepUpService, RecordedKeycloak], login: Login | None = None, action: str = ACTION
) -> tuple[str, str]:
    service, keycloak = pair
    _, url = service.begin(subject=SUBJECT, session_id=SESSION, action_id=action)
    return keycloak.authorize(url, login or _login())


def _complete(pair: tuple[StepUpService, RecordedKeycloak], login: Login | None = None) -> Any:
    state, code = _ceremony(pair, login)
    return pair[0].complete(subject=SUBJECT, session_id=SESSION, state=state, code=code)


class TestTheCeremony:
    def test_the_authorization_url_forces_a_fresh_login_and_keeps_the_verifier(
        self, pair: tuple[StepUpService, RecordedKeycloak]
    ) -> None:
        ceremony, url = pair[0].begin(subject=SUBJECT, session_id=SESSION, action_id=ACTION)
        query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        assert query["client_id"] == STEP_UP_CLIENT_ID
        assert (query["prompt"], query["max_age"]) == ("login", "0")
        assert query["code_challenge_method"] == "S256"
        assert (query["state"], query["nonce"]) == (ceremony.state, ceremony.nonce)
        # the PKCE verifier is what redeems the code; it never leaves the API
        assert ceremony.verifier not in url
        assert ceremony.state != ceremony.nonce

    def test_an_honest_ceremony_yields_one_grant_carrying_the_key_just_used(
        self, pair: tuple[StepUpService, RecordedKeycloak], clock: Clock
    ) -> None:
        grant = _complete(pair)
        assert grant.grant_id.startswith("sug_") and len(grant.grant_id) == 36
        assert (grant.subject, grant.session_id, grant.action_id) == (SUBJECT, SESSION, ACTION)
        assert grant.credential_id == FRESH_CREDENTIAL
        assert grant.assertion_ref.startswith("stepup:") and len(grant.assertion_ref) == 39
        assert grant.expires_at == clock.now + GRANT_TTL
        login_block = ActorBlock(
            subject=SUBJECT,
            role=AdminRole.QMS_OWNER,
            org="org:intake",
            authenticator_aaguid="00000000-0000-0000-0000-000000000000",
            credential_id="cred-qms-owner-000000001",
            session_id=SESSION,
        )
        approver = grant.approver(login_block)
        assert approver.credential_id == FRESH_CREDENTIAL != login_block.credential_id
        assert (approver.subject, approver.session_id, approver.role) == (
            SUBJECT,
            SESSION,
            AdminRole.QMS_OWNER,
        )


class TestNearMisses:
    """The honest ceremony with one thing changed — each refused, by code."""

    @pytest.mark.parametrize(
        ("login", "refusal"),
        [
            # a remembered login: auth_time an hour before the ceremony began
            (_login(auth_offset_s=-3600), StepUpNotFresh),
            # 31 s before the ceremony: just past the clock leeway
            (_login(auth_offset_s=-31), StepUpNotFresh),
            (_login(overrides={"auth_time": None}), StepUpNotFresh),
            (_login(amr=("pwd",)), StepUpWithoutWebAuthn),
            (_login(amr=("pwd", "otp")), StepUpWithoutWebAuthn),
            (_login(amr=()), StepUpWithoutWebAuthn),
            (_login(subject="kc-sub-clinical-lead"), StepUpTokenRefused),
            (_login(session_id="sid-qms-owner-2"), StepUpTokenRefused),
            (_login(nonce="another-ceremony"), StepUpTokenRefused),
            # an access token minted for the same client is not an ID token
            (_login(typ="Bearer"), StepUpTokenRefused),
            (_login(overrides={"azp": "admin-web"}), StepUpTokenRefused),
            (_login(overrides={"aud": "admin-web"}), StepUpTokenRefused),
            (_login(overrides={"iss": "http://localhost:8080/realms/master"}), StepUpTokenRefused),
            (_login(credential_id="not a credential"), StepUpTokenRefused),
            (_login(aaguid=""), StepUpTokenRefused),
            (_login(overrides={"jti": ""}), StepUpTokenRefused),
        ],
    )
    def test_refused(
        self, pair: tuple[StepUpService, RecordedKeycloak], login: Login, refusal: type
    ) -> None:
        with pytest.raises(refusal):
            _complete(pair, login)

    def test_thirty_seconds_of_clock_skew_still_passes(
        self, pair: tuple[StepUpService, RecordedKeycloak]
    ) -> None:
        # near miss to the -31 s case above: the leeway is inclusive
        assert _complete(pair, _login(auth_offset_s=-30)).action_id == ACTION

    def test_an_expired_id_token_is_refused(
        self, pair: tuple[StepUpService, RecordedKeycloak], clock: Clock
    ) -> None:
        state, code = _ceremony(pair, _login(overrides={"exp": clock.epoch() - 400}))
        with pytest.raises(StepUpTokenRefused):
            pair[0].complete(subject=SUBJECT, session_id=SESSION, state=state, code=code)

    def test_a_tampered_signature_is_refused(
        self, pair: tuple[StepUpService, RecordedKeycloak], clock: Clock
    ) -> None:
        honest, keycloak = pair

        def tampered(*, code: str, verifier: str) -> str:
            head, body, signature = keycloak.exchange(code=code, verifier=verifier).split(".")
            flipped = ("A" if signature[0] != "A" else "B") + signature[1:]
            return f"{head}.{body}.{flipped}"

        service = StepUpService(
            config=CONFIG, verifier=honest.verifier, exchange=tampered, clock=clock
        )
        _, url = service.begin(subject=SUBJECT, session_id=SESSION, action_id=ACTION)
        state, code = keycloak.authorize(url, _login())
        with pytest.raises(StepUpTokenRefused):
            service.complete(subject=SUBJECT, session_id=SESSION, state=state, code=code)

    def test_a_refused_code_exchange_refuses_the_step_up(
        self, pair: tuple[StepUpService, RecordedKeycloak]
    ) -> None:
        state, code = _ceremony(pair)
        with pytest.raises(StepUpExchangeFailed):
            pair[0].complete(
                subject=SUBJECT, session_id=SESSION, state=state, code=code + "-not-issued"
            )

    def test_the_state_is_spent_on_the_first_try_whatever_follows(
        self, pair: tuple[StepUpService, RecordedKeycloak]
    ) -> None:
        state, code = _ceremony(pair, _login(amr=("pwd",)))
        with pytest.raises(StepUpWithoutWebAuthn):
            pair[0].complete(subject=SUBJECT, session_id=SESSION, state=state, code=code)
        with pytest.raises(StepUpUnknown):
            pair[0].complete(subject=SUBJECT, session_id=SESSION, state=state, code=code)

    def test_another_callers_state_is_unknown_to_them(
        self, pair: tuple[StepUpService, RecordedKeycloak]
    ) -> None:
        state, code = _ceremony(pair)
        with pytest.raises(StepUpUnknown):
            pair[0].complete(subject="kc-sub-auditor", session_id=SESSION, state=state, code=code)
        state, code = _ceremony(pair)
        with pytest.raises(StepUpUnknown):
            pair[0].complete(subject=SUBJECT, session_id="sid-other", state=state, code=code)

    def test_an_unknown_or_oversized_state_is_unknown(
        self, pair: tuple[StepUpService, RecordedKeycloak]
    ) -> None:
        for state in ("", "x" * 129, "never-issued"):
            with pytest.raises(StepUpUnknown):
                pair[0].complete(subject=SUBJECT, session_id=SESSION, state=state, code="c")

    def test_a_ceremony_outlives_nothing_past_its_window(
        self, pair: tuple[StepUpService, RecordedKeycloak], clock: Clock
    ) -> None:
        state, code = _ceremony(pair)
        clock.advance(CEREMONY_TTL + timedelta(seconds=1))
        with pytest.raises(StepUpUnknown):
            pair[0].complete(subject=SUBJECT, session_id=SESSION, state=state, code=code)

    def test_one_id_token_is_spent_once(self, clock: Clock) -> None:
        service, keycloak = build_step_up(clock)
        fixed = _login(overrides={"jti": "one-token"})
        first = _complete((service, keycloak), fixed)
        assert first.action_id == ACTION
        with pytest.raises(StepUpReplayed):
            _complete((service, keycloak), fixed)

    def test_a_caller_holds_at_most_three_open_ceremonies(
        self, pair: tuple[StepUpService, RecordedKeycloak]
    ) -> None:
        oldest = _ceremony(pair)
        for _ in range(3):
            _ceremony(pair)
        with pytest.raises(StepUpUnknown):
            pair[0].complete(subject=SUBJECT, session_id=SESSION, state=oldest[0], code=oldest[1])


class TestRedemption:
    def test_a_grant_is_spent_once_on_its_own_action(
        self, pair: tuple[StepUpService, RecordedKeycloak]
    ) -> None:
        grant = _complete(pair)
        service = pair[0]
        assert service.redeem(grant.grant_id, subject=SUBJECT, session_id=SESSION, action_id=ACTION)
        with pytest.raises(StepUpUnknown):
            service.redeem(grant.grant_id, subject=SUBJECT, session_id=SESSION, action_id=ACTION)

    @pytest.mark.parametrize(
        "who",
        [
            {"subject": "kc-sub-clinical-lead", "session_id": SESSION, "action_id": ACTION},
            {"subject": SUBJECT, "session_id": "sid-qms-owner-2", "action_id": ACTION},
            {"subject": SUBJECT, "session_id": SESSION, "action_id": OTHER_ACTION},
        ],
    )
    def test_a_foreign_presentation_is_refused_and_burns_nothing(
        self, pair: tuple[StepUpService, RecordedKeycloak], who: dict[str, str]
    ) -> None:
        grant = _complete(pair)
        with pytest.raises(StepUpUnknown):
            pair[0].redeem(grant.grant_id, **who)
        # the owner still holds it: a leaked id cannot be used to burn it
        owner = pair[0].redeem(
            grant.grant_id, subject=SUBJECT, session_id=SESSION, action_id=ACTION
        )
        assert owner.grant_id == grant.grant_id

    def test_a_grant_expires(
        self, pair: tuple[StepUpService, RecordedKeycloak], clock: Clock
    ) -> None:
        grant = _complete(pair)
        clock.advance(GRANT_TTL + timedelta(seconds=1))
        with pytest.raises(StepUpUnknown):
            pair[0].redeem(grant.grant_id, subject=SUBJECT, session_id=SESSION, action_id=ACTION)

    def test_an_unused_string_is_not_a_grant(
        self, pair: tuple[StepUpService, RecordedKeycloak]
    ) -> None:
        # near miss to the pre-INT-563 contract, where any unused string passed
        for presented in ("assert-fresh-1", "sug_" + "0" * 32, ""):
            with pytest.raises(StepUpUnknown):
                pair[0].redeem(presented, subject=SUBJECT, session_id=SESSION, action_id=ACTION)


class TestConfiguration:
    CALLBACK = "https://admin.example.test/step-up/callback"
    TOKEN = "http://keycloak:8080/realms/intake/protocol/openid-connect/token"
    STAGING_ISSUER = "https://auth.example.test/realms/intake"

    def _env(self, **values: str) -> dict[str, str]:
        return {
            ENV_STEP_UP_REDIRECT_URI: self.CALLBACK,
            ENV_STEP_UP_EXCHANGE_URL: self.TOKEN,
            **values,
        }

    def test_neither_variable_leaves_it_unconfigured(self) -> None:
        assert step_up_config_from_env({}, issuer=self.STAGING_ISSUER) is None
        assert step_up_service_from_env({}, issuer=self.STAGING_ISSUER, keys={}) is None

    def test_the_staging_shape_is_accepted(self) -> None:
        config = step_up_config_from_env(self._env(), issuer=self.STAGING_ISSUER)
        assert config is not None
        assert config.authorize_endpoint == f"{self.STAGING_ISSUER}/protocol/openid-connect/auth"
        assert (config.token_endpoint, config.redirect_uri) == (self.TOKEN, self.CALLBACK)

    @pytest.mark.parametrize(
        "env",
        [
            # one without the other
            {ENV_STEP_UP_REDIRECT_URI: CALLBACK},
            {ENV_STEP_UP_EXCHANGE_URL: TOKEN},
            # the code would cross a public network in the clear
            {
                ENV_STEP_UP_REDIRECT_URI: CALLBACK,
                ENV_STEP_UP_EXCHANGE_URL: "http://auth.example.test/realms/intake/token",
            },
            # a redirect anywhere but the console's callback
            {
                ENV_STEP_UP_REDIRECT_URI: "https://admin.example.test/voice",
                ENV_STEP_UP_EXCHANGE_URL: TOKEN,
            },
            {ENV_STEP_UP_REDIRECT_URI: CALLBACK + "?next=/voice", ENV_STEP_UP_EXCHANGE_URL: TOKEN},
            {ENV_STEP_UP_REDIRECT_URI: CALLBACK, ENV_STEP_UP_EXCHANGE_URL: "ftp://keycloak/token"},
        ],
    )
    def test_a_malformed_pair_raises(self, env: dict[str, str]) -> None:
        with pytest.raises(ValueError):
            step_up_config_from_env(env, issuer=self.STAGING_ISSUER)

    def test_loopback_http_is_the_dev_shape(self) -> None:
        env = {
            ENV_STEP_UP_REDIRECT_URI: "http://localhost:3000/step-up/callback",
            ENV_STEP_UP_EXCHANGE_URL: f"{ISSUER}/protocol/openid-connect/token",
        }
        assert step_up_config_from_env(env, issuer=ISSUER) is not None


class TestTheCodeExchange:
    """``HttpTokenExchange`` against a recorded token endpoint (httpx mock)."""

    def _exchange(self, handler: Any) -> HttpTokenExchange:
        return HttpTokenExchange(
            CONFIG, client=httpx.Client(transport=httpx.MockTransport(handler))
        )

    def test_it_posts_the_public_client_pkce_redemption(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={"id_token": "header.body.sig", "access_token": "x"})

        assert self._exchange(handler)(code="the-code", verifier="the-verifier") == (
            "header.body.sig"
        )
        form = {k: v[0] for k, v in parse_qs(seen[0].content.decode()).items()}
        assert str(seen[0].url) == CONFIG.token_endpoint
        assert form == {
            "grant_type": "authorization_code",
            "client_id": STEP_UP_CLIENT_ID,
            "code": "the-code",
            "redirect_uri": CONFIG.redirect_uri,
            "code_verifier": "the-verifier",
        }
        # a public client: no secret travels, the verifier is the proof
        assert "client_secret" not in form and "authorization" not in seen[0].headers

    @pytest.mark.parametrize(
        "response",
        [
            httpx.Response(400, json={"error": "invalid_grant"}),
            httpx.Response(302, headers={"location": "https://elsewhere.test/"}),
            httpx.Response(200, text="not json"),
            httpx.Response(200, json={"access_token": "only"}),
            httpx.Response(200, json=["id_token"]),
        ],
    )
    def test_anything_but_an_id_token_fails_the_exchange(self, response: httpx.Response) -> None:
        with pytest.raises(StepUpExchangeFailed):
            self._exchange(lambda _: response)(code="c", verifier="v")

    def test_an_unreachable_endpoint_fails_the_exchange(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        with pytest.raises(StepUpExchangeFailed):
            self._exchange(handler)(code="c", verifier="v")


class TestTheRealmClient:
    """Both realms declare the step-up client the API redeems codes for."""

    @pytest.mark.parametrize("name", sorted(REALMS))
    def test_a_public_pkce_client_for_the_callback_alone(self, name: str) -> None:
        realm = json.loads(REALMS[name].read_text(encoding="utf-8"))
        (client,) = [c for c in realm["clients"] if c["clientId"] == STEP_UP_CLIENT_ID]
        assert client["publicClient"] is True and client["standardFlowEnabled"] is True
        assert client["implicitFlowEnabled"] is False
        assert client["directAccessGrantsEnabled"] is False
        assert client["serviceAccountsEnabled"] is False
        assert client["attributes"]["pkce.code.challenge.method"] == "S256"
        assert client["webOrigins"] == []
        assert all(uri.endswith("/step-up/callback") for uri in client["redirectUris"])
        assert not any("*" in uri for uri in client["redirectUris"])

    @pytest.mark.parametrize("name", sorted(REALMS))
    def test_its_claims_are_in_the_id_token_and_nowhere_else(self, name: str) -> None:
        realm = json.loads(REALMS[name].read_text(encoding="utf-8"))
        (client,) = [c for c in realm["clients"] if c["clientId"] == STEP_UP_CLIENT_ID]
        mappers = {m["name"]: m for m in client["protocolMappers"]}
        assert set(mappers) == {"aaguid", "credential_id", "amr"}
        assert mappers["amr"]["protocolMapper"] == "oidc-amr-mapper"
        notes = {
            "aaguid": "intake.webauthn.aaguid",
            "credential_id": "intake.webauthn.credential_id",
        }
        for name_, note in notes.items():
            config = mappers[name_]["config"]
            assert mappers[name_]["protocolMapper"] == "oidc-usersessionmodel-note-mapper"
            assert config["user.session.note"] == note
            assert config["id.token.claim"] == "true"
            # the step-up client's access token is never a console bearer
            assert config["access.token.claim"] == "false"
            assert config["userinfo.token.claim"] == "false"
        assert mappers["amr"]["config"]["id.token.claim"] == "true"
