# Vendored test corpus attribution

`pii_corpus.jsonl` is vendored unmodified from the Hugging Face dataset
**fevziegeyurtsevenler/turkish-pii-corpus**, revision
`2e770a8321133c6cc135f6cb3f8cd2212ea76604`, licensed **Apache-2.0**
(sha256 eadadcb559c1f14dac1e5878cf33433aca7eacf9608af88d5530b139cfb9a31a).

It is a fully synthetic, checksum-valid, span-labeled Turkish PII corpus — no
real person's data — including distractor sentences with number-like strings
that are NOT PII. Used by tests/security/test_deid_leak_rate.py as an
independent gate corpus alongside our own authored fixture.

---

`btx24_test_sample400.jsonl` is the first 400 rows of the **test** split of the
Hugging Face dataset **BTX24/turkish-privacy-pii-ner**, revision
`45a8e18edb57224b14368c910f701e064dbb1326`, licensed **CC-BY-4.0**
(machine-generated synthetic; no real persons; sample sha256
903e7616732539e01ea0f21848657bf4bd25422504339399a454ff677dae243a).
Held-out relative to the NER model's training (train split only) — used by
tests/security/test_deid_ner.py as the names/addresses leak gate.
