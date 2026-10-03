# docs/legal/store — store-facing legal artefacts

This tree is deliberately empty of content and full of contract (INT-224).

Two things live here once humans supply them, and both are inside
`docs/legal/` for a reason: CLAUDE.md invariant 18 says legal texts render
only from `docs/legal/` with hash binding, and invariant 20's claims gate
scans this tree — so a store artefact is covered by both rules by virtue of
where it sits, not by anyone remembering to add it to a list.

## `taxonomy/` — the vendors' own words

Apple's App Privacy data types, Google Play's Data safety categories, the
Play Health apps policy and the IARC questionnaire are **published artefacts
that change**. None of them may be written from memory: a store requirement
recalled wrongly reads as authoritative to every later reader, exactly like an
invented clinical threshold, and no diff makes it look wrong.

Each file here is a pair:

- `<store>.txt` — the verbatim published text, copied and dated;
- `<store>.yaml` — the machine-readable form, carrying `provenance:` with
  `store`, `form`, `source_url`, `retrieved_on`, `snapshot` and
  `snapshot_sha256`, then the `data_types:` the form defines and a `mapping:`
  from our inventory categories to them.

`intake_platform.store.taxonomy.load_taxonomy` refuses anything else, and
refuses a `.yaml` whose `snapshot_sha256` no longer matches its `.txt` — a
taxonomy may not outlive the text it was read from.

Nothing is committed yet. The ask is **HUMAN_BLOCKERS.md HB-A12**.

## `listing/` — the listing copy

`<store>.<locale>.yaml`, with a `provenance:` block and a `fields:` mapping of
whatever fields that store's form actually asks for. The loader imposes no
field list of its own, because which fields a form requires is that form's
published fact.

Two gates run over every field, and both fail closed:

1. **No performance claim.** ADR-022 quotes App Review 1.4.1 verbatim; a
   claim about how well a health measurement performs, which we could not
   substantiate today, is a rejection — and invariant 20 forbids the figure
   independently. (This paragraph deliberately names no metric: the gate
   scans this file too, which is the shortest possible proof that the tree is
   in scope.)
2. **No `device_functions` claim.** files/06 §0.3 names the two functions that
   make this product a Class IIb device — automated red-flag triage directing
   a patient's urgency, and automated interpretation of screening instruments
   — plus the investigational acoustic module (§0.7). Copy describing any of
   them claims a capability that stays off without a recorded CE certificate
   or clinical-investigation approval id.

The second gate exempts denials, and that is not a loophole: the fixed copy of
files/06 §7 that we are *required* to show contains "tanı" twice, and the
static device-off safety line contains 112. A gate that rejected the
disclaimers would reject the very sentences that keep the product on the
non-device side of the boundary. The exemption window is bounded so that
denying one capability cannot launder a claim about another.

Nothing is committed yet. The seller's legal entity, the privacy and support
URLs and the Turkish marketing text are owed by **HB-L21**, together with the
determination that decides the largest single row of the label: whether
microphone audio, which is transmitted for transcription and by invariant 3
never written anywhere, counts as *collected* on each store's form.

## `submission/` — the App Store answers that are not copy (INT-482)

`app-store.yaml` holds the category, the age-rating answers and the App Review
notes. Each age-rating answer cites the repo file it comes from. The file may
also hold the privacy-policy link, the support URL and the copyright line, once
HB-L27 and HB-L21(e) answer them. `intake_platform.store.eas_metadata.load_submission`
refuses a missing age-rating key, an answer outside the EAS schema, review notes
that fail either listing gate, and a link that is not https.

Nothing is committed here yet either. The candidates are in
`docs/legal/drafts/store/`, pending legal-lane review.

## `apps/mobile/store.config.json` — rendered, never written

EAS Metadata pushes that file to App Store Connect, so it counts as a published
listing and nobody writes it by hand. `make store-config`
(`scripts/release/render_store_config.py`) builds it from the App Store files in
`listing/` and from `submission/app-store.yaml`, and from nothing else. Each
listing passes both gates above and the strict claims scan. A link inside the
copy is refused. The privacy-policy link binds to the signed `gizlilik` document
and must name that document's sha256 (invariant 18). `automaticRelease` is pinned
to `false`. With nothing served the script exits 3 and writes nothing, and
`tests/legal/test_store_submission_drafts.py` makes sure the file exists only when
served copy exists to render it from.

## Where the label comes from

Not from here. The Data safety and App Privacy answers are **derived** from
the data inventory — the invariant-18 annotations on every column, plus the
flows that have no column — by `intake_platform.store.declaration`, and a fact
the taxonomy does not map is refused rather than defaulted. A declaration that
disagrees with the inventory is a defect, so it is never written by hand.
