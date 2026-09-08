# Evidence — on-demand cached George (ElevenLabs) question clips (dev lane, ADR-028)

User-requested dev-lane enhancement; no backlog issue (a new dev-lane variant of
ADR-028, not a planned INT row). Extends ADR-028's offline clip pre-bake with an
ON-DEMAND path: a scripted question whose `text_tr` has no cached George clip is
synthesised via ElevenLabs at runtime through a DEV server route, cached
addressed by `sha256(text_tr)` (`protocols.dsl.clip_text_hash` — the ADR-028
manifest key), and played; a second request for the same text is a cache hit
that never dials the vendor again.

## Guardrails held
- Only compiled SCRIPTED question `text_tr` reaches the vendor: the mobile
  client accepts a nominal `ScriptedTr` producible solely from an
  `IntakeQuestion` (catalog composition, speech.ts); `requireScriptedTr` refuses
  any string that is not exactly a question's composition. Patient words are
  displayed, never synthesized (invariant 2/10).
- The DEVICE never holds the vendor key — generation goes through
  `services/api` `/dev/voice/george-clip`, which reads the key from its env
  (ADR-028 `TTS_ELEVENLABS_API_KEY`). Key absent → 503 fail-closed; the mobile
  falls back to the self-hosted TTS. Never a crash, never a blocked turn.
- DEV lane only (`INTAKE_DEV_GEORGE_TTS=explicit-yes`), never the PHI path or the
  `residency_tr` profile; invariant 19 intact (the self-hosted lane is unchanged
  and is what production uses). No vendor-FQDN literal enters the tree — the base
  URL is env-supplied (ADR-028), so `assert_no_vendor_calls.sh` stays green and
  NO in-tree egress-allow-list row is added.
- Invariant 22: `assert_speakable_tr` (server) and `assertSpeakableTr` (client)
  refuse any numeral before the wire; the vendor normaliser stays off (gateway).
- Invariant 3: the generated clip is agent speech (a scripted TTS clip), cached
  like the offline clips; it is never patient audio.

## RED → GREEN

### Server (pytest, `tests/api/test_dev_voice_george.py`)
RED (before `intake_api.dev_voice` existed):
```
$ uv run pytest tests/api/test_dev_voice_george.py -q
E   ModuleNotFoundError: No module named 'intake_api.dev_voice'
!!! Interrupted: 1 error during collection !!!    (exit 2)
```
GREEN (after the route + sha256 cache + fail-closed wiring):
```
$ uv run pytest tests/api/test_dev_voice_george.py
7 passed, 1 warning in 2.60s              (exit 0)
```
Covers: (a) cache miss → gateway called once → WAV cached + returned (`X-George-Cache: miss`);
(b) cache hit → gateway NOT called, same bytes (`X-George-Cache: hit`);
(c) unconfigured wiring / no key → 503 fail-closed; env wiring off without dev flag or key;
vendor error → 502 without echoing the key;
(d) numeral-bearing text refused (422 `not_speakable`) before any dial.
`ruff` + `mypy` clean on `dev_voice.py`.

### Mobile (vitest, `apps/mobile/src/lib/dialogue/georgeClip.test.ts`)
RED (before `georgeClip.ts` existed):
```
$ pnpm exec vitest run src/lib/dialogue/georgeClip.test.ts
Error: Cannot find module './georgeClip' ...
Test Files  1 failed (1) · Tests  no tests    (exit 1)
```
GREEN (after `georgeClip.ts` + the `clips.ts` wiring):
```
$ pnpm exec vitest run src/lib/dialogue/georgeClip.test.ts
Test Files  1 passed (1) · Tests  9 passed (9)   (exit 0)
```
Covers: the scripted-text guard (mint from a question, accept its own
composition, REFUSE non-scripted patient text); `fetchGeorgeClip` POSTs
`text_tr` to `/dev/voice/george-clip` and returns bytes, throws
`george_unavailable` on a non-2xx (server 503 / key absent);
(a) cache miss → George generator once, clip cached; (b) cache hit → generator
NOT called again; (c) George unavailable → falls back to the self-hosted lane,
no throw; null source → self-hosted directly.

Full dialogue suite: `240 passed`. Mobile `tsc --noEmit` exit 0; `eslint` clean.

## Not done here (flagged for human/security review)
- Touching the egress allow-list is security-sensitive (CLAUDE.md "stop and
  ask"). No in-tree allow-list literal was added because the vendor FQDN is a
  forbidden literal (`assert_no_vendor_calls.sh`) and ADR-028 keeps the base URL
  env-supplied. A dev deployment that enforces egress through the squid proxy
  would need the ElevenLabs host provisioned out-of-tree — a human decision.
- The KVKK Art. 9 transfer question and the ElevenLabs vendor terms remain the
  ADR-028 human blockers; this dev-lane variant does not resolve them.
