"""INT-420 — the identifiers the rename touches change together.

Acceptance (GitHub #712): "Identifier changes (bundle id, URL scheme, Keycloak
redirect URIs, deep links) change together and are tested."

What each identifier did, and the test that holds it there:

* **URL scheme.** The app registers ``onvizit`` first and keeps ``intake``, so
  a link issued with the old scheme still opens the app (read old, write new).
  Every custom-scheme redirect URI in a committed Keycloak realm must be one of
  those schemes. Today no realm client redirects into the app (``admin-web``
  uses http only), so the check is proven on a planted client as well.
* **Bundle id.** Unchanged, on purpose: ``com.ariomoniri.intakemobile`` is the
  App Store Connect record, and services/api's App Attest verifier and its test
  kit pin the same value. app.json now declares it, as the owner's rebrand did.
* **Push title.** A reminder's title is the app's own name and nothing else
  (notifications/catalogue.py), so it must equal app.json's name.
* **Embed.** The SDK's button attribute, the sample partner's stylesheet, its
  ticket route and its env-var names are one identifier each, spelled in
  several files; each pair is read back from both sides.

Nothing persisted carried the old name: no storage key, DB column, metric or
migration did (the repo-wide guard in test_brand_name.py proves the tree is
clean), so no read-old/write-new migration exists beyond the scheme.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest
from intake_api.settings import IOS_BUNDLE_ID
from intake_platform.notifications.catalogue import TEMPLATES, Locale

REPO = Path(__file__).resolve().parents[2]
MOBILE = REPO / "apps" / "mobile"
SAMPLE = REPO / "apps" / "embed-sample-partner"
SDK = REPO / "packages" / "embed-sdk" / "src" / "index.ts"

NEW_BRAND = "Önvizit"
NEW_ASCII = "onvizit"
LEGACY_SCHEME = "intake"
WEB_SCHEMES = frozenset({"http", "https"})


def _app() -> dict[str, Any]:
    expo = json.loads((MOBILE / "app.json").read_text(encoding="utf-8"))["expo"]
    assert isinstance(expo, dict)
    return expo


def app_schemes() -> tuple[str, ...]:
    scheme = _app()["scheme"]
    return (scheme,) if isinstance(scheme, str) else tuple(scheme)


# --- URL scheme <-> Keycloak redirect URIs -------------------------------------------


def _realm_files() -> list[Path]:
    out = subprocess.run(  # noqa: S603 — fixed argv, no shell
        ["git", "ls-files", "-z"],  # noqa: S607 — git on PATH, as every repo gate
        cwd=REPO,
        capture_output=True,
        check=True,
    ).stdout
    paths = [p.decode("utf-8") for p in out.split(b"\0") if p]
    realms = []
    for rel in paths:
        if not rel.endswith(".json") or "keycloak" not in rel.lower():
            continue
        data = json.loads((REPO / rel).read_text(encoding="utf-8"))
        if isinstance(data, dict) and "clients" in data:
            realms.append(REPO / rel)
    return realms


def redirect_uris(realm: Mapping[str, Any]) -> Iterator[tuple[str, str]]:
    """(clientId, uri) for every redirect and post-logout redirect in a realm."""
    for client in realm.get("clients", []):
        cid = str(client.get("clientId", "?"))
        for uri in client.get("redirectUris", []):
            yield cid, str(uri)
        post_logout = client.get("attributes", {}).get("post.logout.redirect.uris", "")
        for uri in str(post_logout).split("##"):
            if uri and uri != "+":
                yield cid, uri


def foreign_redirects(realm: Mapping[str, Any], schemes: Iterable[str]) -> list[tuple[str, str]]:
    """Redirects that neither use the web nor a scheme the app registers."""
    allowed = WEB_SCHEMES | set(schemes)
    out = []
    for cid, uri in redirect_uris(realm):
        scheme = uri.split(":", 1)[0].lower() if ":" in uri else ""
        if scheme not in allowed:
            out.append((cid, uri))
    return out


def test_the_app_registers_the_new_scheme_first_and_keeps_the_old_one() -> None:
    assert app_schemes() == (NEW_ASCII, LEGACY_SCHEME)


def test_every_keycloak_redirect_lands_on_the_web_or_on_a_scheme_the_app_registers() -> None:
    realms = _realm_files()
    assert {p.relative_to(REPO).as_posix() for p in realms} >= {
        "infra/keycloak/dev-realm.json",
    }, "the realm export moved; the scheme check would be vacuous"
    for path in realms:
        realm = json.loads(path.read_text(encoding="utf-8"))
        assert list(redirect_uris(realm)), f"{path} has no redirect at all"
        assert foreign_redirects(realm, app_schemes()) == [], path


def test_a_planted_client_redirecting_to_an_unregistered_scheme_is_caught() -> None:
    old_scheme = "vizit" + "e"  # derived: the guard must not spell the old name
    realm = {
        "clients": [
            {"clientId": "admin-web", "redirectUris": ["http://localhost:3000/*"]},
            {
                "clientId": "mobile",
                "redirectUris": [f"{NEW_ASCII}://auth", f"{old_scheme}://auth"],
                "attributes": {"post.logout.redirect.uris": f"{LEGACY_SCHEME}://out##+"},
            },
        ]
    }
    assert foreign_redirects(realm, app_schemes()) == [("mobile", f"{old_scheme}://auth")]
    assert foreign_redirects(realm, (NEW_ASCII,)) == [
        ("mobile", f"{old_scheme}://auth"),
        ("mobile", f"{LEGACY_SCHEME}://out"),
    ]


# --- bundle id --------------------------------------------------------------------


def test_the_bundle_id_is_the_one_app_attest_verifies() -> None:
    assert _app()["ios"]["bundleIdentifier"] == IOS_BUNDLE_ID == "com.ariomoniri.intakemobile"
    testkit = (REPO / "tests" / "api" / "app_attest_testkit.py").read_text(encoding="utf-8")
    assert f'BUNDLE_ID = "{IOS_BUNDLE_ID}"' in testkit


# --- the push title is the app's name ----------------------------------------------


def test_every_reminder_title_is_the_app_name() -> None:
    assert _app()["name"] == NEW_BRAND
    for kind, template in TEMPLATES.items():
        for locale in Locale:
            assert template.title[locale] == _app()["name"], (kind, locale)


# --- embed: each identifier read back from both of its sides ------------------------


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _kebab(camel: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "-", camel).lower()


def test_the_sdk_button_attribute_is_the_one_the_sample_partner_styles() -> None:
    keys = re.findall(r'button\.dataset\["(\w+)"\]', _read(SDK))
    assert len(keys) == 1, keys
    attribute = f"data-{_kebab(keys[0])}"
    assert attribute == f"data-{NEW_ASCII}-embed"
    css = _read(SAMPLE / "public" / "styles.css")
    selectors = set(re.findall(r"button\[(data-[\w-]+)\]", css))
    assert selectors == {attribute}


def _string_constant(source: str, name: str) -> str:
    match = re.search(rf'\b{name}\s*=\s*"([^"]+)"', source)
    assert match, f"{name} not found"
    return match.group(1)


def test_the_ticket_route_is_one_path_on_page_server_and_readme() -> None:
    page = _string_constant(_read(SAMPLE / "src" / "browser" / "main.ts"), "TICKET_ENDPOINT")
    server = _string_constant(_read(SAMPLE / "server.mjs"), "TICKET_ROUTE")
    assert page == server == f"/{NEW_ASCII}/ticket"
    assert f"POST {page}" in _read(SAMPLE / "README.md")


def test_the_env_names_are_the_same_on_server_backend_and_readme() -> None:
    server_env = set(re.findall(r"process\.env\.([A-Z0-9_]+)", _read(SAMPLE / "server.mjs")))
    branded = {name for name in server_env if name.startswith(f"{NEW_ASCII.upper()}_")}
    assert branded == {f"{NEW_ASCII.upper()}_API_BASE", f"{NEW_ASCII.upper()}_ADMIN_TOKEN"}
    backend = _read(SAMPLE / "src" / "partnerBackend.ts")
    assert f"set {NEW_ASCII.upper()}_ADMIN_TOKEN" in backend
    readme = _read(SAMPLE / "README.md")
    for name in branded:
        assert f"`{name}`" in readme, name


@pytest.mark.parametrize(
    "path",
    [
        SAMPLE / "package.json",
        SAMPLE / "public" / "index.html",
    ],
    ids=lambda p: p.relative_to(REPO).as_posix(),
)
def test_the_sample_partner_describes_the_product_as_the_new_brand(path: Path) -> None:
    assert NEW_BRAND in _read(path)
