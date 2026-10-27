# ADR-042 · The SMS vendor rides its own egress proxy on the synthetic host

Status: Accepted, 16 Oct 2026 (route decision relayed by the orchestrator for INT-528, GitHub #895; amends ADR-032 for one purpose)

## Context

The owner chose Netgsm's OTP SMS product as the SMS vendor (INT-358, 16 Oct 2026), and INT-528
wires it behind the INT-329 port. On the synthetic AWS host every network the API sits on is
`internal: true`, so the API has no route to `api.netgsm.com.tr` at all, and the OTP tier would
fail closed forever. Two routes were possible, and both had a cost:

- **Give the API a direct route out** (a non-internal network). This throws away the network-tier
  half of ADR-025's "one list, two enforcers" for every call the API makes, not only the SMS call.
- **Send the call through a forward proxy.** INT-203 forbids exactly this (ADR-032): a
  personal-data transport that names a proxy is refused at construction.

ADR-032 gave two reasons for that refusal:

1. Behind the shared proxy neither enforcement point resolves the destination.
2. That proxy's allow-list carries no personal-data row, so routing personal data through it
   loses the in-process pin and gains nothing.

#774's shared proxy keeps both reasons true: it renders only the `hosted_model_inference` rows.

## Decision

The OTP tier's SMS call, `EgressPurpose.SMS_OTP_DELIVERY`, and nothing else, rides a dedicated
forward proxy, `sms-egress`, on the synthetic host. `intake_platform.egress.DEDICATED_PERSONAL_PROXIES`
maps that one purpose to that one URL, `http://sms-egress:3128`, matched exactly. Every other
personal-data proxy arrangement is still refused at construction, as INT-203 requires.

The proxy is built so that ADR-032's two reasons no longer hold:

1. **It renders the one row it carries.** It renders, from the same `infra/security/egress-allowlist.yaml`
   the in-process guard loads, the `phi_path` tier's `sms_otp_delivery` rows and nothing else
   (`scripts/security/render_sms_egress_conf.py`). The rows must be exact hosts on 443.
2. **It resolves at connect, safely.** It closes the rebinding window itself, as ADR-032
   prescribes: no IP or FQDN cache, one-second TTLs, no search-domain expansion. It refuses
   `DENIED_RANGES` at connect.

The in-process allow-list, purpose, data-class and runtime-gate checks still decide before the
proxy is asked. The hostname reaches the CONNECT line, so TLS runs end to end and the proxy sees no
request content. Its log line is `host:port`, a status and byte counts.

The deployment around it:

- `sms-egress` runs the digest-pinned `ubuntu/squid` image that the shared proxy already pins. It
  runs read-only, as uid 13, with every capability dropped and no published port.
- It sits on two networks: `sms-out`, which is internal and shared with the API alone, and
  `sms-wan`, its only way off the host.
- The API joins `sms-out` and names the proxy in `INTAKE_SMS_EGRESS_PROXY_URL`. Only the Netgsm
  wiring reads that variable, and it refuses any other value.

**Two proxies, neither carrying the other's purpose.** INT-442 (#774) put the shared proxy on
the same host as `egress-proxy`, on its own `outbound` and `vendor` networks. The two coexist:

- the API sits on `outbound` and `sms-out`, and nothing else shares either;
- the two proxies share no network;
- `intake_platform.egress.PURPOSE_PROXIES` binds each routed purpose to its one proxy, whatever
  the data class: the SMS call only `sms-egress`, a hosted-model call only `egress-proxy`. The
  SMS proxy carries no other purpose at all, even a non-personal one;
- at the network, each proxy's config is rendered from its own purpose's rows, so neither admits
  the other's host.

## Consequences

**Easier.** SMS can go live on the synthetic host without giving the API a general route out.
Every other call the API makes stays in-process resolve-and-pin with no network route at all.

**Harder.** A second proxy config now has to be kept fresh. `tests/infra/test_staging_sms_egress.py`
holds the committed config equal to what the allow-list renders, and the owner's egress patch
re-renders it when the SMS row lands.

**Enforced by:**

- `tests/security/test_egress_sms_proxy.py`: the one admitted pair; every near miss refused (the
  shared proxy, another port, scheme or lookalike host, another purpose, a pseudonymous call); the
  in-process checks still running behind it; each routed purpose bound to its own proxy, and the
  SMS proxy refusing every other purpose in every data class.
- `tests/infra/test_staging_sms_egress.py`: only the SMS host on 443; nothing without the row;
  other purposes never rendered; cache and denied-range directives; a content-free log; the
  service's privileges; no other service on `sms-out`; the API naming exactly the admitted URL;
  the two proxies on disjoint networks, each rendering only its own purpose's host.

`observability/registry.yaml` carries `sms-egress` (invariant 13): self-hostable, a
`tcp_connect` probe, the squid licence record, and `self_hosted_now: false` until a deploy carrying
this decision runs. The recorded probe sweep was re-taken with the shipped recorder to include it
(INT-528 evidence). The production PHI deployment does not inherit this decision. It is in-country and self-hosted (D11), and its SMS route needs its own
decision when it exists.

No `00_STATE.md` row is minted here. The vendor decision itself is the owner's INT-358.
