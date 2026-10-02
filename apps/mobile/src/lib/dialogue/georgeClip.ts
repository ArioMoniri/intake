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
 * POST one scripted question text to the dev George route and return the audio
 * bytes (a WAV the server wrapped around the vendor's PCM).
 *
 * Throws `george_unavailable` on any non-2xx (the server answers 503 when the
 * key is absent, 502 when the vendor is unreachable), an empty body, or a
 * transport error — every one of which means "fall back to the self-hosted
 * lane". Only a {@link ScriptedTr} may be sent, so no patient text can leave
 * the app through this call.
 *
 * The body is `{ text_tr, delivery_context }` (INT-415). A `"red"` context is
 * never sent: RED audio is pre-positioned on the device and never fetched on
 * demand (invariant 21), and the server refuses it too.
 */
export async function fetchGeorgeClip(
  base: string,
  text: ScriptedTr,
  options: GeorgeFetchOptions = {},
): Promise<Uint8Array> {
  assertSpeakableTr(text); // defence in depth — no numeral crosses, ever
  const {
    fetchImpl = fetch,
    timeoutMs = GEORGE_TIMEOUT_MS,
    signal,
    context = DEFAULT_DELIVERY_CONTEXT,
  } = options;
  if (context === "red") {
    throw new Error("george_unavailable");
  }
  const controller = new AbortController();
  const stop = () => controller.abort();
  signal?.addEventListener("abort", stop);
  const timer = setTimeout(stop, timeoutMs);
  try {
    const res = await fetchImpl(`${base}${GEORGE_CLIP_PATH}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text_tr: text, delivery_context: context }),
      signal: controller.signal,
    });
    if (!res.ok) {
      throw new Error("george_unavailable");
    }
    const bytes = new Uint8Array(await res.arrayBuffer());
    if (bytes.length === 0) {
      throw new Error("george_unavailable");
    }
    return bytes;
  } catch (error) {
    // transport, abort, or the explicit throw above — all mean "unavailable,
    // fall back". Never surface the underlying error (it could name the host).
    throw error instanceof Error && error.message === "george_unavailable"
      ? error
      : new Error("george_unavailable");
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
 */
export function georgePreferringSynth(
  george: GeorgeGenerator | null,
  fallback: SelfHostedSynth,
): (text: ScriptedTr, context?: DeliveryContext) => Promise<Uint8Array> {
  return async (text, context = DEFAULT_DELIVERY_CONTEXT) => {
    if (george !== null) {
      try {
        return await george(text, context);
      } catch {
        // any George failure degrades to a worse voice, never to a dead turn —
        // the same trade the self-hosted ladder makes one level down (ttsLane).
      }
    }
    return fallback(text);
  };
}
