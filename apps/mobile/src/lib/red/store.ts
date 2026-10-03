/**
 * The one RED on the device and what its screen shows (INT-446; CLAUDE.md
 * invariants 10, 21; files/02 §5.3; ADR-033 via lib/motion/red.ts).
 *
 * A RED enters here from a rules-engine trigger — the HTTP hop's answer or a
 * LiveKit data-channel packet, both decoded by `decodeRedTrigger` — and the
 * screen model is derived from it and the pre-positioned catalog alone. No
 * audio, no navigator and no media transport is on this path, so a RED
 * renders with the microphone gone and the room dropped.
 *
 * Escalation only. A RED stays until the patient acts on it: a later GREEN
 * never clears it, nothing times it out, and a second RED replaces it only
 * when the first changed nothing on the patient's screen (DEFERRED_CLINICIAN)
 * and the second does — a clinician-only finding must not swallow one the
 * patient has to act on.
 *
 * Pure: no React Native import, so every register × location × answer
 * combination is node-testable. RedLayer.tsx renders `redScreen(...)`.
 */
import type { Answer } from "../intake/note";
import {
  GENERIC_RED_SCRIPT_IDS,
  genericRed,
  genericRedCopy,
  resolveRed,
  type RedLocation,
  type RedRegister,
} from "../livekit/red";
import type { RedTrigger } from "../livekit/types";
import {
  RED_MOTION,
  redAffordances,
  redPresentationMode,
  type LocationAnswer,
  type RedMotion,
} from "../motion/red";
import {
  evaluateBoundAnswers,
  fetchRedCatalog,
  requestKey,
  scriptIdFor,
  triageRequest,
  type HopOutcome,
  type HopTransport,
  type PrePositionedRed,
  type RedLocationQuestion,
} from "./hop";

/**
 * How long the device waits on an unanswered location question before it takes
 * the rule's no-answer branch (REMOTE, with the 112 control).
 *
 * UNSIGNED ENGINEERING VALUE. CD-24 keeps `no_answer_wait` draft_needs_source:
 * no source states a wait, and EK-4's ten minutes is a treatment target, not a
 * question timeout. CD-24 `fail_closed_while_draft` allows the device a wait in
 * the meantime only if it is recorded as unsigned, and fixes that on expiry the
 * branch is always REMOTE, never silence. It is recorded in
 * docs/evidence/INT-465.md. A physician decides the value before any real patient.
 */
export const UNSIGNED_LOCATION_NO_ANSWER_WAIT_MS = 30_000;

/** A catalog that cannot say CD-24's generic RED reached the store (INT-465). */
export class RedCatalogIncomplete extends Error {
  constructor() {
    super("the pre-positioned RED catalog cannot say the generic RED (CD-24)");
    this.name = "RedCatalogIncomplete";
  }
}

function assertGenericCopy(catalog: PrePositionedRed): void {
  if (
    genericRedCopy(catalog.scripts) === null ||
    catalog.questions[GENERIC_RED_SCRIPT_IDS.UNKNOWN] === undefined
  ) {
    throw new RedCatalogIncomplete();
  }
}

export interface RedState {
  readonly trigger: RedTrigger;
  readonly catalog: PrePositionedRed;
  readonly answer: LocationAnswer;
  /** Answer bound → RED presented, in ms, when the hop measured it. */
  readonly elapsedMs: number | null;
}

/** What the screen shows for the current RED. */
export type RedScreen =
  /** No RED, or one meant for the clinician only (patient screen unchanged). */
  | { readonly kind: "none" }
  /** UNKNOWN location: the rule's one question, verbatim, nothing else yet. */
  | {
      readonly kind: "ask";
      readonly mode: "rootLayer" | "inFlow";
      readonly register: RedRegister;
      readonly askTr: string;
      readonly motion: RedMotion;
    }
  /**
   * The action, verbatim from the rule's `tr`. A generic RED (INT-453) is the
   * one case that can still be UNKNOWN: there is no question copy to ask, so
   * no location action — and no 112 — is offered. Its `actionTr` is empty
   * until a signed generic script is on the device.
   */
  | {
      readonly kind: "act";
      readonly mode: "rootLayer" | "inFlow";
      readonly register: RedRegister;
      readonly location: RedLocation;
      readonly actionTr: string;
      readonly doNotsTr: readonly string[];
      readonly whyTr: string | null;
      /** Mounted only when the location allows it; never under ON_SITE. */
      readonly call112: boolean;
      readonly motion: RedMotion;
    };

const NONE: RedScreen = { kind: "none" };

/** The screen for one RED state. Pure. */
export function redScreen(state: RedState | null): RedScreen {
  if (state === null) {
    return NONE;
  }
  const { trigger, catalog, answer } = state;
  const mode = redPresentationMode(trigger.register);
  if (mode === "none") {
    return NONE;
  }
  let located: Exclude<RedLocation, "UNKNOWN">;
  let scriptId: string;
  if (trigger.location === "UNKNOWN") {
    const question = catalog.questions[trigger.scriptId];
    if (question === undefined) {
      return genericScreen(trigger, catalog, answer);
    }
    if (answer === "unanswered") {
      // No location action — and so no 112 — mounts before the answer.
      return {
        kind: "ask",
        mode,
        register: trigger.register,
        askTr: question.askTr,
        motion: RED_MOTION,
      };
    }
    // The rule's own branch targets decide where each answer goes.
    located = branchFor(question, answer);
    scriptId = scriptIdFor(trigger.ruleId, located);
  } else {
    located = trigger.location;
    scriptId = trigger.scriptId;
  }
  const presentation = resolveRed({ ...trigger, location: located, scriptId }, catalog.scripts);
  if (presentation === null) {
    return genericScreen({ ...trigger, location: located }, catalog, answer);
  }
  return {
    kind: "act",
    mode,
    register: trigger.register,
    location: located,
    actionTr: presentation.script.actionTr,
    doNotsTr: presentation.script.doNotsTr,
    whyTr: presentation.script.whyTr,
    call112: redAffordances(presentation, answer).call112,
    motion: RED_MOTION,
  };
}

/** The branch the rule's own question takes for this answer (files/04 §8.1 rule 7). */
function branchFor(
  question: RedLocationQuestion,
  answer: Exclude<LocationAnswer, "unanswered">,
): Exclude<RedLocation, "UNKNOWN"> {
  if (answer === "inHospital") {
    return question.onYes;
  }
  return answer === "noAnswer" ? question.onNoAnswer : question.onNo;
}

/**
 * The generic escalation (INT-453; CD-24; livekit/red.ts `genericRed`). A RED
 * whose own script or question is not on this device is still a RED on screen:
 * - Register: the trigger's own (CD-24 carry_engine_register). ALERT and CALM
 *   paint the root layer, SILENT renders in the flow with no headline (CD-24's
 *   meanwhile for SILENT), and DEFERRED_CLINICIAN never gets here.
 * - Location: the trigger's own, so there is no 112 under ON_SITE.
 * - UNKNOWN: it asks CD-24's "Şu anda hastanede misiniz?" first, with no 112
 *   until the answer; with no question copy it offers none at all
 *   (files/04 §8.1 rule 7: never resolved by guessing).
 * - Words: CD-24's generic copy, or none. Nothing is invented.
 */
function genericScreen(
  trigger: RedTrigger,
  catalog: PrePositionedRed,
  answer: LocationAnswer,
): RedScreen {
  const mode = redPresentationMode(trigger.register);
  if (mode === "none") {
    return NONE; // unreachable from redScreen, which answers DEFERRED_CLINICIAN first
  }
  // INT-465: never wordless — a catalog without the generic copy fails here.
  const copy = genericRedCopy(catalog.scripts);
  if (copy === null) {
    throw new RedCatalogIncomplete();
  }
  let location: Exclude<RedLocation, "UNKNOWN">;
  if (trigger.location === "UNKNOWN") {
    const question = catalog.questions[GENERIC_RED_SCRIPT_IDS.UNKNOWN];
    if (question === undefined) {
      throw new RedCatalogIncomplete();
    }
    if (answer === "unanswered") {
      // CD-24's verdict: ask first, with no 112 before the answer.
      return {
        kind: "ask",
        mode,
        register: trigger.register,
        askTr: question.askTr,
        motion: RED_MOTION,
      };
    }
    location = branchFor(question, answer);
  } else {
    location = trigger.location;
  }
  const presentation = genericRed({ ...trigger, location }, copy);
  return {
    kind: "act",
    mode,
    register: presentation.register,
    location,
    actionTr: presentation.script.actionTr,
    doNotsTr: presentation.script.doNotsTr,
    whyTr: presentation.script.whyTr,
    call112: redAffordances(presentation, answer).call112,
    motion: RED_MOTION,
  };
}

/**
 * Whether a RED in this state takes the patient out of the dialogue: the
 * agent stops speaking and the microphone closes. True whenever the patient
 * is shown a RED (SILENT included — "No audio, ever"), the generic RED
 * included; false for DEFERRED_CLINICIAN, which changes nothing on the
 * patient's side.
 */
export function redStopsDialogue(state: RedState | null): boolean {
  const kind = redScreen(state).kind;
  return kind === "ask" || kind === "act";
}

export interface RedStore {
  getSnapshot: () => RedState | null;
  subscribe: (listener: () => void) => () => void;
  /** A rules-engine trigger arrived. Escalation only (see the header). */
  present: (trigger: RedTrigger, catalog: PrePositionedRed, elapsedMs?: number | null) => void;
  /** The patient answered the one location question, or it went unanswered (`noAnswer`). */
  answerLocation: (answer: Exclude<LocationAnswer, "unanswered">) => void;
}

export function createRedStore(): RedStore {
  let state: RedState | null = null;
  const listeners = new Set<() => void>();
  const emit = () => {
    for (const listener of listeners) {
      listener();
    }
  };
  return {
    getSnapshot: () => state,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    present: (trigger, catalog, elapsedMs = null) => {
      // INT-465: a catalog that cannot say the generic RED fails at every
      // location (CD-24 generic_red_silent_is_never_wordless).
      assertGenericCopy(catalog);
      if (redStopsDialogue(state)) {
        return; // a RED the patient sees stays until they act on it
      }
      const next: RedState = { trigger, catalog, answer: "unanswered", elapsedMs };
      if (state !== null && !redStopsDialogue(next)) {
        return; // the first one stands: the second shows the patient nothing new
      }
      state = next;
      emit();
    },
    answerLocation: (answer) => {
      if (state === null || state.trigger.location !== "UNKNOWN" || state.answer !== "unanswered") {
        return; // one question, answered once
      }
      state = { ...state, answer };
      emit();
    },
  };
}

/**
 * CD-24 `generic_red_stops_intake`, on the device (INT-465): the dialogue stream
 * is frozen at its length when a RED first stops the dialogue. Pure: the caller
 * keeps the result and passes it back on every render.
 */
export function dialogueFrozenAt(
  previous: number | null,
  stopsDialogue: boolean,
  length: number,
): number | null {
  if (previous !== null) {
    return previous;
  }
  return stopsDialogue ? length : null;
}

/** What of the dialogue stream may still show: nothing that arrived after the RED. */
export function dialogueShown<T>(stream: readonly T[], frozenAt: number | null): readonly T[] {
  return frozenAt === null ? stream : stream.slice(0, frozenAt);
}

/** The app's one RED store. */
export const redStore: RedStore = createRedStore();

export interface RedHopOptions {
  readonly transport: HopTransport;
  readonly store: RedStore;
  /** Monotonic-enough ms clock for the answer→RED measurement. */
  readonly now: () => number;
  /** The session's reference time, stamped once per visit. */
  readonly clock: () => Date;
}

export interface RedHop {
  /** One visit's bound answers changed. Resolves once the engine has answered. */
  onAnswers: (
    visitId: string,
    answers: readonly Answer[],
    location: RedLocation,
  ) => Promise<HopOutcome>;
}

/**
 * The controller between the note and the engine. Equal requests are sent
 * once; the catalog is fetched before the first evaluation and retried
 * before the next one until it arrives, so it is always on the device
 * before any RED it could render.
 */
export function createRedHop({ transport, store, now, clock }: RedHopOptions): RedHop {
  let catalog: PrePositionedRed | null = null;
  const lastKey = new Map<string, string>();
  const referenceTime = new Map<string, Date>();
  return {
    onAnswers: async (visitId, answers, location) => {
      const startedAt = now();
      let reference = referenceTime.get(visitId);
      if (reference === undefined) {
        reference = clock();
        referenceTime.set(visitId, reference);
      }
      const request = triageRequest(answers, location, reference);
      if (Object.keys(request.answers).length === 0) {
        return { kind: "unevaluated" };
      }
      const key = requestKey(request);
      if (lastKey.get(visitId) === key) {
        return { kind: "unevaluated" };
      }
      lastKey.set(visitId, key);
      catalog ??= await fetchRedCatalog(transport);
      // The words before the verdict: with no catalog on the device the
      // answers are not sent, so a RED can never arrive that this device
      // cannot render (invariant 21). Not evaluated is retried next change.
      const outcome: HopOutcome =
        catalog === null ? { kind: "unevaluated" } : await evaluateBoundAnswers(transport, request);
      if (outcome.kind === "unevaluated") {
        lastKey.delete(visitId);
      }
      if (outcome.kind === "red" && catalog !== null) {
        store.present(outcome.trigger, catalog, now() - startedAt);
      }
      return outcome;
    },
  };
}
