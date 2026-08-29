/**
 * INT-240 — the dev TTS lane as an ordered ladder, behind config.
 *
 * files/03 §4.9.1 rows 10-11 pin `openbmb/VoxCPM2` as the TTS for both the
 * cached-clip and the dynamic path; row 12, `freyavoice/Freya-TTS`, is the
 * low-footprint fallback selected at session start. Until INT-240 the client
 * hardcoded one port (8803, Freya) and had nowhere to put a second tier.
 *
 * So: VoxCPM2 serves on 8805, Freya keeps serving on 8803, and this module is
 * the seam between them. The order and the ports come from app.json
 * `extra.ttsLanes`; the built-in order is the default, not a hardcode you
 * have to edit code to change. First tier whose /health answers wins, and a
 * dead VoxCPM2 costs nothing but one failed probe.
 *
 * Deliberately NOT here: how a clip is chunked, shaped or assembled. That is
 * INT-237's `speechShaping.ts` on branch int-237-tts-quality, still unmerged.
 * This module owns the endpoint and the fallback and stops there, so the two
 * changes compose instead of fighting: `synthesizeOnLane` is the same POST
 * `synthesizeWav` performs, against a base this module resolved.
 *
 * Invariant 22 is tier-independent: `assertSpeakableTr` is re-used verbatim
 * from tts.ts and throws before any request leaves the app, whichever model
 * is about to answer. VoxCPM2's own normaliser is disabled server-side and
 * its daemon rejects digits too (files/03 §4.9.6) — this is the third of the
 * three guards, not the only one.
 */
import { assertSpeakableTr, type SynthesizeOptions } from "./tts";

export interface TtsLaneSpec {
  /** Stable id for logs and health output — "voxcpm2", "freya". */
  readonly id: string;
  readonly port: number;
}

/** A lane spec bound to one concrete host base. */
export interface TtsLaneBase {
  readonly id: string;
  readonly base: string;
}

/**
 * The default ladder: VoxCPM2 first (files/03 §4.9.1 rows 10-11), Freya
 * second (row 12). Overridable per install through app.json.
 */
export const DEFAULT_TTS_LANES: readonly TtsLaneSpec[] = Object.freeze([
  Object.freeze({ id: "voxcpm2", port: 8805 }),
  Object.freeze({ id: "freya", port: 8803 }),
]);

/**
 * Reads an app.json `extra.ttsLanes` value into a lane ladder. Absent or
 * empty means the default order; malformed throws, because a TTS lane that
 * quietly invents a port is worse than one that refuses to start.
 */
export function parseTtsLanes(raw: unknown): readonly TtsLaneSpec[] {
  if (raw === undefined || raw === null) {
    return DEFAULT_TTS_LANES;
  }
  if (!Array.isArray(raw)) {
    throw new Error("tts_lanes_malformed");
  }
  if (raw.length === 0) {
    return DEFAULT_TTS_LANES;
  }
  return raw.map((entry) => {
    if (typeof entry !== "object" || entry === null) {
      throw new Error("tts_lanes_malformed");
    }
    const { id, port } = entry as { id?: unknown; port?: unknown };
    if (typeof id !== "string" || id.length === 0) {
      throw new Error("tts_lanes_malformed");
    }
    if (typeof port !== "number" || !Number.isInteger(port) || port <= 0 || port > 65535) {
      throw new Error("tts_lanes_malformed");
    }
    return { id, port };
  });
}

/**
 * Every (tier, host) base to try, in order: the whole ladder for the first
 * host, then the whole ladder for the next. Tier order dominates host order —
 * a reachable Freya on the dev Mac must not beat a reachable VoxCPM2 there.
 */
export function laneCandidates(
  hostUri: string | undefined,
  extraHosts: readonly string[],
  lanes: readonly TtsLaneSpec[] = DEFAULT_TTS_LANES,
): TtsLaneBase[] {
  const hosts: string[] = [];
  if (hostUri) {
    const host = hostUri.split(":")[0];
    // tunnel mode gives an exp.direct name with no route back to the Mac
    if (!host.endsWith(".exp.direct")) {
      hosts.push(host);
    }
  }
  for (const host of extraHosts) {
    if (!hosts.includes(host)) {
      hosts.push(host);
    }
  }
  return lanes.flatMap((lane) =>
    hosts.map((host) => ({ id: lane.id, base: `http://${host}:${lane.port}` })),
  );
}

export interface LaneProbeOptions {
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

/**
 * First candidate whose /health answers 2xx wins; null when the whole ladder
 * is down. A transport error is "down", not a crash — the point of the ladder
 * is that the next tier gets its turn.
 */
export async function resolveTtsLane(
  candidates: readonly TtsLaneBase[],
  { timeoutMs = 1500, fetchImpl = fetch }: LaneProbeOptions = {},
): Promise<TtsLaneBase | null> {
  for (const candidate of candidates) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetchImpl(`${candidate.base}/health`, { signal: controller.signal });
      if (res.ok) {
        return candidate;
      }
    } catch {
      // unreachable tier — fall through to the next
    } finally {
      clearTimeout(timer);
    }
  }
  return null;
}

/** Default cap for one synthesis; both daemons answer in seconds. */
const SYNTHESIZE_TIMEOUT_MS = 30_000;

/**
 * POST /synthesize on a resolved lane. Identical wire contract on both tiers
 * — `{"text": ...}` in, WAV bytes out — which is what makes the fallback a
 * swap rather than a rewrite.
 */
export async function synthesizeOnLane(
  lane: TtsLaneBase,
  text: string,
  options: SynthesizeOptions = {},
): Promise<Uint8Array> {
  assertSpeakableTr(text); // invariant 22 — before any network call, every tier
  const { fetchImpl = fetch, timeoutMs = SYNTHESIZE_TIMEOUT_MS } = options;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetchImpl(`${lane.base}/synthesize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
      signal: controller.signal,
    });
    if (!res.ok) {
      throw new Error("tts_unavailable");
    }
    const bytes = new Uint8Array(await res.arrayBuffer());
    if (bytes.length === 0) {
      throw new Error("tts_empty_clip");
    }
    return bytes;
  } finally {
    clearTimeout(timer);
  }
}
