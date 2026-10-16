/**
 * The rules-engine hop on the device (INT-446; CLAUDE.md invariants 1, 21).
 *
 * Every bound answer — what the patient tapped, confirmed or typed, on the
 * typed StepFlow, the dialogue composer or the spoken turn — lands in the
 * session note through one reducer action, and this module carries the note's
 * answers to the deterministic rules engine (services/api `/v1/triage`,
 * packages/protocols/triage). The device holds no rule, no threshold and no
 * opinion about urgency: it sends the values it has bound and renders what
 * the engine answers.
 *
 * The answer is the data-channel packet itself — `{kind: "red_trigger",
 * ruleId, register, location, scriptId}` — and it is decoded by the one
 * schema-constrained decoder the LiveKit lane uses (`decodeRedTrigger`), so a
 * RED reaches the screen through exactly one parser whichever lane fired it.
 * Identifiers and axes only: the words come from the catalog fetched BEFORE
 * any evaluation could return a RED, never at RED time (invariant 21).
 *
 * Pure: the transport is injected. Nothing here logs, and nothing it returns
 * carries a slot value (invariant 6).
 */
import type { Answer } from "../intake/note";
import {
  decodeRedTrigger,
  type RedLocation,
  type RedScript,
  type RedScriptCatalog,
} from "../livekit/red";
import type { RedTrigger } from "../livekit/types";

export const EVALUATE_PATH = "/v1/triage/evaluate";
export const CATALOG_PATH = "/v1/triage/red-scripts";

/** One HTTP exchange, as the hop needs it. `body` null means GET. */
export type HopTransport = (
  path: string,
  body: string | null,
) => Promise<{ readonly status: number; readonly bytes: Uint8Array }>;

/** The UNKNOWN branch: the rule's one question and where each answer goes. */
export interface RedLocationQuestion {
  readonly askTr: string;
  readonly onYes: Exclude<RedLocation, "UNKNOWN">;
  readonly onNo: Exclude<RedLocation, "UNKNOWN">;
}

/** Everything a RED can show, on the device before the RED. */
export interface PrePositionedRed {
  readonly scripts: RedScriptCatalog;
  readonly questions: Readonly<Record<string, RedLocationQuestion>>;
}

/** Mirrors `intake_api.triage_rules.script_id`: rule id plus location. */
export function scriptIdFor(ruleId: string, location: RedLocation): string {
  return `${ruleId}.${location.toLowerCase()}`;
}

export type HopOutcome =
  | { readonly kind: "red"; readonly trigger: RedTrigger }
  | { readonly kind: "level"; readonly level: "GREEN" | "YELLOW" }
  /** Not evaluated: no served rule set, no session, a transport failure, or
   * an answer this decoder refuses. Never read as GREEN. */
  | { readonly kind: "unevaluated" };

/** The request body: bound values keyed by slot, the location axis, the clock. */
export interface TriageRequest {
  readonly location: RedLocation;
  readonly reference_time: string;
  readonly answers: Readonly<Record<string, string | readonly string[]>>;
}

/**
 * Project the note's answers onto the engine's slot map. `values` only —
 * never `words`, which is provenance and can never reach a rule (note.ts).
 * A single value is the value; several (a chips answer) are one list value.
 * An answer with no non-empty value was not bound and is left out.
 */
export function triageRequest(
  answers: readonly Answer[],
  location: RedLocation,
  referenceTime: Date,
): TriageRequest {
  const slots: Record<string, string | readonly string[]> = {};
  for (const answer of answers) {
    const values = answer.values.filter((value) => value.trim().length > 0);
    if (values.length === 0) {
      continue;
    }
    slots[answer.questionId] = values.length === 1 ? values[0] : values;
  }
  return { location, reference_time: referenceTime.toISOString(), answers: slots };
}

/** The same request, as a stable string: equal bodies need no second hop. */
export function requestKey(request: TriageRequest): string {
  const ordered = Object.keys(request.answers)
    .sort()
    .map((slot) => [slot, request.answers[slot]]);
  return JSON.stringify([request.location, ordered]);
}

function parse(bytes: Uint8Array): unknown {
  try {
    return JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    return null;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Send the bound answers to the engine and decode its answer. */
export async function evaluateBoundAnswers(
  transport: HopTransport,
  request: TriageRequest,
): Promise<HopOutcome> {
  let response: { status: number; bytes: Uint8Array };
  try {
    response = await transport(EVALUATE_PATH, JSON.stringify(request));
  } catch {
    return { kind: "unevaluated" };
  }
  if (response.status !== 200) {
    return { kind: "unevaluated" };
  }
  const trigger = decodeRedTrigger(response.bytes);
  if (trigger !== null) {
    return { kind: "red", trigger };
  }
  const body = parse(response.bytes);
  if (
    isRecord(body) &&
    body.kind === "triage_level" &&
    (body.level === "GREEN" || body.level === "YELLOW")
  ) {
    return { kind: "level", level: body.level };
  }
  // A red_trigger the decoder refused (a missing axis, an id with spaces) is
  // NOT a non-RED: it is unevaluated, and nothing is coerced either way.
  return { kind: "unevaluated" };
}

const LOCATED: ReadonlySet<unknown> = new Set(["REMOTE", "ON_SITE"]);

function decodeScript(value: unknown): RedScript | null {
  if (!isRecord(value)) {
    return null;
  }
  const { primary, show112, actionTr, doNotsTr, whyTr } = value;
  if (
    typeof primary !== "string" ||
    typeof show112 !== "boolean" ||
    typeof actionTr !== "string" ||
    actionTr.length === 0 ||
    !Array.isArray(doNotsTr) ||
    !doNotsTr.every((line) => typeof line === "string") ||
    !(whyTr === null || typeof whyTr === "string")
  ) {
    return null;
  }
  return { primary, show112, actionTr, doNotsTr: doNotsTr as string[], whyTr };
}

function decodeQuestion(value: unknown): RedLocationQuestion | null {
  if (!isRecord(value)) {
    return null;
  }
  const { askTr, onYes, onNo } = value;
  if (
    typeof askTr !== "string" ||
    askTr.length === 0 ||
    !LOCATED.has(onYes) ||
    !LOCATED.has(onNo)
  ) {
    return null;
  }
  return {
    askTr,
    onYes: onYes as RedLocationQuestion["onYes"],
    onNo: onNo as RedLocationQuestion["onNo"],
  };
}

/**
 * Decode the pre-positioned catalog. All or nothing: one malformed entry
 * refuses the whole catalog, because a partly-trusted RED script table is
 * not something to render clinical words from (invariant 14).
 */
export function decodeRedCatalog(bytes: Uint8Array): PrePositionedRed | null {
  const body = parse(bytes);
  if (!isRecord(body) || !isRecord(body.scripts) || !isRecord(body.questions)) {
    return null;
  }
  const scripts: Record<string, RedScript> = {};
  for (const [id, raw] of Object.entries(body.scripts)) {
    const script = decodeScript(raw);
    if (script === null) {
      return null;
    }
    scripts[id] = script;
  }
  const questions: Record<string, RedLocationQuestion> = {};
  for (const [id, raw] of Object.entries(body.questions)) {
    const question = decodeQuestion(raw);
    if (question === null) {
      return null;
    }
    questions[id] = question;
  }
  return { scripts, questions };
}

/** Fetch the catalog; null on any failure (the caller retries before the next hop). */
export async function fetchRedCatalog(transport: HopTransport): Promise<PrePositionedRed | null> {
  try {
    const response = await transport(CATALOG_PATH, null);
    return response.status === 200 ? decodeRedCatalog(response.bytes) : null;
  } catch {
    return null;
  }
}
