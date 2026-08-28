# LiveKit dev tier (INT-090) — and what production residency needs instead

## Dev tier: what exists

- `infra/docker-compose.dev.yml` service `livekit` (image
  `livekit/livekit-server:v1.13.6`, Apache-2.0 verified from the raw LICENSE
  blob at that tag), behind the `livekit` compose profile — the unit lane
  never boots it. Start it only when driving a real voice session:

  ```bash
  docker compose -f infra/docker-compose.dev.yml --profile livekit up -d --wait
  ```

  `make dev` deliberately does not include the profile — same precedent as
  `clamav` (INT-120).

- Config: `infra/livekit/livekit-dev.yaml`. Rooms are ephemeral
  (`empty_timeout: 300`, `departure_timeout: 20`, auto-create), audio-only
  (`audio/opus` is the sole enabled codec), and recording is structurally
  impossible: no redis bus (egress/ingress workers would have nothing to
  register against), no ingress/webhook block, no writable volume on the
  container. `tests/voice/test_audio_retention_guard.py` parses both files
  and fails on any drift (invariant 3).

- Keys: `LIVEKIT_KEYS` env with a dev-only default in the compose file. The
  token-minting side (`intake_platform.room_tokens`) reads
  `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET`; in prod mode it refuses
  dev-shaped material (invariant 14 — the production pair comes from
  OpenBao and never enters a committed file).

- TURN: the **embedded** LiveKit TURN server, UDP/3478 only. That is the
  honest single-host dev tier: no certificates, no TCP/TLS listener, media
  and relay on one loopback-published host.

- Tokens: `intake_platform.room_tokens.mint_room_token(session_id, identity,
  now)` — HS256 JWT, TTL ≤ 600 s, room `intake-<session uuid>`, grants
  exactly `roomJoin + canPublish(sources: microphone) + canSubscribe`,
  `canPublishData` pinned to explicit `false`. `tests/voice/
  test_room_tokens.py` decodes and asserts the surface.

## Production residency: what is REQUIRED instead (do not grow the dev tier)

Per files/03 §4.4/§4.4b/§4.9 and files/00 §2 (D11), the production shape is
different in kind, not degree:

1. **SFU self-hosted in Türkiye.** LiveKit Cloud has no Turkish region, so we
   operate the Apache-2.0 server ourselves — which makes us the TURN operator
   too. Residency is a latency *win*: −39 ms p50 / −47 ms p95 media-only
   versus a Frankfurt SFU, −156/−188 once the models move too.
2. **coturn co-located in the same İstanbul PoP as the SFU** (not the
   embedded dev TURN): offer `turn:` UDP, `turn:` TCP/443 and `turns:`
   TLS/443 with real certificates. TURN in a different PoP than the SFU is
   never acceptable (+39/+47 ms).
3. **TCP/TLS relay selection is a degradation trigger (T4), not a success** —
   detect via `RTCIceCandidatePair.relayProtocol` and wire it into the
   files/03 §4.5b policy.
4. **Keys from OpenBao only** (invariant 14), rotated; no `LIVEKIT_KEYS` env
   defaults anywhere. Signed images and admission control per files/10.
5. **Egress/ingress stay non-deployed.** No egress workers, no redis bus
   config on the media plane beyond what multi-node SFU routing itself
   requires; if a redis bus ever arrives for SFU clustering, the
   audio-retention guard must be extended first so recording stays refused
   (invariant 3) — that is a stop-and-ask change, not a drive-by.
6. **AWS İstanbul Local Zone (`eu-central-1-ist-1a`) fits the SFU + TURN +
   API tier** but has no GPU families; physical residency ≠ legal residency
   (control plane Frankfurt, operator AWS EMEA SARL) — KVKK Art. 9 is a
   counsel question. The narrow testable claim stays: audio bytes never
   leave TR on the media path.
7. **Gate `residency_tr` infra on a signed GPU capacity contract, never on a
   date** (00 §2: GPU supply in Türkiye is thin).
