/**
 * Dev-lane George (ElevenLabs) on-demand question clips — CLIENT half of
 * ADR-028's on-demand variant. Pure and node-testable: no expo imports here
 * (the host resolution + `__DEV__` gating live in clips.ts).
 *
 * What this adds. ADR-028 pre-bakes the FIXED scripted set into clips at build
 * time; a scripted question with no cached George clip today falls to the
 * self-hosted TTS. This client asks a DEV server route to synthesise that one
 * scripted question in George's voice on demand, so dynamically-selected
 * scripted questions (e.g. a department pack) get George's voice without
 * pre-baking every one — and then it degrades to the self-hosted lane on any
 * failure, so a turn is never blocked.
 *
 * The two hard guarantees this module is responsible for:
 *
 *  1. **The device never holds the vendor key.** This client only POSTs text to
 *     the dev server route (`/dev/voice/george-clip`); the key lives in the
 *     server's environment (services/api dev_voice.py). There is no key here.
 *
 *  2. **Patient words never reach the vendor.** {@link fetchGeorgeClip} and
 *     {@link georgePreferringSynth} accept only a nominal {@link ScriptedTr},
 *     which is producible solely from an `IntakeQuestion` via the catalog
 *     composer (speech.ts). A plain `string` — a patient answer — is not
 *     assignable, and {@link requireScriptedTr} refuses at runtime any string
 *     that is not exactly a question's scripted composition. Patient words are
 *     DISPLAYED, never synthesized (the invariant 2/10 posture speech.ts
 *     already documents); this makes that a checked fact on the George path.
 *
 * Invariant 22 is enforced here too: `assertSpeakableTr` throws before any
 * request leaves the app, and the server refuses a numeral again.
 */
import type { IntakeQuestion } from "../intake/questions";
import { DEFAULT_DELIVERY_CONTEXT, type DeliveryContext } from "./deliveryContext";
import { questionSpeechTr } from "./speech";
import { assertSpeakableTr } from "./tts";

/** The dev server route the mobile client POSTs scripted text to. Matches
 * `intake_api.dev_voice.GEORGE_CLIP_PATH`. */
export const GEORGE_CLIP_PATH = "/dev/voice/george-clip";

/** How long one on-demand generation may take before the client gives up and
 * falls back. Cloud synthesis of one short scripted sentence is well inside
 * this; a slower answer is treated as unavailable rather than holding the turn. */
export const GEORGE_TIMEOUT_MS = 8000;

/**
 * Text that is provably a scripted-question composition. The ONLY producers are
 * the constructors below, so a plain string (a patient answer) is not
 * assignable to it — which is what keeps patient words off the vendor path.
 */
export type ScriptedTr = string & { readonly __brand: "ScriptedTr" };

/**
 * Mint a {@link ScriptedTr} from a scripted question: compose it from the
 * catalog (speech.ts), past the invariant-22 numeral guard. This is the single
 * intended way to obtain scripted text for the George path.
 */
export function scriptedQuestionTr(question: IntakeQuestion): ScriptedTr {
  const text = questionSpeechTr(question);
  assertSpeakableTr(text); // invariant 22 — never a numeral to a TTS
  return text as ScriptedTr;
}

/**
 * Runtime guard for a caller holding a candidate string: refuse unless it is
 * EXACTLY this question's scripted composition. Patient words never are, so a
 * patient answer routed here throws rather than reaching the vendor. This is
 * what makes "patient text cannot reach the generator" a runtime fact and not
 * only a type.
 */
export function requireScriptedTr(candidate: string, question: IntakeQuestion): ScriptedTr {
  if (candidate !== questionSpeechTr(question)) {
    throw new Error("george_not_scripted");
  }
  assertSpeakableTr(candidate);
  return candidate as ScriptedTr;
}

/**
 * Why a George request did not serve (INT-440) — a closed set, so it can be a
 * dev-banner token and a metric label without ever carrying the host, the
 * text or a server narrative (invariant 6).
 */
export const GEORGE_MISSES = [
  /** No George source in this build (production, or the dev source is off). */
  "off",
  /** No API base answered. */
  "no_host",
  /** No authenticated patient session on the device to sign the request. */
  "no_session",
  /** 401/403 — the route refused the credentials (INT-326 requires a patient). */
  "unauthorized",
  /** 404 — the host does not mount the dev route (any `prod*` INTAKE_ENV). */
  "not_mounted",
  /** 422 — off-catalogue text, a numeral, or a pinned delivery context. */
  "refused",
  /** 429 — the per-patient budget. */
  "rate_limited",
  /** 502 — the vendor refused or could not be reached. */
  "vendor",
  /** 503 — no key, flag, catalogue or budget store on the server. */
  "unconfigured",
  /** Any other non-2xx. */
  "status",
  /** A 2xx with no audio in it. */
  "empty",
  /** The client gave up waiting. */
  "timeout",
  /** The request never completed. */
  "transport",
] as const;

export type GeorgeMiss = (typeof GEORGE_MISSES)[number];

/**
 * The one error the George path throws. Its message stays `george_unavailable`
 * — "fall back" is still the only thing a caller does with it — and `reason`
 * says why, for the dev banner and the lane metric.
 */
export class GeorgeUnavailable extends Error {
  readonly reason: GeorgeMiss;

  constructor(reason: GeorgeMiss) {
    super("george_unavailable");
    this.reason = reason;
  }
}

/** The closed-set reason for a non-2xx answer from the George route. */
export function georgeMissForStatus(status: number): GeorgeMiss {
  switch (status) {
    case 401:
    case 403:
      return "unauthorized";
    case 404:
      return "not_mounted";
    case 422:
      return "refused";
    case 429:
      return "rate_limited";
    case 502:
      return "vendor";
    case 503:
      return "unconfigured";
    default:
      return "status";
  }
}

/** The reason behind any George failure; a stray error is a transport one. */
export function georgeMissOf(error: unknown): GeorgeMiss {
  return error instanceof GeorgeUnavailable ? error.reason : "transport";
}

/**
 * How a George request reaches the API: a route PATH and a request, answered
 * with a Response. The device's transport is the DPoP-bound `authedFetch`
 * (clips.ts), which resolves the base and signs the request — the route has
 * required an authenticated patient since INT-326, and an anonymous POST is
 * what made every George request a silent 401 (INT-440).
 */
export type GeorgeTransport = (path: string, init: RequestInit) => Promise<Response>;

export interface GeorgeFetchOptions {
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
  signal?: AbortSignal;
  /** How the utterance is delivered (INT-415); default `"routine"`. The server
   * maps it to its own delivery profile — the device never holds a voice
   * setting, only this label. It never changes the words. */
  context?: DeliveryContext;
}

/**
 * POST one scripted question text to the dev George route at a known base and
 * return the audio bytes — {@link fetchGeorgeClipVia} over a plain fetch. It
 * sends no credentials, so a mounted route answers it 401; the device uses
 * the authenticated transport instead.
 */
export async function fetchGeorgeClip(
  base: string,
  text: ScriptedTr,
  options: GeorgeFetchOptions = {},
): Promise<Uint8Array> {
  const { fetchImpl = fetch, ...rest } = options;
  return fetchGeorgeClipVia((path, init) => fetchImpl(`${base}${path}`, init), text, rest);
}

/**
 * POST one scripted question text to the dev George route through `transport`
 * and return the audio bytes (a WAV the server wrapped around the vendor's PCM).
 *
 * Throws {@link GeorgeUnavailable} on any non-2xx, an empty body, a timeout or
 * a transport error — every one of which means "fall back to the self-hosted
 * lane" — with the closed-set reason attached. Only a {@link ScriptedTr} may
 * be sent, so no patient text can leave the app through this call.
 *
 * The body is `{ text_tr, delivery_context }` (INT-415). A `"red"` context is
 * never sent: RED audio is pre-positioned on the device and never fetched on
 * demand (invariant 21), and the server refuses it too.
 */
export async function fetchGeorgeClipVia(
  transport: GeorgeTransport,
  text: ScriptedTr,
  options: Omit<GeorgeFetchOptions, "fetchImpl"> = {},
): Promise<Uint8Array> {
  assertSpeakableTr(text); // defence in depth — no numeral crosses, ever
  const { timeoutMs = GEORGE_TIMEOUT_MS, signal, context = DEFAULT_DELIVERY_CONTEXT } = options;
  if (context === "red") {
    throw new GeorgeUnavailable("refused");
  }
  const controller = new AbortController();
  let timedOut = false;
  const stop = () => controller.abort();
  signal?.addEventListener("abort", stop);
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  try {
    const res = await transport(GEORGE_CLIP_PATH, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text_tr: text, delivery_context: context }),
      signal: controller.signal,
    });
    if (!res.ok) {
      throw new GeorgeUnavailable(georgeMissForStatus(res.status));
    }
    const bytes = new Uint8Array(await res.arrayBuffer());
    if (bytes.length === 0) {
      throw new GeorgeUnavailable("empty");
    }
    return bytes;
  } catch (error) {
    // Never surface the underlying error (it could name the host): only the
    // closed-set reason leaves this function.
    if (timedOut) {
      throw new GeorgeUnavailable("timeout");
    }
    throw error instanceof GeorgeUnavailable ? error : new GeorgeUnavailable("transport");
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", stop);
  }
}

/** Generates one scripted clip in George's voice, delivered per `context`
 * (INT-415). `null` means "no George source" (prod, or the dev route
 * unconfigured) — the caller uses only the fallback. Accepts a
 * {@link ScriptedTr}, never a bare string. */
export type GeorgeGenerator = (text: ScriptedTr, context?: DeliveryContext) => Promise<Uint8Array>;

/** The self-hosted per-clip synthesizer George degrades to (ttsLane). */
export type SelfHostedSynth = (text: string) => Promise<Uint8Array>;

/** Which lane produced one clip, and — when it was not George — why (INT-440).
 * `elevenlabs_bundled` is a clip rendered offline in George's voice and played
 * from the app bundle (bundledClips.ts); no synthesizer ever reports it. */
export type ClipLaneOutcome =
  | { lane: "george" }
  | { lane: "elevenlabs_bundled" }
  | { lane: "self_hosted"; georgeMiss: GeorgeMiss };

/** A clip's outcome as the session keeps it: a fallback also names the
 * self-hosted tier(s) that spoke (ttsLane ids — `voxcpm2`, `freya`). */
export type ClipLaneRecord =
  | { lane: "george" }
  | { lane: "elevenlabs_bundled" }
  | { lane: "self_hosted"; georgeMiss: GeorgeMiss; tiers: readonly string[] };

/**
 * A clip synthesizer that PREFERS George for scripted text and falls back to
 * the self-hosted lane on any George failure (unconfigured, unavailable,
 * timeout). The scripted brand travels with the value, so only catalog-composed
 * text can reach the vendor generator; the fallback takes a plain string
 * because a `ScriptedTr` is one.
 *
 * The delivery context is per utterance (INT-415): the returned synthesizer
 * takes it next to the text, defaults it to `"routine"`, and forwards it to
 * George. The self-hosted fallback has no delivery controls today, so it takes
 * the text alone (docs/voice/on-prem-tts-wiring.md).
 *
 * INT-440: the fallback is no longer silent. `onOutcome` hears, once per clip
 * that was actually produced, which lane produced it and why George did not.
 */
export function georgePreferringSynth(
  george: GeorgeGenerator | null,
  fallback: SelfHostedSynth,
  onOutcome?: (outcome: ClipLaneOutcome) => void,
): (text: ScriptedTr, context?: DeliveryContext) => Promise<Uint8Array> {
  return async (text, context = DEFAULT_DELIVERY_CONTEXT) => {
    let georgeMiss: GeorgeMiss = "off";
    if (george !== null) {
      try {
        const bytes = await george(text, context);
        onOutcome?.({ lane: "george" });
        return bytes;
      } catch (error) {
        // any George failure degrades to a worse voice, never to a dead turn —
        // the same trade the self-hosted ladder makes one level down (ttsLane).
        georgeMiss = georgeMissOf(error);
      }
    }
    const bytes = await fallback(text);
    onOutcome?.({ lane: "self_hosted", georgeMiss });
    return bytes;
  };
}
