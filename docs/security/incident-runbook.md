# Incident response runbook (INT-020)

The executable skeleton files/10 §7 names at this path: "triage, containment (kill switch →
typed mode, token revocation, key rotation), forensics on immutable logs, KVKK Board
notification within 72 h and data-subject notification, hospital-tenant notification per DPA,
post-incident review with action items tracked as tasks."

Scope honesty: this runbook is the operating skeleton. The notification **content** — the
Board form flow automation, data-subject notice texts, the USOM report format and the
hospital notice texts — is legal machinery that lands with **INT-214** and renders only from
docs/legal/ (CLAUDE.md invariant 18). Nothing in this file is a legal text, and nobody should
improvise one during an incident: the pointers below say who decides and where the machinery
will live.

## Detection sources

Where an incident announces itself (files/10 §7):

- **SIEM/XDR:** Wazuh — failed logins and OTP anomalies per phone/IP/ASN, impossible
  travel, new-device logins, token reuse detections. The tier is
  `infra/docker-compose.siem.yml` (profile `siem`, `make siem`), the rules are
  `infra/security/wazuh/rules/intake_rules.xml`, and what reaches a screen is the
  scrubbed feed in `intake_platform.siem` — **ids, a truncated path and a rule name
  resolved from a committed file, never a log line** (INT-205). It has not been booted:
  HB-I1 and HB-I2 are open, so treat Wazuh as unavailable until they close.
- **Runtime:** Falco alerts (`infra/security/falco/rules/intake_rules.yaml`) and k8s
  audit anomalies (INT-205; the cluster and its audit policy land with INT-201).
- **Edge:** WAF/Coraza and CrowdSec blocks; **egress denials — attempted calls to
  non-allow-listed hosts are a hard alert** (INT-018, INT-203).
- **Application security events:** consent-scope denials (`consent_guard` refusals),
  injection suspicions (`security.injection_suspected`), PolicyGuard spikes (land with
  INT-038, INT-083, INT-102).
- **Integrity:** audit-chain verification failures and `seq` gaps, image-signature and
  protocol-signature failures (INT-016, INT-019, INT-058).
- **Control-plane (group O, files/10 §7):** `device_functions` changes in either direction,
  study-assertion changes and expiry, break-glass rate per actor and out-of-hours grants
  without an open P1, four-eyes self-approval attempts — an intrusion signal (land with
  INT-180…INT-192).
- **Humans:** a patient, clinician, tenant, vendor or researcher telling us. Treat an
  external report as a detection source with its own clock — "learning of it" starts the
  KVKK 72 h countdown (see Notification pointers).

## Severity ladder

Internal targets from files/10 §7: MTTD under 15 min for P1 signals; MTTR under 4 h.

| Sev | Definition | Response |
|---|---|---|
| **SEV1** | Confirmed or presumed PHI exposure; patient-safety impact (missed/blocked RED path); audit-chain integrity failure; active compromise of a privileged account or the control plane | Page now, incident commander assigned, notification clocks assessed immediately |
| **SEV2** | Strong signal without confirmed exposure: egress-denial spike, repeated four-eyes self-approval attempts, pack or image signature failure, break-glass anomaly | Page during on-call hours; SEV1 escalation decided within the first 15 minutes |
| **SEV3** | A degraded control with no evidence of exploitation: backup freshness breach, certificate or rotation countdown expiry, probe failures | Ticket with a dated owner; escalate on any second correlated signal |
| **SEV4** | Hygiene finding (scanner output within SLA, single anomalous login explained) | Track in the normal vulnerability SLA (files/10 §7: critical 72 h / high 7 d / medium 30 d) |

When in doubt between two levels, take the higher one; a downgrade later is free, a late
upgrade is not.

## First 15 minutes

1. **Name an incident commander** (see Roles). One person owns decisions from this moment.
2. **Open the incident record** — timestamped, ids only (see Communications rules). Note who
   detected what, when, and when we *learned* of it — that word starts legal clocks.
3. **Set severity** from the ladder above; page per severity.
4. **Preserve before you contain** where the two conflict for anything forensic: capture the
   current audit-chain head and relevant log windows first (see Evidence preservation) —
   containment that destroys evidence is a last resort, taken knowingly.
5. **Contain in the safe direction.** files/10 §2 gives one-actor authority for every move
   to the safer state — no approver needed at 03:00: kill switch → typed mode, protocol-pack
   quarantine, lane disable, token revocation, `device_functions` off.
6. **Rotate what is plausibly burned:** affected OpenBao leases and tokens, session families,
   connector credentials (key rotation per files/10 §7 containment).
7. **Assess the notification question early:** if personal data may be affected, alert the
   owner/counsel now — the KVKK Board window is 72 h from learning, and the 7545 channel is
   "without delay" (pointers below). Do not draft any notice text; that is INT-214 machinery
   plus counsel.
8. **Start the rolling timeline** in the incident record: every action, every time, every
   actor role.

## Roles

- **Incident commander:** the security owner — founder until a security lead exists
  (files/10 §10). Owns severity, containment decisions, and the timeline.
- **Clinical impact assessor:** the clinical lead. Answers one question continuously: does
  this incident change what any patient should be told or how triage behaves right now?
- **Device change control:** `qms_owner` (files/10 §10) for anything touching the device
  boundary; device-vigilance clocks (files/06 §1 TCY row) are theirs to raise with the
  regulatory consultant.
- **Legal/notification decision:** owner + counsel. The only people who may decide that a
  notification is or is not required, and the only consumers of the INT-214 packet.
- **Tenant liaison:** whoever holds the hospital relationship; executes the DPA notice
  decision (see pointers) but does not draft its content.
- **Scribe:** keeps the timeline while the commander decides. In a two-person company these
  hats stack; the record still names which hat took each action.

## Evidence preservation

- **The audit chain (INT-016) is the spine of the forensic story:** hash-chained,
  append-only, INSERT-only writer, WORM copies (files/10 §3). At incident start, record the
  current chain head and, once it lands, the externally anchored head (inv. 40) in the
  incident record.
- **Work from immutable copies** — forensics on the WORM/object-lock exports and log
  archives, never on the live database (files/10 §7 "forensics on immutable logs").
- **Egress logs are transfer evidence** (files/10 §4): for any suspected exfiltration,
  capture the egress proxy log window (vendor, purpose, bytes) covering the incident span.
- **Do not restart, rotate or delete ahead of capture:** crashed workers, queue contents and
  collector buffers may hold the only trace. Snapshot first where the platform allows.
- **Chain of custody:** every captured artefact gets a hash and a line in the incident
  record — who captured it, from where, when. The hash-chained audit log covers actions
  taken through the system; captures taken beside it must be logged by hand.
- **Clock discipline:** note the time source for every timestamp; regulator-facing
  timelines are reconstructed from these.

## Notification pointers

This section is deliberately pointers, not templates. Legal texts render only from
docs/legal/ (CLAUDE.md invariant 18); the machinery and the texts land with **INT-214**
("Breach machinery: KVKK 72h Board form automation + data-subject notices + USOM report
(7545) + hospital notices"), with the hospital DPA template under INT-213. Counsel decides
applicability in every case.

| Channel | Clock | Basis | Where the machinery lands |
|---|---|---|---|
| KVKK Board | within **72 h** of learning of the breach | Kurul Kararı **2019/10** (files/06 §1 KVKK-12-breach), with the Board's form content | INT-214 |
| Data subjects | without undue delay, after Board form assessment | KVKK m.12 flow per Kurul Kararı 2019/10 | INT-214 |
| USOM / Siber Güvenlik Başkanlığı | **without delay** | Law **7545** (files/06 §1: cyber incidents reported to the Cybersecurity Directorate/USOM channel in addition to KVKK) | INT-214 |
| Hospital tenant (controller) | per the signed **DPA** — breach notice to the controller within 24 h (files/06 §5 DPA clause list) | the tenant DPA | INT-213 (template), INT-214 (flow) |
| Device vigilance (if a device function is implicated) | MDR/TCY timelines per files/06 §1 TCY row | TCY vigilance | INT-216/INT-217 scope |

Operating rule until INT-214 lands: the commander records the trigger time and the
learning time in the incident record, alerts owner + counsel, and counsel drives the
notification by hand against the files/06 obligations. Twice-yearly breach drills
(files/06 §1) and quarterly tabletops (files/10 §7) rehearse exactly this hand-off.

## Communications rules

- **Ids only, never PHI** — in tickets, chat, the incident record, pager payloads, and
  post-incident documents (CLAUDE.md invariant 6). Patient references are pseudonymous ids;
  staff references are roles until the review requires names.
- No screenshots of clinical content into any channel. If reviewing patient content is
  necessary, it goes through the break-glass path with its audit entry and patient
  access-log consequence (files/10 §9 break-glass row), not through a paste.
- External statements (tenants, patients, press, regulators) go only through the owner and
  counsel; nobody else communicates outward about an incident.
- Vendor coordination happens over the contract's named security contact; what we send a
  vendor is subject to the same ids-only rule.

## Post-incident review

- Within 5 working days of closure: a written review — timeline, root cause, what the
  signals did and did not catch, control gaps against the relevant
  docs/security/threat-model.md section.
- **Action items become backlog issues** (files/10 §7: "action items tracked as tasks"),
  each with an owner; a control gap found here updates the threat model section and, where
  it changes files/10's meaning, is raised as a files/10 correction rather than papered over
  locally.
- Feed the drill programme: the next tabletop (quarterly, files/10 §7) replays the incident
  shape; the breach drill (twice a year, files/06 §1) rehearses the notification hand-off.
- If the incident revealed a missing or silent signal, the fix lands in the metrics
  catalogue and alerting (INT-025, INT-021, INT-205) — a metric with nothing attached to it
  is the failure mode files/10 §7 warns about.
