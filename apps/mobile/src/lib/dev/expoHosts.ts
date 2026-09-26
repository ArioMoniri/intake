/**
 * Reads the Metro hostUri and the app.json `extra.asrHosts` list (one list —
 * both dev daemons sit on the same box behind the same Mac) and derives the
 * candidate bases for a given port. Kept apart from hosts.ts so the pure
 * helpers stay node-testable without an expo import.
 *
 * INT-243 adds the TTS ladder, which is a list of (tier, port) pairs rather
 * than a single port: `extra.ttsLanes`, defaulting to VoxCPM2 8805 then
 * Freya 8803. Same hosts, same probe, one more dimension.
 *
 * Both walks are dev-only (`devLanCandidates(__DEV__, …)`): a release build
 * probes no LAN lane for ASR, extract or TTS (INT-328's rule, audit F01/F17).
 */
import Constants from "expo-constants";

import { laneCandidates, parseTtsLanes, type TtsLaneBase } from "../dialogue/ttsLane";
import { devLanCandidates, serviceCandidates } from "./hosts";

/** The (ASR, extract) bases to probe for `port`; none in a release build. */
export function configuredServiceCandidates(port: number): string[] {
  return devLanCandidates(__DEV__, () => {
    const extra = (Constants.expoConfig?.extra ?? {}) as { asrHosts?: string[] };
    return serviceCandidates(Constants.expoConfig?.hostUri, extra.asrHosts ?? [], port);
  });
}

/** Every (TTS tier, host) base to probe, tier order dominating host order;
 * none in a release build. */
export function configuredTtsLaneCandidates(): TtsLaneBase[] {
  return devLanCandidates(__DEV__, () => {
    const extra = (Constants.expoConfig?.extra ?? {}) as {
      asrHosts?: string[];
      ttsLanes?: unknown;
    };
    return laneCandidates(
      Constants.expoConfig?.hostUri,
      extra.asrHosts ?? [],
      parseTtsLanes(extra.ttsLanes),
    );
  });
}
