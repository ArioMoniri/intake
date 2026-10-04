# ADR-040 · Subject-aware addressing: a proxy hears the pack's own proxy text or nothing

Status: Accepted (INT-483, GitHub #826). Implements owner decision D24, answer 1Y.

## Context

**The owner's decision.** Owner decision D24 (3 Oct 2026, answer 1Y; recorded in `files/00_STATE.md` §3 on the INT-470 branch, PR #804) reads: in a proxy session, where a parent or carer answers for the patient, every self-addressed question is reworded for the patient ("Çocuğunuz…") or skipped. The child and carer paths stay closed until that mechanism exists.

**The legal bounds.** LD-02 (INT-471, PR #809, `docs/legal/decisions/LD-02.md`, status `proposed`, synthetic and test use only) sets them:

- majority is the eighteenth birthday;
- only a holder of velâyet or a vasi acts for a minor;
- an adult with discernment who is not restricted answers for themselves;
- that a carer answers for nobody in a synthetic session is the owner's product rule, not the law;
- HB-L20 stays open for counsel, and INT-223's fail-closed defaults hold unchanged.

**Why the DSL could not do it.** Before this ADR a slot carried one `ask_tr`, written to the patient in the second person ("Şikâyetiniz ne zaman başladı?"). A proxy hearing it answers about themselves, and that answer is filed in the patient's slot. The only tool was a gate. CD-01 used one as a stop-gap: `chest_pain.present` carries `skip_if: "identity_check.subject_role == 'yakınım adına'"`. That gate skips a life-threat probe in exactly the sessions where nobody else will ask it, and CD-01 records the result as under-triage finding F13.

**The hazard as INT-448 and INT-470 named it.** CD-103 (cluster-wave-b `#L77`) names it for the base pack: a guardian's own pregnancy, smoking, alcohol use, weight or complaint must never become the child's. The items waiting on this mechanism are:

- CD-100 T11–T15: ÇEMATEM and child and adolescent mental health, against the cluster's self-addressed slots;
- CD-103: cluster-wave-b `#L77` (child §0 guardian proxy), `#L105` (pedodonti) and `#L117` (Evde Sağlık);
- CD-104: INT-353 `#L310` (the ÇEMATEM and Çocuk ve Ergen Ruh Sağlığı rebind);
- CD-110: the pedodonti airway item, whose proxy text CD-104 accepts;
- CD-105: ortodonti, all items;
- the base self-addressed items: `pregnancy_status`, the HPI items, `weight_kg`, `smoking_status` and `alcohol_use`.

**Why this needs an ADR.** Without a decision, each pack would solve this alone, with a gate, a duplicated slot or a `suppress_slot`. None of those can be checked for completeness, and each one fails silently.

## Decision

No question addressed to the patient is ever put to a proxy in its self-addressed form. In a proxy session, each such slot is spoken from its own verbatim proxy text in the pack, or it is not asked and is recorded `NOT_ASKED_PROXY`.

A red-flag probe is never skipped and never addressed to the speaker. The compiler emits no proxy bundle while any self-addressed askable slot of the resolved chain lacks that handling, and that includes inherited base items.

The session's subject role chooses the document. Every session is composed with its role stated, never defaulted, and the engine refuses a session whose role differs from the document's.

## Mechanism

### The DSL (`packages/protocols/src/protocols/addressing.py`, `dsl.py`)

Two new fields on `Slot`:

- **`addressee: patient | speaker`.** The default is `patient`. Silence means self-addressed, so a slot nobody has classified needs proxy handling. `speaker` is for questions about whoever holds the device, which read correctly in either session, such as the identity and consent-recap turns.
- **`proxy`.** It takes one of two forms, and never both or neither:

  ```yaml
  proxy:
    ask_tr: {tr: "…"}        # reworded: the question as put to the proxy, about the patient
    follow_up_tr: {tr: "…"}  # exactly when the self form has one
    confirm_tr: {tr: "…"}    # exactly when the self form has one
  ```

  ```yaml
  proxy:
    skip: true               # not asked in a proxy session
  ```

CD-01's `proxy_selection` names the chest-pain proxy fields `proxy_ask_tr` and `proxy_follow_up_tr`. In this DSL they are `proxy.ask_tr` and `proxy.follow_up_tr`, so CD-01's copy maps field for field once a decision record carries it into the pack.

Rules on these fields:

- `choices_tr` has no proxy form. The choices are the literals a rule tests, so both sessions offer the same ones.
- A `speaker` slot carries no proxy block. This is a schema error.
- A rewording must speak exactly the texts its self form speaks. If it does not, the validator reports `PROXY_TEXT_MISMATCH` and the pack is refused on every path. This check is a finding and not a schema error, because a hospital `override_text` can add a spoken field after authoring. The merged slot has to stay representable so the compiler can name the gap instead of crashing on it.
- Proxy texts go through the same numeral gate as every other spoken string (invariant 22).

There is no new op. The closed op set of files/12 §3.1 is unchanged, and no `set_attr` can reach `addressee` or `proxy`. Proxy handling is written on the slot, in the pack that declares the slot. Base items are handled in `base.intake`.

### The compiler (`compile/proxy_path.py`, `resolve.py`, `bundle.py`)

`resolve_protocol` and `compile_bundle` take `addressing: self | proxy`. The CLI takes `--addressing`. Checks run on the merged pack, after every layer and every op.

A **red-flag probe** is any slot that a red-flag rule reads, through `when` or `tense_anchor`. The rules counted are the pack rules after overlay composition and the `base.life_threat` rules, drafts included. These are the reads INT-382 protects. Every slot of the files/04 §1 `red_flags` section is also a probe, because those families' triggers are unsigned (HB-C1) and a probe must not become skippable in the gap.

| Refusal | Path | What it refuses |
|---|---|---|
| `PROXY_SKIPS_RED_FLAG_PROBE` | every | A probe marked `skip`. Unasked, the probe reads Unknown and its rule never fires (invariant 7). Also raised for a rule whose `when` cannot be read, while any skip exists. |
| `RED_FLAG_PROBE_SPEAKER_ADDRESSED` | every | A probe declared `speaker`. The speaker's own answer would fill the patient's rule slot (F13 by another door). |
| `PROXY_ADDRESSING_MISSING` | proxy | Every askable slot addressed to the patient that has no `proxy` block. The message names the pack that declared the slot and whether it is must-ask. |
| `PROXY_TEXT_INCOMPLETE` | proxy | A rewording that does not speak what the merged slot speaks, or whose self form a hospital `override_text` rewrote, which leaves the proxy form unreviewed. A locale the proxy text lacks is refused earlier, as `LOCALE_NOT_SELECTABLE`: the proxy maps join the INT-297 intersection like any other speakable field. |
| `RED_FLAG_PROBE_GATED_ON_SUBJECT_ROLE` | proxy | A probe whose `ask_if` or `skip_if` reads `identity_check.subject_role` or a speaker-addressed slot, directly or through another slot's gate, so that the role or the speaker's own answer decides whether the probe is asked. The CD-01 stop-gap is one, and so are the six chest-pain follow-ups gated on it, so the proxy path refuses until the gate is dropped. |
| `PROXY_GATED_ON_SUBJECT_ROLE` | proxy | Any other patient-addressed slot whose gate reads the subject role. A gate that closes in a proxy session skips the question without a trace: no `NOT_ASKED_PROXY`, no coverage gap, no note line. The skip has to be the explicit `proxy: skip`. A speaker-addressed slot, such as `proxy_reported`, may follow the role. |
| `PROXY_SKIP_CLOSES_GATE` | proxy | A question asked in the proxy session whose gate reads a skipped slot. The gate would never open, and the question would be silently never asked (files/13 §9.5). |
| `PROXY_ADMINISTERS_INSTRUMENT` | proxy | A section of the chain administers a validated instrument. Its items are self-report by validation and never reworded (invariant 10). files/12 §2.2 settles that a non-self item yields `InstrumentNotScored`, never a number, but no engine path implements that yet, so a chain with an instrument (`base.intake`'s screening section) has no proxy path. |

Two of these deserve a note:

- `PROXY_ADDRESSING_MISSING` covers every askable slot, not only must-ask ones. An optional question in the second person fills the patient's slot with the speaker's answer just the same. Defaulting it to "skip" would be a clinical choice made by the compiler.
- The two "every path" refusals fire on the self path too, so an unsafe statement about proxy sessions cannot sit in a served self bundle waiting for the proxy path to open.

**The proxy document.** Once there are no refusals, the proxy document is a projection:

- a reworded slot carries its proxy text in `ask_tr`, `follow_up_tr` and `confirm_tr`;
- a skipped slot is marked `proxy_skipped`;
- `ResolvedProtocol.addressing` is `proxy`, so the pinned `resolved_protocol_hash` covers exactly what a proxy hears.

The proxy bundle's clip manifest and Questionnaire carry the proxy text and leave skipped items out. It is written to `dist/<pack>/proxy/` with `"addressing": "proxy"` in its manifest. The self bundle is byte-identical to the INT-297 baseline apart from its hash.

### The runtime (`clinical_agent/fsm.py`, `plan.py`, `note/facts.py`)

`IntakeEngine(..., addressing=...)` takes the session's subject role. A role that differs from the document's addressing raises `EngineError` before any question is asked:

- a proxy is never put the self document's second-person questions;
- no self session runs on proxy wording.

Both session builders, `build_residency_tr_session` and `build_typed_session` (`composition.py`), require `addressing` as a keyword with no default and pass it to the engine. Whoever wires session start therefore has to state the role, and a `proxy_report` session cannot fall through to the self document.

The engine's own parameter may be omitted only by a unit test that constructs an engine directly, which then runs the document's own addressing. A test asserts that every `IntakeEngine(...)` built under `services/` passes `addressing`.

The role maps from INT-133's attribution:

| INT-133 attribution | Addressing | Why |
|---|---|---|
| `proxy_report` | `proxy` | someone answers for the patient |
| `self_report` | `self` | the patient answers |
| `assisted_self_report` | `self` | the patient answers, on a relative's device |

A skipped step starts in **`AnswerState.NOT_ASKED_PROXY`**, a new eighth state:

- it is never on the frontier, so it can never be offered;
- nothing binds to it, so an extraction that names it changes nothing;
- no confirm step is offered for it from the patient's overlay, because a confirm is a question too;
- it is never `ASKED_ABSENT`;
- it carries no value and reads Unknown to every gate and every rule (files/12 §1.1; asserted in `tests/safety/test_triage_when.py`);
- it counts as outstanding in must-ask coverage, never as covered.

`IntakeEngine.proxy_skipped` lists these steps. `NoteGap.not_asked_proxy(step_id)` turns each one into a note gap with the new reason **`not_asked_proxy`**, so the clinician reads it as not asked (proxy).

The clinician-facing wording of that marker is key `previsit_note.gap.not_asked_proxy` in `docs/legal/strings.yaml`. That file is a human deliverable that does not exist yet, so the note renderer fails closed, as it already does for every other note string.

## What stays closed

- **Every proxy path.** No pack in the tree carries a `proxy` block or an `addressee` (pinned by `test_no_pack_in_the_tree_carries_proxy_content_yet`), so the compiler refuses the proxy path for every pack. For `base.intake` it names every askable slot, the CD-01 chest-pain stop-gap, and the screening section's four instruments.
- **Instruments.** Every pack inherits `base.intake`'s screening section, so the proxy path stays closed even after the slot content lands, until two things exist: an instrument path in the engine that honours files/12 §2.2 (`SelfReportAttestation` → `InstrumentNotScored`), and a decision on how a proxy session treats the screening section. This is deliberate: the alternative serves a proxy-answered PHQ-2 as a score.
- **The content.** Which item is reworded and which is skipped, and every proxy sentence, are clinical decisions (owner decision D18). They come in a separate clinical decision record. This ADR writes no proxy copy and chooses no skip.
- **What the content PR must also do.** When that record lands, the PR that writes it into the packs must:
  - drop the CD-01 `skip_if` stop-gap, which the proxy path refuses while it stays;
  - add English mirror keys `<section>.<slot>.proxy.<field>` (the base pack's mirror test now reads proxy text);
  - edit the closed-state pin test and cite its decision record.
- **The child path.** INT-223's age gate refuses every subject under eighteen before any attribution, and so before any addressing, whoever answers and whatever was acknowledged. The guardian-path rows (`guardian_link_basis`, `guardian_relationship_proof`, `adolescent_self_consent`) stay awaiting-human (HB-L20; LD-02).
- **The carer path, on the compiled-pack route.** No proxy bundle compiles, and the engine refuses a proxy session on a self document.
- **What this ADR does not close.** INT-133's profile flow still admits an acknowledged adult companion as `proxy_report`. The mobile app's own question set lies outside the compiled packs (INT-096). Closing those two routes is a profile-layer and app decision, and LD-02 already routes the files/06 §6 conflict to its owner (`carers.conflict_for_06_owner`).
- **Who may be a proxy.** ADR-040 decides how a question is worded for a proxy, never who may be one. `resolve_profile_flow` takes no addressing input, and `intake_platform` does not import `protocols.addressing`.

## Alternatives considered

1. **Gates only, generalising the CD-01 stop-gap.** Put `ask_if`/`skip_if` on `subject_role` on every self-addressed slot. CD-103 `#L77` offered this as "a subject_role gate". Rejected for three reasons:
   - a gate can only skip and never reword;
   - completeness cannot be checked, because a forgotten gate is silence;
   - it skips red-flag probes with no error, which is F13 as policy.
2. **Rewording at runtime**, by pronoun substitution or by asking the Talker to restate the question in the third person. Rejected:
   - invariant 10 requires the verbatim `text_tr` from the pack, and there is nothing to clip-cache;
   - Turkish possession is morphology, not a pronoun ("şikâyetiniz" → "çocuğunuzun şikâyeti"), so a template rewrites the grammar, not just a word;
   - PolicyGuard cannot certify text it did not see at review.
3. **Separate proxy packs, or `suppress_slot` plus a re-declared twin.** Rejected:
   - `suppress_slot` on a must-ask slot is a hard compile error (files/12 §3.2);
   - inherited base items cannot be suppressed by a cluster without exactly that error;
   - every twin is a second copy that drifts from the first. That is the near-twin problem CD-100 spends fifteen rows on.
4. **A per-field reporter flag only** (files/12 §2.2 `Reporter` / `ObservationKind`). It records who answered, but it does not change what is asked, so the hazard is recorded instead of prevented. It is complementary, and `proxy_reported` already rides the note.
5. **Default unhandled optional items to "skip".** This would make the compiler the author of a clinical decision (D18). Rejected in favour of failing closed on every askable slot.
6. **One bundle carrying both texts, with the runtime choosing per turn.** The pinned `resolved_protocol_hash` would then no longer state what was spoken. Two documents, each pinned to its own hash, keep "this is what the session heard" provable.

## Consequences

**Easier.** Each dependent item becomes one clinical decision about one slot, and the compiler checks every slot of the chain. A content author sees the whole outstanding list in one compile.

**Harder.**

- Every new patient-addressed slot is one more item the proxy path waits on.
- The note's gap vocabulary grows from four reasons to five. The goldens were re-rendered: one gap line, and the synthetic strings hash.
- `files/13` §9.3's seven answer states become eight. `files/12` §2.2's unimplemented `NotAskedReason` is not the vehicle, because a reason attached to `NOT_ASKED` would still leave the step on the frontier.
- Every `resolved_protocol_hash` changes once, because the canonical dump gains `addressing`, `addressee`, `proxy` and `proxy_skipped`. The INT-297 baseline test substitutes the hash and still passes byte-for-byte.

**Recorded tensions.**

- **Safeguarding.** The two suicidality probes sit in the `red_flags` section. A pack may therefore not skip them in a proxy session, while INT-133's attribution regime does not ask safeguarding of a proxy at all (files/13 §13). The regime is a session rule and this ADR does not override it. Whatever wording the decision record gives those two probes must be consistent with files/13 §13 and with HB-C8.
- **The RED action script in a proxy session.** A red-flag action, and the UNKNOWN branch's one question ("Şu anda hastanede misiniz?"), speak to whoever holds the device. In a proxy session that person decides the location, which sets REMOTE or ON_SITE for the patient, and ON_SITE removes the 112 affordance (invariant 21). files/02 §5.3 already gives the RED schema a proxy dimension (the CALM register "where the subject is a child and the user is a proxy"; `subject_is_child`), and what proxy flows say at the door is the open HB-C9 question. This ADR does not reword or gate action scripts. Before any proxy path opens for a chain with an active RED rule, the decision record must state the proxy reading of the location question and of the action (HB-C9).
- **An in-session contradiction.** A speaker may answer "yakınım adına" in a session that was started as self. The CD-01 stop-gap still applies for chest pain, and the session's addressing is fixed when the engine is built. Ending such a session and restarting it on the proxy document is runtime behaviour this ADR does not specify.

**Enforced by:**

- `tests/protocols/test_proxy_addressing.py`: the DSL, every refusal with a near-miss control, `base.intake` and an inheriting cluster on the proxy path, and the closed-state pin;
- `tests/engine/test_proxy_addressing_runtime.py`: selection by subject role, the `NOT_ASKED_PROXY` semantics and the note gap;
- `tests/safety/test_triage_when.py`: Unknown to triage;
- `tests/legal/test_proxy_addressing_minor_defaults.py`: INT-223 unrelaxed;
- `tests/protocols/test_base_intake_pack.py`: proxy copy held to the register, numeral and mirror rules.

Recorded against `docs/security/threat-model.md` row `clinical-content`.
