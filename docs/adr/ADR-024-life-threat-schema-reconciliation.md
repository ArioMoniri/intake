# ADR-024 · `when` / `source` are canonical; the life-threat set keeps its on-disk spelling

Status: Accepted (29 Aug 2026 — INT-041)

## Context

`files/protocols/base.life_threat.yaml` carries an explicit open item:

> `schema_reconciliation: status: OPEN — decide before the compiler is written`

Two field names are the same field twice:

- the predicate is `gate:` in the life-threat set and `when:` in `12 §2.4`, which is also the name the `12 §3.2` deny-suffix list protects (`DENY_SUFFIXES = (…, "/when", …)`);
- the provenance block is `evidence:` in the life-threat set and `source:` in `04 §8.1` rule 3 and `12 §2.5`, which is also the name the CI gate carries — `every_red_rule_has_a_source_block`.

The file states the risk precisely: *"if `evidence` wins the gate name has to move with it or it will silently pass by finding nothing to check."* INT-040 had already implemented the DSL with `when` / `source` and recorded that choice in its module docstring; INT-041 is the compiler that has to read both documents, so the decision can no longer be deferred.

## Decision

**`when` and `source` are canonical** — in the pydantic types, in the deny-list, in every CI gate name and in every chain pack on disk.

**The life-threat document keeps `gate:` and `evidence:` as its on-disk spelling**, and `protocols.compile.life_threat.load_life_threat_set` normalises them to the canonical names at load. Writing both spellings on one rule is a load error, not a merge.

## Consequences

- One `RedFlagRule` type serves both documents, so the chain packs and the universal sibling set cannot drift apart in shape, and every rule-level gate written against `source:` sees the life-threat rules too — which is the failure the file warned about.
- `files/protocols/base.life_threat.yaml` needs no edit to be loadable, so the exemplars stay byte-identical to what the clinician will review.
- The deny-suffix `/when` keeps its meaning without a second entry: the alias exists only in the loader, and no pack op can address it.
- If a future author prefers `gate` everywhere, the change is a rename in one loader plus the gate names, and this ADR is the record of why it was not done that way.

## Correction — 29 Aug 2026 (INT-254)

One consequence above is wrong as written and is corrected here rather than edited in place:

> `files/protocols/base.life_threat.yaml` needs no edit to be loadable, so the exemplars stay byte-identical to what the clinician will review.

It was false when it was written. `load_life_threat_set` on that document produced **21 validation errors**, of which the two alias renames this ADR decided were zero — the aliasing works. The claim generalised from "the two names this ADR is about need no edit" to "the file needs no edit", and nothing tested the wider claim because no test loaded the blueprint document at all; the compiler suite runs against a synthetic signed fixture.

What is true, and what INT-254 changed:

- The **alias decision stands unchanged.** `gate`/`evidence` remain the on-disk spelling and are still normalised at load. That half of the consequence holds.
- The file **is** edited, minimally and visibly: the two sourced exemplars now carry `status: active` (the field is required with no default — a default would make a forgotten status read `active`), and the inline rule-schema block documents `status`, `secondary` and the namespace `tense_anchor` lives in. No rule text, level, register, route, threshold, Turkish string or evidence block changed.
- `tense_anchor` was the deeper miss. It was typed as a bare `SlotKey`, but `protocols.triage.engine` unions it into `referenced_slots(when)` and `TriageContext.answers` is keyed "by the dotted slot reference exactly as the when predicate spells it" — so the anchor and the predicate are one namespace, and typing them differently produced two. Both spellings now come from a single `SLOT_REF_PATTERN` in `protocols.types`, used by the DSL constraint and by the `when` tokenizer.
- The exemplars are **not yet loadable**: 13 errors remain, all of them annotations the document carries and the DSL does not model. They are enumerated and pinned open by a test, and INT-255 owns them.

The general lesson for the next ADR of this shape: a consequence that asserts a file loads is a claim a test can make, and this one should have been a test rather than a sentence.
