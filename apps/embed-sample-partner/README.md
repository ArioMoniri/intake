# Vizite embed — sample partner app (INT-320 follow-up)

A **synthetic, dev-tier** sample that shows another app embedding Vizite's
_Start pre-visit_ button and launching the branded intake end to end, over the
real signed launch-ticket handshake (ADR-029). It turns the built mechanism
(`packages/embed-sdk`, `services/api` `/embed/v1/*`, `infra/tenants/embed_registry.yaml`)
into something you can run and see.

Nothing here is a real partner. `Örnek Sağlık Portalı` ("Sample Health Portal")
is a made-up name with no real branding; it embeds the synthetic dev tenant
`dev-partner-alpha` from the committed registry. A real partner is a `prod`
registry row and stays refused until a human records its executed DPA and its
brand-use permission — no engineer can supply those (see
`docs/backlog/blockers.md` INT-320 and ADR-029).

## The path this demonstrates

```
  browser (partner page)            partner backend (this app)         Vizite API
  --------------------              --------------------------         ----------
  [ Ön muayeneyi başlat ]  ──POST──▶  POST /vizite/ticket
   @intake/embed-sdk                    handleTicketRequest ──POST──▶  POST /embed/v1/launch-tickets
   (holds NO secret)                    (holds the credential)          (mints a signed ticket)
        ▲                                     │
        └──────── { ticket, launch_url, expires_at } ◀────────┘
        │
   SDK opens launch_url (https only)  ─────────────────────▶  POST /embed/v1/launch  → branded theme + consent set id
                                                              POST /embed/v1/consent → the hash-bound consent to show
```

The button holds no Vizite secret: it calls this app's **own** backend, which is
the only place the credential lives, and it opens **only** an `https` Vizite URL.
The tenant is bound inside the ticket signature, so a ticket can never cross
tenants; the ticket rides in the URL fragment, so it never reaches an access
log; and no clinical or personal value crosses the handshake in either direction.

## App shape

```
apps/embed-sample-partner/
  server.mjs                 runnable Node server (stdlib http + fetch, zero deps)
  public/index.html          the synthetic partner page (import map → the SDK)
  public/styles.css
  src/partnerBackend.ts       the tested core: mint a ticket server-to-server
  src/partnerBackend.test.ts  the fixture-backed proof of the handshake
  src/browser/main.ts         renders the SDK button, wires it to /vizite/ticket
  tsconfig.node.json          → dist/partnerBackend.js  (the server imports this)
  tsconfig.web.json           → dist/web/main.js        (the browser glue)
  tsconfig.vendor.json        → dist/web/vendor/index.js (the SDK, browser-loadable)
```

`build` compiles all three with the repo's own `tsc` — no bundler, no new
dependency. The browser resolves the SDK's bare `@intake/embed-sdk` import
through the import map in `index.html`, which points at the vendored SDK file.

## Run the proof (no infra needed)

The handshake is proven by a fixture-backed test that stands a recorded Vizite
response in for the live endpoint:

```bash
pnpm --filter @intake/embed-sample-partner test
```

It asserts the partner backend calls the real `POST /embed/v1/launch-tickets`
with the bearer credential and a `{tenant_id}` body, returns **only** the three
public launch fields (never the token), fails closed on an upstream refusal or a
malformed body, and — fed to `@intake/embed-sdk` — opens exactly the branded
`https` launch URL. The **server side** of the handshake (mint → launch →
consent over the real FastAPI app, without OpenBao, using the unit-lane signing
key) is proven by `tests/embed/test_router.py`.

## Run the sample against the dev API (a live end-to-end run)

A live run additionally needs infra that this PR does not stand up. These steps
are the **operator's**:

1. **A reachable Vizite dev API with the embed surface configured.** The API
   fails closed (503 on every `/embed` route) unless it is started with a launch
   base URL and an OpenBao-backed signing-key resolver:

   | env (on the Vizite API) | value |
   | --- | --- |
   | `INTAKE_DEV_TOKEN_ADMIN` | the admin bearer (the partner-backend credential, dev tier) |
   | `INTAKE_DEV_TOKEN_PATIENT` | the patient bearer (the rest of the dev tier) |
   | `INTAKE_EMBED_LAUNCH_URL` | `https://…/embed/launch` — must be `https`, or the SDK refuses to open it |
   | `INTAKE_EMBED_REGISTRY` | optional; defaults to the committed `infra/tenants/embed_registry.yaml` |
   | `OPENBAO_ADDR`, `OPENBAO_TOKEN` | the dev OpenBao pointer |
   | `INTAKE_LEGAL_ROOT` | for the consent step (see note 3) |

   Docker is banned locally, so this runs against a **separately-running** dev
   API and dev OpenBao, not a local `make dev` compose stack.

2. **Seed the dev signing key into that dev OpenBao** (the mint fails closed with
   `503 embed_signing_key_unavailable` until you do):

   ```bash
   python scripts/dev/seed_embed_dev_key.py
   ```

   It needs the dev OpenBao reachable (`OPENBAO_ADDR` + `OPENBAO_TOKEN`), refuses
   to run against `INTAKE_ENV=prod`, and never prints the key. This is the
   operator's step because it writes a secret to a running secrets store.

3. **The consent step.** `POST /embed/v1/consent` renders from Vizite's own
   `docs/legal`-bound flow and fails closed until the texts exist. The
   counsel-vetted tenant consent tree is a human blocker (HB-L27, via INT-210);
   for local dev the API reads dev-only sample texts from its dev legal tree
   (`INTAKE_LEGAL_ROOT`). `device_functions` stays off for this tenant (ADR-020).
   Authoring or enabling consent copy is not an engineering step.

4. **Start the sample and open it:**

   ```bash
   VIZITE_ADMIN_TOKEN="$INTAKE_DEV_TOKEN_ADMIN" \
   VIZITE_API_BASE="http://127.0.0.1:8000" \
   pnpm --filter @intake/embed-sample-partner dev
   # → http://localhost:4123  — click “Ön muayeneyi başlat”
   ```

   | env (on this sample app) | default | meaning |
   | --- | --- | --- |
   | `PARTNER_PORT` | `4123` | where this sample listens |
   | `VIZITE_API_BASE` | `http://127.0.0.1:8000` | the dev Vizite API base |
   | `VIZITE_ADMIN_TOKEN` | _(empty)_ | the admin bearer; without it a tap returns `500 partner_backend_unconfigured` |
   | `EMBED_TENANT_ID` | `0b6f9d2e-1111-5aaa-8bbb-000000000001` | the `dev-partner-alpha` row |

Until the API + OpenBao are up and the key is seeded, the page loads and a tap
surfaces the fail-closed state (e.g. "partner backend refused the launch") —
which is the honest behaviour, not an error in the sample.

## What stays out of scope

A partner-supplied patient identifier — the correlation that would let a note
flow back to a specific partner record — is deliberately **not** part of this
handshake: it is a new personal-data category and a new recipient relationship
that needs human sign-off (ADR-029, `docs/backlog/blockers.md` INT-320). Anything
that needs a real DPA or brand permission is a stop-and-flag, fail closed.
