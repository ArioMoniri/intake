# COUNSEL BRIEF — engineering factual annex for INT-210

> **This is not a legal document and it is not for publication.** It contains no
> aydınlatma metni, no açık rıza wording, no privacy policy and no terms. It is an
> annex of facts, written by engineering, so that the Turkish consent texts (INT-210)
> can be drafted against **what the software actually does** rather than against a
> description written from memory. Every factual line below cites the file and line it
> came from. Where the code says `awaiting-human`, this brief says `awaiting-human`
> rather than filling the cell in.
>
> Drafting the patient-facing Turkish copy is INT-210 and it is human legal work.
> Nothing in this file may be copied into a consent text.

Prepared under INT-245. Repository state: branch `int-245-counsel-annex`, off `main` at
`1815fa3`. Date of the survey: 29 Aug 2026.

---

## 0 · How to read this brief

Three vocabularies meet here and they are not interchangeable:

| term | where it is defined | what it means |
|---|---|---|
| **purpose** | `packages/intake_platform/src/intake_platform/consent/registry.py:89-121` | one of eleven closed ids; the unit a consent text is written for |
| **scope** | `registry.py:131-146` | the string a route or a grant carries. Every purpose id is a scope except `share`, which is only ever grantable as `share:<qualifier>` |
| **inventory annotation** | `packages/intake_platform/src/intake_platform/db/inventory.py:24` | the per-column `{category, purpose, basis, retention, recipients}` tuple invariant 18 requires. Its `purpose` field is prose describing the column, **not** a consent-purpose id — the two do not share a namespace |

That last row matters for reading §2: the database's `purpose` annotations describe
columns, and the mapping from a consent purpose to the tables it reaches is made below
from the route guards, not from the annotations.

---

## 1 · The file contract

### 1.1 Where the files go

One file per purpose. The filename is the purpose id with every `:` replaced by `.`,
plus the suffix `.tr.md`:

```python
def text_filename(purpose_id: str) -> str:
    """``lane:affect`` → ``lane.affect.tr.md`` — Turkish-first (invariant 5),
    colon-free for the filesystem."""
    return purpose_id.replace(":", ".") + ".tr.md"
```
— `packages/intake_platform/src/intake_platform/consent/texts.py:81-84`

The directory is a constructor argument (`ConsentTextCatalog(root)`,
`texts.py:117-118`). The value the API actually runs with is:

```python
legal_root: Path = field(default_factory=lambda: Path("docs/legal/consents"))
```
— `services/api/src/intake_api/settings.py:60`

**Flag for counsel and for the owner, stated rather than resolved here.** files/06 §2
(`files/06_COMPLIANCE_TR.md:85`) says texts "live only in `docs/legal/`", and the
loader's own docstring says the same (`texts.py:5-7`). The running default is one level
deeper, at `docs/legal/consents/`. The eleven files must go **where the running code
looks**, which today is `docs/legal/consents/`. This is an engineering discrepancy to
settle before INT-210 lands (either move the default up or amend files/06); it is not a
legal question, and it is recorded here only so the texts are not authored into a
directory nothing reads.

### 1.2 What is inside each file

The loader's format contract, stated in its own words:

> the file starts with a front-matter block `---` / `consent_text_version: <token>` /
> `---` followed by non-empty Turkish copy.
— `texts.py:19-25`

Mechanically (`texts.py:87-109`):

1. line 1 must be exactly `---`;
2. within the next nine lines a line matching
   `^consent_text_version:\s*([A-Za-z0-9][A-Za-z0-9._-]{0,63})\s*$` must appear
   (`texts.py:47-50`), and a closing `---` must appear;
3. everything after the closing `---` is the body, and it must not be blank.

Any of those failing is `ConsentTextInvalidError`, on both the strict and the tolerant
lookup (`texts.py:63-66`, `texts.py:144-151`). A **missing** file is
`ConsentTextMissingError`; an **invalid** one is never treated as merely absent.

### 1.3 The hash covers the whole file

```text
text_hash=hashlib.sha256(raw).hexdigest(),
```
— `texts.py:139`, over `raw = path.read_bytes()` (`texts.py:129`).

The consequence is written into the loader docstring: "the hash covers the ENTIRE file
(front matter included), so a version edit alone re-binds too: version and hash can
never drift apart" (`texts.py:16-17`).

Every grant stores that hash (`consents.text_hash`,
`packages/intake_platform/src/intake_platform/db/models.py:477-489`) and the guard
compares it to the hash of the file **as it stands right now** on every check:

- live grant, hash matches current file → `granted`
- live grant, hash no longer matches → `stale`, treated as absent, patient re-prompted
- live grant, no canonical text exists yet → `unbound`, honoured
— `packages/intake_platform/src/intake_platform/consent/service.py:121-149`

**So: any edit to any of the eleven files — a typo fix, a comma, a version bump —
invalidates every prior grant of that purpose and re-prompts every patient who holds
one.** This is deliberate (files/06 §2, `files/06_COMPLIANCE_TR.md:85`: "the UI renders
from source so what was shown is provable"). Counsel should treat each file as a
release artefact, not a wiki page.

A grant is also refused if the text moved between the moment the client displayed it
and the moment it submitted (`services/api/src/intake_api/consents.py:256-283`, HTTP
409 `consent_text_changed`).

### 1.4 The eleven purposes and their filenames

Ids exactly as `registry.py:89-121` holds them, in registry order. Filenames as
`text_filename()` produces them, under `docs/legal/consents/`:

| # | purpose id | filename | exists today |
|---|---|---|---|
| 1 | `core` | `core.tr.md` | no |
| 2 | `voice` | `voice.tr.md` | no |
| 3 | `wellbeing` | `wellbeing.tr.md` | no |
| 4 | `lane:affect` | `lane.affect.tr.md` | no |
| 5 | `lane:linguistic` | `lane.linguistic.tr.md` | no |
| 6 | `documents` | `documents.tr.md` | no |
| 7 | `learning:personal` | `learning.personal.tr.md` | no |
| 8 | `learning:service_improvement` | `learning.service_improvement.tr.md` | no |
| 9 | `satisfaction` | `satisfaction.tr.md` | no |
| 10 | `share` | `share.tr.md` | no |
| 11 | `research` | `research.tr.md` | no |

`share` is the family text: a `share:<qualifier>` scope resolves to the `share` row
(`registry.py:144-145`) and therefore binds to `share.tr.md`. The share's parameters —
recipient, visit, sections, expiry — live on the grant row, not in the copy
(`texts.py:23-25`).

`lane:acoustic` is **not** on this list and must not be given one. It is rejected by
name (`registry.py:53`, `registry.py:139-140`) because files/06 §2.4
(`files/06_COMPLIANCE_TR.md:104-105`) turned it into an investigational-device informed
consent form under TCKAY. An ICF is a different artefact with a different process; it
is not a `{version, text_hash}` row and it does not belong in `docs/legal/consents/`.

### 1.5 What files/06 §2.1 already requires of the lane texts

Not drafted here, recorded as a constraint the drafter is bound by
(`files/06_COMPLIANCE_TR.md:89-94`): every lane consent must state five things in this
order — purpose; vendor by legal name and country; whether audio or only text leaves
Türkiye; retention; how to withdraw. See §2.2 below for what the code says the truthful
answer to the second and third of those is today.

---

## 2 · Per-purpose factual sheets

Each sheet answers the same nine questions. "Basis the code claims" is the
`LegalBasis` on the registry row (`registry.py:61-71`) plus, where the purpose reaches
persisted columns, the `basis` string in those columns' inventory annotations
(`db/inventory.py:73-83`). Retention classes are named from
`packages/intake_platform/src/intake_platform/retention/retention_policy.yaml`, whose
own source is files/06 §3 (`files/06_COMPLIANCE_TR.md:107-108`).

The three route-enforced scopes today are `core`, `documents` and `share:previsit_note`
(`services/api/src/intake_api/visits.py:33`, `notes.py:37`, `documents.py:66`). The
other eight purposes are recorded in the ledger and rendered in the app, but no server
route yet refuses on them — that is a fact about build state, not about the law, and it
is stated on each sheet rather than glossed.

---

### 2.1 `core` — `core.tr.md`

**What the software does.** Creates and reads the patient's visits, runs the intake
session, stores the protocol slot values it captured and assembles the pre-visit note.
Enforced on `GET /v1/visits`, `POST /v1/visits`, `GET /v1/visits/{id}`
(`visits.py:64,100,134`) and on the note routes (`notes.py:73,125`).

**Tables and fields.**

| table | fields | inventory category |
|---|---|---|
| `patients` | `id`, `tenant_id`, `pseudonym` | `pseudonymised_identity` for `pseudonym` (`models.py:235-246`); the rest `operational_metadata` |
| `sessions` | `protocol_id`, `status` are `special_category_health` (`models.py:267-306`); `protocol_version`, `started_at`, `completed_at`, ids are operational |
| `slots` | `slot_id` and `value` are `special_category_health` (`models.py:350-390`); `value` carries an `EncryptedField` envelope when the classification column marks it sensitive (the column is named in `models.py:350-390`) |
| `notes` | `payload` is `special_category_health`, always envelope-encrypted (`models.py:423-434`) |

No name, TCKN, phone or address column exists in any of these tables; the raw
identifier lives only in `identity_vault` behind the tokenization role
(`models.py:4-7`).

**Basis the code claims.** Registry: `explicit_consent` (`registry.py:93`). Columns:
`KVKK m.6 — special-category health data under açık rıza per consent scope` for the
health columns, `KVKK m.5/2-c — processing necessary for the service contract` for the
operational ones (`db/inventory.py:73-74`).

**Retention.** `life of the record; patient-deletable, 30-day grace, then crypto-shred`
(`db/inventory.py:87`), retention class `clinical_record`, `kind: life_of_record`,
`action: crypto_shred`, `destruction_path: dsar_only`, `dsar_erasable: true`, status
`sourced` from files/06 §3 (`retention_policy.yaml:86-99`).

**Recipients.** `internal services only` for operational columns; `tenant clinicians via
a consented share` for the health columns; `the patient (own record) and tenant
clinicians via consented share` for `notes.payload` (`db/inventory.py:106-108`).

**Required or optional.** It is itself an açık rıza purpose — `default_granted=False`,
basis `explicit_consent` (`registry.py:93`) — but the service does not exist without it.
The mobile UI classifies it `ui: "info"`, "shown as information, never a switch"
(`apps/mobile/src/lib/consent/purposes.ts:62-73`, and the classification comment at
`purposes.ts:15-17`). INT-038's acceptance forbids gating core on any optional purpose
(`docs/backlog/issues.yaml:387`).

**Withdrawal cascade.** `dependents_of("core")` returns **every other purpose**
(`registry.py:156-157`), and core withdrawal additionally revokes every live share
(`service.py:280-283`, `service.py:300-305`). Cascade completes in the same evaluation
pass; the crash-recovery sweep bounds the end-to-end at ≤ 1 min (`service.py:18-27`).

**What the patient observably loses.** Everything. Visits, notes, documents and shares
all 403; every other purpose falls with it.

---

### 2.2 `voice` — `voice.tr.md`

**What the software does.** Runs the spoken intake (`services/voice-runtime`, the
Talker). **No audio is written anywhere** — not to disk, DB, object store or logs
(CLAUDE.md invariant 3), and the retention matrix carries `raw_audio: never_written` as
a positive row rather than as an absence (`retention_policy.yaml:59-64`). Lane windows
are memory-only and zeroed on six named triggers, one of which is consent withdrawal
(`retention_policy.yaml:65-80`).

**Tables and fields.** **None.** `voice` creates no row of its own. What the patient
says lands in `slots` and `notes` under `core`. This is worth stating to counsel
plainly: the `voice` consent is a consent to a *modality*, not to a data store.

**Basis the code claims.** `explicit_consent` (`registry.py:97-101`). No column carries
a `voice`-specific annotation, because no column is created by it.

**Retention.** No retention class exists and none may be added: the policy loader
refuses any class whose name matches an audio pattern
(`retention/policy.py:59-62`, `retention_policy.yaml:17-22`).

**Recipients — the fact files/06 §2.1 requires and the answer the code gives today.**
The PHI-path egress allow-list is empty:

```yaml
  phi_path: []
```
— `infra/security/egress-allowlist.yaml:96`, with the comment at lines 89-95: "there is
NO vendor host a PHI-path service may reach and this list stays empty."

So, as the system stands: **no third-party vendor receives audio, and no audio (nor
text) leaves Türkiye on the PHI path.** Adding a row requires a recorded human decision
plus `INTAKE_ALLOW_PHI_EGRESS=explicit-yes` at runtime. CLAUDE.md invariant 19 and
files/10 §9.1 inv. 25 (`consent_vendor_parity`) hold the consent text and this file in
agreement in CI — meaning **whatever vendor sentence counsel writes will be
machine-checked against this file**, and a text naming a vendor that is not on the list
will fail the build.

**Required or optional.** Optional, `default_granted=False`.

**Withdrawal cascade.** `cascade_children=("lane:affect",)` (`registry.py:100`) —
withdrawing `voice` withdraws `lane:affect` because the affect lane rides the voice
stream (files/06 §2.1). `lane:linguistic` is deliberately **not** a child
(`registry.py:104-106`).

**What the patient observably loses.** The spoken intake. The `typed` profile remains —
there are exactly two production profiles, `residency_tr` and `typed`
(CLAUDE.md invariant 19) — so the patient can still complete an intake by typing.

---

### 2.3 `wellbeing` — `wellbeing.tr.md`

**What the software does.** Delivers validated screening instruments. What actually
compiles today, from the licence registry
(`packages/protocols/src/protocols/licences.py:38-46`): **PHQ-9, PHQ-2, GAD-7, GAD-2 are
`GO`; C-SSRS and WHO-5 are `BLOCKED`** and a pack referencing a non-`GO` instrument
fails the build (`packages/protocols/src/protocols/validator.py:483-491`). The base pack
records that C-SSRS is not referenced at all and WHO-5 is likewise absent
(`packages/protocols/base/intake.yaml:589-601`).

Two claim constraints counsel must not accidentally cross, from CLAUDE.md's clinical
content rules: PHQ-2/GAD-2 have **no Turkish validation at all** and must not be
described as "Turkish-validated"; the PHQ-9 Turkish evidence is a reliability study
only. Invariant 20 forbids any performance figure of the four kinds it names, in
`docs/legal/`, and a CI text gate scans this tree for performance-claim patterns.

**Tables and fields.** No dedicated table. Instrument answers land in `slots`
(`models.py:332-391`) and are summarised into `notes.payload`.

**Basis the code claims.** `explicit_consent` (`registry.py:102`); the columns it
reaches carry `KVKK m.6 … açık rıza per consent scope`.

**Retention.** `clinical_record` (as §2.1).

**Recipients.** `tenant clinicians via a consented share`; the patient's own record.

**Required or optional.** Optional, off by default.

**Withdrawal cascade.** None — `cascade_children` is empty (`registry.py:102`).

**What the patient observably loses.** The Wellbeing tab disappears from the app. It is
the single consent-gated tab:

```ts
export function visibleTabs(consents: ConsentState | null): TabId[] {
  const base: TabId[] = ["today", "visits", "records"];
  if (consents?.wellbeing) { base.push("wellbeing"); }
```
— `apps/mobile/src/lib/session.tsx:225-229`

---

### 2.4 `lane:affect` — `lane.affect.tr.md`

**What the software does.** Infers emotional state from the *sound* of the voice, not
only from the words (files/06 §2.1, `files/06_COMPLIANCE_TR.md:93`). It is read-only:
the lane writes `ObserverState` and never a slot, never a triage level, and never sits
on the speech critical path (CLAUDE.md invariant 11). The only thing that crosses the
module boundary is a closed six-field `InteractionState` record — no emotion label, no
confidence score, no numeric affect value, no free text
(`files/06_COMPLIANCE_TR.md:26`).

**Build state, stated honestly.** `services/voice-runtime/src/intake_voice_runtime/`
contains `talker/` and no `observers/` directory. The lane is specified and typed
(`packages/clinical-schemas/src/clinical_schemas/observers.py`) but not built. Counsel
is drafting for a function that will exist; the description above is the design as
committed, not as running.

**Tables and fields.** None. Lane windows are memory-only
(`retention_policy.yaml:65-80`).

**Basis the code claims.** `explicit_consent` (`registry.py:103`).

**Retention.** No persisted class. Zeroization triggers include `consent_withdrawal`
(`retention_policy.yaml:70-76`).

**Recipients.** Not the clinician as an assessment. files/06 §2.1 requires the text to
say it "is not a diagnosis and is not shared with the doctor as an assessment", and the
clinician note's `affect_summary` sentence was **deleted** in favour of an objective
"Konuşma özellikleri" block of measured speech parameters
(`files/06_COMPLIANCE_TR.md:28`).

**Required or optional.** Optional, off by default.

**Withdrawal cascade.** No children of its own; it is a **child of `voice`** and falls
with it (`registry.py:100`). Mid-session withdrawal is effective ≤ 1 s at the lane
boundary; already-emitted `LaneSignal` events are tombstoned, not deleted, because
deleting one breaks the audit hash chain (`files/06_COMPLIANCE_TR.md:96-97`). Engine
decisions already taken are annotated in the note as derived from a since-withdrawn
signal, not retroactively undone (`files/06_COMPLIANCE_TR.md:99`).

**What the patient observably loses.** Pace and format adaptation during the
conversation. Nothing clinical.

**One drafting constraint counsel is already bound by.** files/06 §10
(`files/06_COMPLIANCE_TR.md:143`): although the EU AI Act is territorially out of scope
today, the instruction is to write the `lane:affect` consent to the **Art. 50(3)
transparency standard now** — it costs one sentence and avoids reopening every consent
artefact at CE time.

---

### 2.5 `lane:linguistic` — `lane.linguistic.tr.md`

**What the software does.** Text-only linguistic analysis of what the patient typed or
said (files/06 §2.1). Same read-only observer contract as §2.4; same build state (not
yet built).

**Tables and fields.** None.

**Basis the code claims.** `explicit_consent` (`registry.py:106`).

**Retention.** No persisted class.

**Recipients.** Internal only.

**Required or optional.** Optional, off by default.

**Withdrawal cascade.** None, and — deliberately — it is **not** a child of `voice`:

```text
    # lane:linguistic is text-only (files/06 §2.1) — deliberately NOT a child
    # of voice; it stands and falls with core alone.
    PurposeDef(id="lane:linguistic", legal_basis=_OPTIONAL, default_granted=False),
```
— `registry.py:104-106`

**The carve-out that must be disclosed inside this text and nowhere else.** files/06
§2.1 (`files/06_COMPLIANCE_TR.md:94`): certain phrases about self-harm trigger a fixed
safety response **regardless of this choice**. The file states the reasoning as a rule
for the drafter: "The honest place to disclose an exception is the consent that does not
cover it — not a paragraph elsewhere in a policy document."

**What the patient observably loses.** Linguistic adaptation. The crisis signposting
continues either way.

---

### 2.6 `documents` — `documents.tr.md`

**What the software does.** Accepts patient-supplied documents (lab reports,
prescriptions, discharge summaries), scans them, stores them in the object store and
parses them into structured items **for the patient's own confirmation**. Enforced on
four routes: upload init (`documents.py:260`), list (`documents.py:313`), content ingest
`PUT /{doc_id}/content` (`documents.py:341-347`) and download (`documents.py:432`).

The intended-purpose wording here is load-bearing and counsel should treat it as such.
files/06 §0.6 files the module as *"to parse patient-supplied documents into structured
items for the patient's own confirmation"*
(`files/06_COMPLIANCE_TR.md:21`), and §0.3 records that MDCG 2019-11 Rev.1 closed the
"simple search" safe harbour for NLP by name, so *"to identify abnormal results"* would
be a different — and device — intended purpose
(`files/06_COMPLIANCE_TR.md:11-12`).

**Tables and fields.** `documents` (`models.py:707-779`): `object_ref` is
`special_category_health` (the bytes live in the object store, never inline in a row);
`sha256`, `media_type`, `provenance`, `patient_id`, `session_id` are
`operational_metadata`. Tests pin the absence of any `LargeBinary` column
(`models.py:12-13`).

**Basis the code claims.** Registry `explicit_consent` (`registry.py:107`); `object_ref`
carries `KVKK m.6 … açık rıza per consent scope` (`models.py:738-744`).

**Retention.** `clinical_record` — the retention row names document objects explicitly
(`retention_policy.yaml:96-99`).

**Recipients.** `tenant clinicians via a consented share` for `object_ref`; internal for
the rest.

**Required or optional.** Optional, off by default.

**Withdrawal cascade.** None (`registry.py:107`).

**What the patient observably loses.** The Kayıtlarım (records) tab keeps rendering, but
every document endpoint refuses: no upload, no list, no download
(`apps/mobile/src/app/(tabs)/records.tsx:1-8`, which states the screen is "gated on the
documents consent scope").

---

### 2.7 `learning:personal` — `learning.personal.tr.md`

**What the software does — and what it does not do yet.** Design: Loop 1, service
performance inside the patient's own record; learned facts are inspectable, and a
`PatientOverlay` fact requires patient or clinician confirmation at type level
(CLAUDE.md invariant 12; `files/06_COMPLIANCE_TR.md:123`). **Build state: `services/`
contains `api`, `probes` and `voice-runtime` only. There is no `services/learning` in
this tree and no table stores a learned fact.** Counsel is drafting ahead of the
implementation, which is the right order, but the sheet should not pretend otherwise.

**Tables and fields.** None today.

**Basis the code claims.** **Not açık rıza.** `LegalBasis.SERVICE_PERFORMANCE`, defined
as "performance of the very service the patient configured" (`registry.py:66-68`,
`registry.py:108-112`). This is one of only two purposes that are ON by default —
`default_granted=True` — and the registry docstring explains the rule: every açık rıza
purpose starts OFF because "there is no pre-tick the server could even represent", and
only the two purposes files/06 §2 marks with a non-consent basis start ON
(`registry.py:20-23`).

**Retention.** No class exists. The nearest applicable row would be `clinical_record`
(learned facts sit inside the patient's record), but no code says so today.
**`awaiting-human` in effect** — see §3.6.

**Recipients.** Internal; nothing leaves the patient's own record by design.

**Required or optional.** On by default, opt-out. Not a consent, so no açık rıza text
governs it — but files/06 §2 still requires it to be inspectable and the basis to be
stated honestly, and the UI renders it as `ui: "optout"` with dedicated basis copy
(`apps/mobile/src/lib/consent/purposes.ts:136-147`).

**Withdrawal cascade.** None. But withdrawal of a default-on purpose **materialises an
opt-out row** even though no grant row existed, "because an opt-out that leaves no
record is an opt-out nobody can prove" (`service.py:21-23`, `service.py:361-376`). That
row carries `version = "opt-out"` and no text hash, since no consent text governs a
non-consent basis (`service.py:70-73`).

**What the patient observably loses.** Personalisation of their own record across
visits.

---

### 2.8 `learning:service_improvement` — `learning.service_improvement.tr.md`

**What the software does.** Design: Loop 2, de-identified aggregates with k ≥ 10, used
to improve the service (`files/06_COMPLIANCE_TR.md:123`, files/06 §8). Proposal-only:
the pipeline may open PRs with evidence bundles and is technically unable to modify
red-flag levels, instruments, consent texts, the Talker tool list, PolicyGuard or
profile routing (CLAUDE.md invariant 12; `files/06_COMPLIANCE_TR.md:15`). **Build state:
same as §2.7 — not built.**

**Tables and fields.** None today.

**Basis the code claims.** `LegalBasis.DEIDENTIFIED_OPTOUT` — "de-identified aggregates
(k ≥ 10, files/06 §8); an opt-out purpose whose refusal costs no feature"
(`registry.py:69-71`, `registry.py:113-117`). Default ON.

**Retention.** No class. `awaiting-human` in effect.

**Recipients.** Internal. Anything publishable, or voice-model training, is **not** this
purpose — it is `research` plus ethics plus KSVY-16 anonymisation
(`files/06_COMPLIANCE_TR.md:123`).

**Required or optional.** On by default, opt-out, and files/06 §2 states the promise the
text must keep: **opting out costs no feature**
(`files/06_COMPLIANCE_TR.md:85`).

**Withdrawal cascade.** None; opt-out row materialised as in §2.7.

**What the patient observably loses.** Nothing. That is the point, and it is a
representation the text will be held to.

---

### 2.9 `satisfaction` — `satisfaction.tr.md`

**What the software does.** Collects CSAT/NPS responses after a visit.

**Tables and fields.** `events` is the only table that can carry them — its docstring
names "csat/nps/lifecycle streams" (`models.py:969-971`) — with `event_type` values
`csat.v1`, `nps.v1` (`models.py:1000-1010`) and `payload` constrained to id-shaped
values with no PHI (`models.py:1011-1021`).

**Basis the code claims.** Registry `explicit_consent` (`registry.py:118`). But the
`events` columns are annotated `KVKK m.5/2-c — processing necessary for the service
contract` (`models.py:1014-1020`), and `retention_policy.yaml:174` also gives the
`satisfaction` class the m.5/2-c contract basis, not m.6 açık rıza.

**An inconsistency counsel should know about, flagged not resolved.** The registry makes
`satisfaction` an açık rıza purpose; the storage annotations and the retention class
give it a contract basis. Both cannot be the operative ground. This is an engineering
defect to reconcile before the text is drafted, because the text must state the basis
the system actually relies on.

**Retention.** Two different answers exist in code, which is the second half of the same
defect. The `events` columns claim `telemetry window: 30 d hot / 1 y cold`
(`db/inventory.py:90`), while the dedicated retention class says
`kind: with_account`, sourced verbatim from files/06 §3 "Satisfaction: with account"
(`retention_policy.yaml:173-182`). The class is `dsar_erasable: true`.

**Recipients.** `internal services only`.

**Required or optional.** Optional, off by default.

**Withdrawal cascade.** None.

**What the patient observably loses.** The satisfaction prompt. No clinical effect.

---

### 2.10 `share` — `share.tr.md`

**What the software does.** Issues a Doctor Link: a time-limited, section-scoped grant
of one note to one recipient. Enforced conditionally on the note routes as
`share:previsit_note` (`notes.py:37,73,125`).

**Tables and fields.** `shares` (`models.py:654-704`): `note_id`, `scope_sections`
(section ids only), `expires_at`, `revoked_at`, all category `consent_record` with basis
`KVKK m.6 … açık rıza per consent scope`.

**Basis the code claims.** `explicit_consent`, `parameterised=True`
(`registry.py:119`).

**Parameterisation is a legal constraint, not a UI convenience.** The bare `share` id is
**not grantable** (`registry.py:142-146`): a scope must be `share:<qualifier>`, "because
a share consent without its parameters would be a bundled consent"
(`registry.py:16-18`). The mobile registry omits a `share` row for the same reason: "A
bare share toggle on a settings screen would be the bundled consent 06 §2 forbids"
(`apps/mobile/src/lib/consent/purposes.ts:8-10`). The per-visit grant is asked in the
Review & send flow.

**Retention.** Two clocks. The token: `doctor_link_tokens`, `kind: expiry`,
`max_hours: 72`, `action: destroy`, `destruction_path: periodic`
(`retention_policy.yaml:101-112`). The grant row itself: `share expiry ≤ 72 h default;
grant row retained with the record for audit` (`db/inventory.py:89`), following
`clinical_record`.

**Recipients.** `tenant clinicians via a consented share` (`db/inventory.py:107`).

**Required or optional.** Optional, off by default, and granted per visit rather than
once.

**Withdrawal cascade.** `dependents_of("share")` is empty, but shares are revoked by a
separate rule: withdrawing `share` **or** `core` revokes every live share row in the
same evaluation pass (`service.py:280-283`, `service.py:318-326`).

**The boundary counsel must state plainly, and the reason it is stated rather than
softened.** files/06 §2.3 (`files/06_COMPLIANCE_TR.md:102`): where a note has already
been pushed to a hospital HBYS/FHIR endpoint, deletion is **the hospital's** as
controller — "say so plainly to the patient rather than promising a deletion we cannot
perform". The system emits a FHIR `Consent`/`Provenance` update so the hospital's record
shows the withdrawal, but it cannot delete on the hospital's behalf.

**What the patient observably loses.** No Doctor Link can be created; existing ones are
revoked on withdrawal.

---

### 2.11 `research` — `research.tr.md`

**What the software does.** Design: anything publishable, and any voice-model training,
runs under this purpose plus ethics approval plus KSVY-16 anonymisation
(`files/06_COMPLIANCE_TR.md:123`). Every export carries an ethics id
(`files/06_COMPLIANCE_TR.md:75`). **Build state: no research export path exists in this
tree.**

**Tables and fields.** None today.

**Basis the code claims.** Registry `explicit_consent` (`registry.py:120`). The
retention class names `KVKK m.6 + KSVY-16 — research under ethics approval`
(`retention_policy.yaml:185`).

**Retention — `awaiting-human`, and the code says so.**

```yaml
    retention: { kind: unspecified }
    …
    status: draft_needs_source
    source: >-
      06 §3: "Research extracts: per ethics protocol." The ethics protocol
      that would supply the duration does not exist in this repository, so
      this row is draft_needs_source and the engine fails closed.
```
— `retention_policy.yaml:189-197`. A `draft_needs_source` class may carry no duration and
may not be DSAR-erasable; the validator refuses both
(`retention/policy.py:159-176`).

**Recipients.** Per ethics protocol; not defined in code.

**Required or optional.** Optional, off by default.

**Withdrawal cascade.** None.

**What the patient observably loses.** Nothing available today.

**Do not conflate this with the acoustic ICF.** The registered clinical investigation of
the `acoustic` module is a separate artefact under TCKAY with its own required content
list (`files/06_COMPLIANCE_TR.md:105`) — study id, protocol version, investigator, KAEK
approval number, TİTCK permission, insurance, that audio is retained and for how long,
who sees it, and the right to withdraw without effect on care. `research.tr.md` is not
that document and must not try to be.

---

## 3 · Open questions counsel must answer

Gathered from the existing blocker rows and gap statements in the repository. Nothing in
this section is invented; each item cites where it is already recorded.

### 3.1 The nine minor/guardian questions — HB-L20

`files/HUMAN_BLOCKERS.md:68`. Named human: **Turkish counsel (health-law), instructed by
the owner**. Status open, raised 29 Aug 2026. The row's own framing: "Nine
minor/guardian questions counsel must answer before the age gate can assert anything
beyond its fail-closed defaults. INT-223 encodes the mechanism with every contested
value refused rather than chosen".

1. `unverified_dob` — may a self-declared DOB ground the adult self-consent path, or must it be verified against an authenticated source?
2. `dob_collection_mandatory` — must a DOB be collected and verified before any intake at all, given that without one the under-18 regime cannot be asserted?
3. `adolescent_self_consent` — does HHY m.24 let a mature 12–17 year old give açık rıza alone, and for which purposes?
4. `emancipation` — must a TMK ergin kılınma / marriage claim end the guardian requirement, on what evidence?
5. `leap_day_maturity` — does a 29 February birth attain majority on 1 March in a non-leap year?
6. `adolescent_private_guardian_default` — with no recorded clinic policy, may the adolescent-private section be withheld from the guardian, or do HHY rights compel disclosure?
7. `jurisdiction_tr_only` — which jurisdictions beyond Türkiye must be served, so their rules can be encoded rather than refused?
8. `guardian_link_basis` — which KVKK m.5/m.6 ground and retention applies to a persisted guardian↔minor record?
9. `guardian_relationship_proof` — what evidence of velâyet is required before a guardian may consent, and who verifies it?

**Question 8 is visible in the schema right now**, which is why it belongs in a brief
about consent texts rather than only in an engineering backlog. Every column of
`guardian_links` carries an `awaiting-human` basis and an `awaiting-human` retention:

```python
BASIS_AWAITING_HUMAN_GUARDIAN = (
    "awaiting-human — the KVKK m.5/m.6 ground for a guardian↔minor link is unassigned; "
    "counsel names it (policy row guardian_link_basis) before the guardian_link gate opens"
)
```
— `db/inventory.py:80-83`; retention twin at `db/inventory.py:99-102`; the table at
`models.py:540-651`. `verified_at` stays NULL because no proof standard exists yet
(`models.py:550-551`).

Today the gate is shut: no DOB is collected or persisted, every non-adult path demands
the guardian, and a non-TR subject is refused rather than evaluated against Turkish
thresholds (`files/HUMAN_BLOCKERS.md:68`, blocks column). Relevant background for
counsel: files/06 §6 (`files/06_COMPLIANCE_TR.md:117`) and the TMK-339 / HHY-24 rows
(`files/06_COMPLIANCE_TR.md:58,71`).

### 3.2 The staff-access purpose gap — HB-L6, files/08 §2.6

There is **no purpose in files/06 §2 that covers a member of INTAKE staff reading
clinical content**, so there is no basis for the code to check against. The gap is
stated in terms at `files/08_ADMIN_CONSOLE_AND_OBSERVABILITY.md:137-138`:

> ### 2.6 Legal basis for staff access — a genuine gap **[counsel]**
> … post-7499 the health regime aligns to **GDPR Art. 9**, so legitimate interest is
> unavailable, and m.6/3's care ground runs to persons **under a healthcare obligation
> of secrecy** — **an INTAKE support engineer is not that person**. The purposes
> enumerated in `06 §2` contain **nothing covering staff access** at all. **Inference for
> counsel:** a `support_access` **explicit-consent** purpose is needed, unbundled from
> the others and obtained **at the point of the support request**, not at onboarding.

Corroborated in this tree: a repo-wide search for `support_access` returns exactly one
hit — that sentence. The registry's closed list (`registry.py:89-121`) contains no staff
purpose of any kind, and an unlisted scope raises `UnknownPurposeError`
(`registry.py:56-58`).

**INT-175 hit this while building the Langfuse annotation queues.** Its code is on the
unmerged `int-175` branch, so it is cited here as a finding rather than as code in this
tree: all three review queues need a staff read of patient content, every queue's
`content_scope` is `None`, and the authorisation function's only return type is
`ContentReadRefused` — there is no granted branch to write, because there is no scope to
name. The refusal it records reads: "staff reads of patient content are unruled:
files/HUMAN_BLOCKERS.md HB-L6 is open, and files/06 §2 enumerates no purpose covering
staff access (files/08 §2.6). No lawful basis exists to check, so there is nothing to
grant."

The blocker row itself, `files/HUMAN_BLOCKERS.md:59` (HB-L6, named human **counsel**,
open, raised 25 Aug 2026), asks two further things:

- the **controller-instruction reference** for processor tenants;
- whether **24 h is the right notice window** for the patient access-log entry under
  KSVY / KVKK m.11.

And it records the four unmanaged read paths that the design collapses into a single
audited break-glass: Langfuse spans, Grafana Explore over Loki/Tempo, `replay(event_log)`
and break-glass itself (`files/08_ADMIN_CONSOLE_AND_OBSERVABILITY.md:116-121`), three of
which have **no governance and no logging today**.

**Why this reaches INT-210 and not only the console backlog.** files/08 §2.5
(`files/08_ADMIN_CONSOLE_AND_OBSERVABILITY.md:123`): "the honest answer to *'does the
patient ever find out a member of staff read their intake?'* is: **only if they file a
KVKK m.11 request, and the DSAR export is not specified to include staff reads at all**."
If counsel's answer is a `support_access` purpose, it becomes a twelfth purpose and a
twelfth file, and the aydınlatma set must describe it.

### 3.3 Backup retention versus crypto-shredding — HB-I8

`files/HUMAN_BLOCKERS.md:100`. Named human: **owner + counsel (via INT-212)**. Open,
raised 29 Aug 2026. The row asks two things and states why the first is legal rather
than operational:

> **(a) How many full backups does the pgBackRest repository keep, and for how long is
> the WAL archive retained?** … A backup outlives the crypto-shredding it is supposed to
> be subject to, which makes this a **KVKK-7 / DEST-2017 question, not an ops
> preference** — the destruction policy (INT-212) and the retention engine (INT-036)
> both need the same number.
>
> **(b)** `10 §3` says "a second location in Türkiye" and no file names a site, a
> provider or a region … so `INTAKE_DR_S3_ENDPOINT` has no default and the DR object
> store has no registry row.

Why it touches the consent texts: the retention sentence in every purpose's text, and
the deletion promise in the DSAR copy, are only true to the extent the backups honour
them. Today `PGBACKREST_REPO1_RETENTION_FULL` has no default anywhere and the DR drill
fails closed rather than expiring anything.

### 3.4 The DSAR export strings INT-037 left empty

INT-037 is `status: done` (`docs/backlog/issues.yaml:370`) and its export refuses to
render, because the fixed strings it renders from do not exist. The module that declares
them says exactly why no engineer may fill them in:

```text
This module declares a KEY SET, not copy. The Turkish wording behind every
key is authored by counsel into ``docs/legal/strings.yaml`` under INT-210
(files/06 §7, "Fixed legal copy … PolicyGuard-protected") … Nothing here may ever carry
a default: a "temporary" Turkish string in source is exactly the drafted-legal-copy this
project forbids, and it would be indistinguishable from counsel's own once merged.
```
— `services/api/src/intake_api/dsar/strings.py:1-9`

Thirteen keys are unauthored (`dsar/strings.py:34-62`):

| key | what it labels |
|---|---|
| `dsar_export.title` | the document title |
| `dsar_export.footer` | the footer — see the question below |
| `dsar_export.section.visits` | section heading |
| `dsar_export.section.notes` | section heading |
| `dsar_export.section.documents` | section heading |
| `dsar_export.section.consents` | section heading |
| `dsar_export.section.shares` | section heading |
| `dsar_export.section.rectifications` | section heading |
| `dsar_export.section.requests` | section heading |
| `dsar_export.section.learned_facts` | section heading: the learned facts files/09 §3 calls "exported/deletable" |
| `dsar_export.section.feedback` | section heading: the patient's satisfaction comment |
| `dsar_export.section.preferences` | section heading: the notification opt-out and quiet window |
| `dsar_export.section.guardians` | section heading: the guardian↔minor link (gate shut today) |

*(Updated 27 Sep 2026 by INT-395. The survey found nine keys; INT-395 added the last four,
because the export now lists every table the inventory annotations put under the
subject's access right and no existing heading fits these four. Each is one more
heading, with no wording drafted; the export refuses without it exactly as before.)*

**The one substantive question inside that list**, recorded verbatim at
`dsar/strings.py:11-14`: `dsar_export.footer` is deliberately its own key rather than a
reuse of the files/06 §7 note footer, because "whether the KVKK m.13 response document
carries the 1219 m.8 clinical disclaimer verbatim, a variant, or nothing at all is
counsel's call, and encoding a guess here would take that call from them."

`docs/legal/strings.yaml` does not exist (verified: a repo-wide search for
`strings.yaml` returns nothing). The whole files/06 §7 fixed-string set
(`files/06_COMPLIANCE_TR.md:119-120` — note/PDF footer, static safety line, AI labels,
the "Konuşma özellikleri" caveat, the third-party provenance qualifier) is unauthored
with it, and files/10 §7 records that this file "and PolicyGuard rules are not editable
from any console at any privilege — PR with legal CODEOWNER review only"
(`files/10_SECURITY_AND_TECHNICAL_MONITORING.md:87`).

### 3.5 The consumer-tenant consent-record retention period

Not a blocker row, but an `awaiting-human` the code carries and a number the texts will
have to state:

```yaml
  - data_class: consent_records_consumer_tenant
    …
    retention: { kind: unspecified }
    status: draft_needs_source
    source: >-
      06 §3: "Consent & audit records: 10 years (hospital tenants)" — the
      parenthetical scopes the figure to hospital tenants; the consumer-tenant
      duration is unspecified in 06 §3, so this row is draft_needs_source and
      the engine fails closed.
```
— `retention_policy.yaml:128-143`

### 3.6 Smaller factual gaps a drafter will run into

- **No retention class exists for either learning purpose** (§2.7, §2.8). If Loop 1
  facts sit inside the clinical record they follow `clinical_record`; nothing in code
  says so, and the text will have to state a retention.
- **The `satisfaction` basis and retention disagree with themselves** (§2.9): registry
  says açık rıza, storage and retention class say m.5/2-c contract; column annotation
  says 30 d / 1 y, retention class says with-account.
- **`docs/legal/` has no `opinions/` directory**, although files/06's preamble says
  nothing is deferred "without a written counsel opinion in `docs/legal/opinions/`"
  (`files/06_COMPLIANCE_TR.md:3`).
- **No HUMAN_BLOCKERS row exists for authoring the texts themselves.** Recorded in
  terms at `docs/backlog/blockers.md:10`: "(legal-text authoring is INT-210's
  deliverable; no HB row exists for it)". Every other awaiting-human item in the project
  carries an `HB-*` id; this is the exception, and it is the largest one.
- **The KSVY 30-year deceased-person retention** (RG 33096, 3 Dec 2025) has not been
  checked against the §3 retention schedule, which was written against the 20-year text
  — flagged `[counsel]` at `files/06_COMPLIANCE_TR.md:78-80`.
- **Two instruments are licence-blocked** (HB-L2 C-SSRS, HB-L3 WHO-5;
  `files/HUMAN_BLOCKERS.md:55-56`, named human **owner + counsel**). They do not compile
  into a pack, so the `wellbeing` text must not describe them.

---

## 4 · What breaks today without these texts

Stated as observable behaviour, with the commands and the output.

### 4.1 The legal tree is empty

```
$ ls docs/legal/
accessibility-statement.md
$ ls docs/legal/consents/
ls: docs/legal/consents/: No such file or directory
```

One file, and it is not a consent text.

### 4.2 So the catalogue is empty and the loader refuses, purpose by purpose

```
$ uv run python -c "…ConsentTextCatalog('docs/legal/consents')…"
catalogue root: docs/legal/consents | exists: False
texts loadable: []
core                             -> ConsentTextMissingError: no consent text for purpose 'core' at docs/legal/consents/core.tr.md — texts are authored into docs/legal by INT-210; nothing may be granted without one
voice                            -> ConsentTextMissingError: no consent text for purpose 'voice' at docs/legal/consents/voice.tr.md — …
wellbeing                        -> ConsentTextMissingError: … wellbeing.tr.md …
lane:affect                      -> ConsentTextMissingError: … lane.affect.tr.md …
lane:linguistic                  -> ConsentTextMissingError: … lane.linguistic.tr.md …
documents                        -> ConsentTextMissingError: … documents.tr.md …
learning:personal                -> ConsentTextMissingError: … learning.personal.tr.md …
learning:service_improvement     -> ConsentTextMissingError: … learning.service_improvement.tr.md …
satisfaction                     -> ConsentTextMissingError: … satisfaction.tr.md …
share                            -> ConsentTextMissingError: … share.tr.md …
research                         -> ConsentTextMissingError: … research.tr.md …
```

Eleven for eleven. The full message text is at `texts.py:131-134`.

### 4.3 So no scope can be granted

`grant_consent` loads the text **before** it writes anything:

```text
    resolve_scope(scope)
    text = catalog.entry(scope)  # fail closed before anything is written
```
— `service.py:195-196`

Over HTTP the same refusal is a 409 (`consents.py:255-258`,
`services/api/src/intake_api/errors.py`), and the pinning test asserts it with today's
tree: `test_grant_fails_closed_when_docs_legal_is_absent` →
`assert response.status_code == 409`, `assert response.json() == {"error":
"text_missing", "scope": "voice"}`, `assert _consent_rows(harness, "voice") == []`
(`tests/api/test_consent_routes.py:236-247`). Its sibling in
`tests/legal/test_consent_guard.py:184-206` asserts that a refused grant writes no audit
entry either — "a refused grant is not a consent change".

`GET /v1/consents` still answers, but its `texts` array is empty: "An absent legal tree
serves an EMPTY texts list — fail closed, never invented copy (invariant 18)"
(`consents.py:22-23`).

### 4.4 So documents, records and sharing are unreachable on a real device

The three route-enforced scopes are `core`, `documents` and `share:previsit_note`. A
real account can hold none of them, because the only way a real account acquires a grant
is `grant_consent`, which refuses. The two synthetic dev-tier accounts carry seeded rows
for exactly those three scopes, and the seed comment states the boundary:

```python
# … These seed rows are UNBOUND on purpose: no docs/legal
# text exists yet (INT-210, awaiting-human), so they carry no text_hash — and
# the INT-038 guard treats them as stale (absent, re-prompt) the moment the
# canonical text for their purpose lands. Real accounts (INT-131) grant only
# through intake_platform.consent.grant_consent, which refuses without a text.
DEV_CONSENT_SCOPES = ("core", "documents", "share:previsit_note")
```
— `services/api/src/intake_api/dev_fixture.py:48-56`

So on a real device: visits and notes 403 (`visits.py:64,100,134`; `notes.py:73,125`),
every document endpoint 403 (`documents.py:260,313,344,432`), no Doctor Link can be
created (`notes.py:125`), and the Wellbeing tab never appears
(`apps/mobile/src/lib/session.tsx:225-229`).

### 4.5 And the DSAR answer cannot be rendered

```
$ uv run python -c "…LegalStringsCatalog('docs/legal/strings.yaml').entry(required=DSAR_EXPORT_STRING_KEYS)…"
LegalStringsMissingError: no fixed legal strings at docs/legal/strings.yaml — the strings are authored by INT-210 (files/06 §7); nothing that renders them may be produced without
```

The endpoint answers 503 `legal_strings_missing`
(`services/api/src/intake_api/dsar/router.py:66-69`) **while the KVKK m.13 clock keeps
running** — the request is recorded, `status: received`, `completed_at: None`
(`tests/legal/test_dsar_flows.py:216-231`), because, in that suite's words, "a request we
cannot answer is an obligation we still owe" (`tests/legal/test_dsar_flows.py:9-14`).

---

## 5 · Why this brief ships no `<purpose>.tr.md` scaffolds

Deliberate, and worth stating because the absence would otherwise look like an omission.

**A scaffold with an empty body is rejected outright.** The loader treats it as a defect
in the legal tree, not as an absent text:

```
$ uv run python -c "…write '---\nconsent_text_version: v1\n---\n' then entry('core')…"
scaffold with empty body -> ConsentTextInvalidError: <dir>/core.tr.md: no consent copy after front matter
```

That is `texts.py:107-108`. And an invalid text raises on **both** the strict and the
tolerant lookup (`texts.py:9-15`, `texts.py:144-151`), so eleven empty scaffolds would
convert today's clean fail-closed state — "no text, no grant", which is correct and
provable — into eleven hard errors on a path that currently degrades gracefully for
already-recorded grants. **A scaffold would be strictly worse than nothing.**

**A scaffold carrying stand-in Turkish copy would be a fake consent text.** It would
load, it would hash, it would bind to real grants, and once merged it would be
indistinguishable from counsel's own words — the exact failure mode `dsar/strings.py:7-9`
names for the fixed strings. CLAUDE.md invariant 17 forbids it, and the sole exception
that invariant carves out is reserved for a clinical value inside a
`draft_needs_source` rule, which a consent text is not.

Consequently the deliverable of INT-245 is this annex and nothing else. The eleven files
are INT-210's, they are human legal work, and they arrive with a counsel sign-off
recorded in the evidence file before merge (`docs/backlog/issues.yaml:2242`).

---

## 6 · Sources cited

| area | file |
|---|---|
| invariants, clinical content rules, stop-and-ask list | `CLAUDE.md` |
| purposes, bases, defaults, cascade, ICF carve-out | `files/06_COMPLIANCE_TR.md` §0.7, §1, §2–§2.4, §3, §6, §7, §8, §10 |
| staff-access gap, four read paths, DSAR completeness | `files/08_ADMIN_CONSOLE_AND_OBSERVABILITY.md` §2.5, §2.6 |
| audit chain, egress, consent-vendor parity, strings immutability | `files/10_SECURITY_AND_TECHNICAL_MONITORING.md` §2–§5, §7, §9 |
| HB-L2, HB-L3, HB-L6, HB-L20, HB-I8 | `files/HUMAN_BLOCKERS.md` |
| the eleven purposes, bases, defaults, cascade | `packages/intake_platform/src/intake_platform/consent/registry.py` |
| the file contract and the hash binding | `packages/intake_platform/src/intake_platform/consent/texts.py` |
| grant / state / withdraw / sweep semantics | `packages/intake_platform/src/intake_platform/consent/service.py` |
| `{category, purpose, basis, retention, recipients}` vocabulary | `packages/intake_platform/src/intake_platform/db/inventory.py` |
| tables and per-column annotations | `packages/intake_platform/src/intake_platform/db/models.py` |
| retention classes and their files/06 §3 sources | `packages/intake_platform/src/intake_platform/retention/retention_policy.yaml` |
| instrument licence gate | `packages/protocols/src/protocols/licences.py`, `validator.py` |
| route scope enforcement | `services/api/src/intake_api/{visits,notes,documents,consents,consent_guard,dev_fixture,settings}.py` |
| DSAR key set and fail-closed export | `services/api/src/intake_api/dsar/{strings,router,document}.py`, `packages/intake_platform/src/intake_platform/legal/strings.py` |
| PHI-path egress | `infra/security/egress-allowlist.yaml` |
| UI purpose mirror and tab gating | `apps/mobile/src/lib/consent/purposes.ts`, `apps/mobile/src/lib/session.tsx` |
| INT-210, INT-037, INT-038, INT-132, INT-212, INT-223 entries | `docs/backlog/issues.yaml` |
| the missing HB row for text authoring | `docs/backlog/blockers.md` |
