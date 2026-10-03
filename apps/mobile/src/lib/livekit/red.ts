/**
 * The RED path on the device (INT-103; CLAUDE.md invariant 21).
 *
 * "RED has three axes — route × register × location. The RED script is
 * PRE-POSITIONED on the device and triggered over the DATA channel — the RED
 * path touches no media transport."
 *
 * That sentence is the whole design of this module, and it has a concrete
 * consequence: the inbound data packet carries IDENTIFIERS AND AXES ONLY, and
 * the words the patient reads come from a catalog that was already on the
 * phone before the session started. So a RED renders correctly when the
 * microphone track is gone, the audio session is torn down, the SFU has
 * dropped us and the only thing still alive is the data channel. The
 * `renders with media torn down` test in voice.spec.ts pins exactly that.
 *
 * Everything here is PURE. Decoding is schema-constrained parsing of an
 * untrusted byte payload (invariant 14: data is never instructions) — an
 * unrecognised, malformed or under-specified message is REFUSED, never
 * coerced into a plausible RED and never into a plausible non-RED.
 *
 * Invariant 9: this module cannot originate a RED. `decodeRedTrigger` is the
 * only constructor of a RedTrigger in the app and its sole input is an
 * inbound packet. The client renders what the rules engine tells it; it holds
 * no rule, no threshold and no opinion about urgency.
 */
import type { RedTrigger } from "./types";

/** How a RED is told. Mirrors clinical_schemas.triage.RedRegister exactly. */
export type RedRegister = "ALERT" | "CALM" | "SILENT" | "DEFERRED_CLINICIAN";

/** What a RED tells the patient to do. Mirrors RedLocation exactly. */
export type RedLocation = "REMOTE" | "ON_SITE" | "UNKNOWN";

const REGISTERS: ReadonlySet<string> = new Set<RedRegister>([
  "ALERT",
  "CALM",
  "SILENT",
  "DEFERRED_CLINICIAN",
]);

const LOCATIONS: ReadonlySet<string> = new Set<RedLocation>(["REMOTE", "ON_SITE", "UNKNOWN"]);

/** Ids are ids: no spaces, no free text, so a rule id can never carry PHI. */
const ID_SHAPE = /^[a-z0-9][a-z0-9._-]{0,127}$/;

/**
 * One pre-positioned RED script, resolved from the compiled pack that shipped
 * with the app. The field names mirror protocols.dsl.LocationAction so the
 * pack compiler's output drops straight in without a translation layer.
 */
export interface RedScript {
  /** Action code, e.g. CALL_112, GO_TO_IN_HOUSE_ACIL. */
  readonly primary: string;
  /** Whether the pack authorises the 112 affordance for this action. */
  readonly show112: boolean;
  /** Patient-facing Turkish, action first, spoken/rendered verbatim. */
  readonly actionTr: string;
  /** Explicit do-not list. */
  readonly doNotsTr: readonly string[];
  /** Explanation — never a diagnosis. */
  readonly whyTr: string | null;
}

/** The on-device catalog: scriptId → script. Pre-positioned, never fetched. */
export type RedScriptCatalog = Readonly<Record<string, RedScript>>;

/**
 * What the UI renders for one RED. Produced only by `resolveRed`, so the
 * ON_SITE 112 rule cannot be bypassed by a caller assembling its own object.
 */
export interface RedPresentation {
  readonly ruleId: string;
  readonly register: RedRegister;
  readonly location: RedLocation;
  readonly script: RedScript;
  /**
   * Whether to render the 112 affordance. Under ON_SITE this is ALWAYS false:
   * "Under ON_SITE the 112 affordance is absent, not de-emphasised"
   * (invariant 21; files/04 §8.2 on_site_action_never_offers_112).
   */
  readonly show112: boolean;
}

/**
 * Decode one inbound data-channel packet into a RED trigger.
 *
 * Returns null for anything that is not an unambiguous, fully-specified RED
 * trigger — including a message that omits `register` or `location`. There is
 * no permitted default for either axis (invariant 21), so a message missing
 * one is a defect on the wire, not something to fill in from here.
 *
 * The payload is UTF-8 JSON. It is untrusted input: nothing in it is ever
 * executed, interpolated into a prompt, or used as anything but the four
 * fields below.
 */
export function decodeRedTrigger(payload: Uint8Array): RedTrigger | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(new TextDecoder().decode(payload));
  } catch {
    return null; // not JSON — refused, not guessed
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return null;
  }
  const message = parsed as Record<string, unknown>;
  if (message.kind !== "red_trigger") {
    return null; // some other agent message; not this module's business
  }
  const { ruleId, register, location, scriptId } = message;
  if (typeof ruleId !== "string" || !ID_SHAPE.test(ruleId)) {
    return null;
  }
  if (typeof scriptId !== "string" || !ID_SHAPE.test(scriptId)) {
    return null;
  }
  // No default for either axis: absent or unknown means refuse.
  if (typeof register !== "string" || !REGISTERS.has(register)) {
    return null;
  }
  if (typeof location !== "string" || !LOCATIONS.has(location)) {
    return null;
  }
  return {
    kind: "red_trigger",
    ruleId,
    register: register as RedRegister,
    location: location as RedLocation,
    scriptId,
  };
}

/**
 * The generic escalation's script ids (INT-453), one per location. These mirror
 * `intake_voice_runtime.talker.red_path.GENERIC_RED_SCRIPT_IDS`, and
 * tests/voice/test_red_winner.py pins the two together.
 */
export const GENERIC_RED_SCRIPT_IDS = {
  REMOTE: "base.generic_red.remote",
  ON_SITE: "base.generic_red.on_site",
  UNKNOWN: "base.generic_red.unknown",
} as const satisfies Record<RedLocation, string>;

/**
 * The generic escalation's words while none are signed: there are none. The
 * copy is `draft_needs_source` (INT-453 → the INT-432 clinical-decisions
 * register), so nothing is invented here. The RED still shows — ALERT, with
 * the location-correct affordance — and its words arrive the day a signed
 * generic script is compiled into the catalog under the ids above.
 */
const UNWORDED_GENERIC: RedScript = {
  primary: "GENERIC_ESCALATION",
  show112: true,
  actionTr: "",
  doNotsTr: [],
  whyTr: null,
};

/** The register until CD-24 (pending) says otherwise: the most conservative. */
export const DEFAULT_GENERIC_RED_REGISTER: RedRegister = "ALERT";

const GENERIC_IDS: ReadonlySet<string> = new Set(Object.values(GENERIC_RED_SCRIPT_IDS));

/**
 * How a generic RED is told. A trigger the server sent as the generic
 * escalation carries the server's register, which is CD-24's once that lands.
 * A RED the device could not resolve on its own is told in the default.
 */
function genericRegister(trigger: RedTrigger): RedRegister {
  return GENERIC_IDS.has(trigger.scriptId) ? trigger.register : DEFAULT_GENERIC_RED_REGISTER;
}

/**
 * The RED a patient sees when the trigger's own script is not on the device
 * (INT-453): never nothing. The register is the most conservative, ALERT. The
 * location is the trigger's own, so ON_SITE carries no 112. The words come
 * from the catalog's generic script when one is pre-positioned.
 */
export function genericRed(trigger: RedTrigger, catalog: RedScriptCatalog): RedPresentation {
  const script = catalog[GENERIC_RED_SCRIPT_IDS[trigger.location]] ?? UNWORDED_GENERIC;
  return {
    ruleId: trigger.ruleId,
    register: genericRegister(trigger),
    location: trigger.location,
    script,
    show112: trigger.location === "ON_SITE" ? false : script.show112,
  };
}

/**
 * Resolve a trigger against the pre-positioned catalog.
 *
 * Returns null when the script is not on the device. The caller shows
 * `genericRed` instead, and never invents clinical words (invariant 17: never
 * a plausible value).
 */
export function resolveRed(trigger: RedTrigger, catalog: RedScriptCatalog): RedPresentation | null {
  const script = catalog[trigger.scriptId];
  if (script === undefined) {
    return null;
  }
  return {
    ruleId: trigger.ruleId,
    register: trigger.register,
    location: trigger.location,
    script,
    // Defence in depth over the pack's own flag. The compiler already
    // refuses show_112 under ON_SITE; if a pack ever slipped through with
    // one, the patient standing in the hospital still must not be told to
    // call an ambulance. Clamping down is always safe; clamping up never is.
    show112: trigger.location === "ON_SITE" ? false : script.show112,
  };
}
