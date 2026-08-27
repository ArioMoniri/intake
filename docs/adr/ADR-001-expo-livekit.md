# ADR-001 · Expo + LiveKit for realtime voice

Status: Accepted

## Context

The product is a Turkish-first, mobile-first realtime voice intake. It needs duplex audio with barge-in, a data channel for RED delivery, accessibility as a release blocker (02 §8.2), and native modules for AGC-off capture, HealthKit/Health Connect and attestation. RN uses the real platform accessibility tree; Flutter synthesises one over a canvas, and 02 §5.3 binds us to render 112 as large selectable OS text.

## Decision

The mobile app is Expo (SDK 57, dev builds, New Architecture); the realtime transport and agent runtime are LiveKit (self-hosted server + LiveKit Agents 1.7.0 in Python). No bare RN, no second transport stack.

## Consequences

One audio pipeline to certify; LiveKit's SFU keeps participant tracks separate by construction, which resolves agent-vs-patient attribution with zero models (00 §2). Costs: Expo module gaps (audio-session control needs react-native-audio-api; attestation/DPoP need a first-party config-plugin, 4–6 wk). Enforced by the runtime invariant suite (03 §4.6).
