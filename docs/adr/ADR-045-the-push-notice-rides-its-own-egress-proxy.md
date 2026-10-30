# ADR-045 · The push notice rides its own egress proxy

Status: Accepted, 30 Oct 2026. The number was allocated by the orchestrator for INT-583 (GitHub
#982). This decision amends ADR-042 for a second purpose.

## Context

Owner decision D35 (28 Oct 2026, files/00_STATE.md §3) sends the new-device sign-in notice by
push to the patient's previously signed-in iPhones, never by SMS. INT-583 builds the notice as a
direct call to Apple Push Notification service: `EgressPurpose.PUSH_SECURITY_NOTICE`, a device
token addressed to a patient account, over HTTP/2.

On the synthetic AWS host every network the API sits on is `internal: true`. As things stood,
the API's only ways off the host were two forward proxies:

- `egress-proxy` (ADR-035) carries the hosted-model rows only;
- `sms-egress` (ADR-042) carries the SMS row only.

So the notice had no route there, and every push would fail as `unreachable`. ADR-042 met the
same problem for SMS, and the same two options apply:

- **Give the API a direct route out.** That drops the network half of ADR-025 for every call the
  API makes.
- **Put the push on an existing proxy.** ADR-032 forbids a personal-data call on the shared
  proxy. ADR-042 made `sms-egress` carry only its own purpose, and
  `intake_platform.egress.DEDICATED_PERSONAL_PROXIES` admitted that one pair and nothing else.

## Decision

The push notice, `EgressPurpose.PUSH_SECURITY_NOTICE`, and nothing else, rides a third forward
proxy on the synthetic host: `push-egress`, built to ADR-042's pattern.
`DEDICATED_PERSONAL_PROXIES` maps that purpose to exactly `http://push-egress:3128`. Every other
personal-data proxy arrangement is still refused at construction, as INT-203 requires.

- **Its config.** It renders, from the same `infra/security/egress-allowlist.yaml` the in-process
  guard loads, the `phi_path` tier's `push_security_notice` rows and nothing else
  (`scripts/security/render_push_egress_conf.py`). The rows must be exact hosts on 443.
  - With no such row it admits nothing.
  - That is the shipped state until the owner applies the two APNs rows
    (`owner-583-apns-egress.patch`), which also re-renders the config.
- **Resolution.** It closes the rebinding window itself: no IP or FQDN cache, one-second TTLs,
  no search-domain expansion. It refuses `DENIED_RANGES` at connect.
- **What it sees.** TLS, and HTTP/2 inside it, run end to end through CONNECT. The proxy sees
  `host:443` and no request content: not the device token in the path, not the provider token,
  not the notice. Its log line is `host:port`, a status and byte counts.
- **How it runs.** The same digest-pinned `ubuntu/squid` as the other two, read-only, as uid
  13, with every capability dropped, no published port and a listener healthcheck.
- **Its networks.** `push-out` is internal and shared with the API alone. `push-wan` is its only
  way off the host.
- **How the API uses it.** The API joins `push-out` and names the proxy in
  `INTAKE_PUSH_EGRESS_PROXY_URL`. Only the APNs wiring (`intake_api.push_wiring`) reads that
  variable, and it refuses any other value. On the synthetic host, a missing proxy leaves the
  push channel off with the typed reason `no_route`.

**Three proxies, none carrying another's purpose:**

- The proxies share no network.
- Each inner network is shared with the API alone.
- `PURPOSE_PROXIES` binds each routed purpose to its one proxy, whatever the data class.
- Each proxy's config renders only its own purpose's rows.

## Consequences

**Easier.** The notice can go live on the synthetic host, once the owner's APNs rows and key
exist, without giving the API a general route out.

**Harder.**

- A third generated config has to be kept fresh, and a third registry and inventory row kept
  true.
- The synthetic vendor tripwire was re-cut for a new service and two new networks. This was
  done at the orchestrator's direction, for the legal lane to verify. The push carries a device
  token and constant words, never audio, answers or documents. No text names Apple's push
  service yet; that question is open (`docs/legal/synthetic/documents.yaml`, `aydinlatma.app`).

**Enforced by:**

- `tests/security/test_egress_sms_proxy.py`: the two dedicated pairs exactly, and each routed
  purpose bound to its one proxy.
- `tests/infra/test_staging_push_egress.py`:
  - only Apple's hosts on 443, and nothing without the rows;
  - other purposes never rendered;
  - non-exact or non-443 rows refused;
  - the cache and denied-range directives, and a content-free log;
  - the committed config equal to the render;
  - the service's privileges, its healthcheck, its registry and inventory rows;
  - no other service on `push-out`;
  - the API naming exactly the admitted URL;
  - the three proxies on disjoint networks.
- `tests/api/test_push_wiring.py`: the synthetic host with its proxy wired; without it, or with
  any other proxy, `no_route` and no key read; a production host with no proxy resolving and
  pinning itself.
- `tests/api/test_push_apns.py`: through the proxy the name survives to the CONNECT and the
  policy still decides first; any other proxy is refused at construction.
- `tests/legal/test_synthetic_vendor_tripwire.py`: the re-cut topology and its near misses (the
  push and SMS proxies bridged, probes on `push-out`, the API on `push-wan`).

`observability/registry.yaml` carries `push-egress` (invariant 13): self-hostable, a
`tcp_connect` probe, the squid licence record, and `self_hosted_now: false` until a deploy
carrying this decision runs. `infra/staging/inventory.yaml` places it as `needed: false`
(`fails_closed_without_it`) and `unprobed: outside_probe_networks`. The recorded sweeps and the
admin-console fixtures were re-taken with the shipped recorders.

The production PHI deployment does not inherit this decision. Its push route needs its own
decision when it exists. No `00_STATE.md` row is minted here: the decision to push is the
owner's D35.
