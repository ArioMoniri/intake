/**
 * INT-582 (D36) — enrolling a passkey and stepping up with it, as pure
 * orchestration over injected ports (the native module and the server), so
 * every branch is vitest-covered without a phone or a network.
 *
 * Enrolment runs only on an OTP-verified session (the server refuses the
 * dev-bearer tier). A step-up for one action asks the server first: a patient
 * without a passkey is told so (`otp_session`) and is never locked out; a
 * patient with one asserts, and the server returns a single-use grant for that
 * action on this device session. A refusal carries the manual path the server
 * names (KVKK m.11(1)(g)); a cancelled sheet is the patient's own choice and
 * is reported as such, never as a refusal.
 *
 * Nothing here logs, stores or displays a challenge, a credential or a grant.
 */
import {
  type CreationOptions,
  type RequestOptions,
  type StepUpAction,
  guardCreationOptions,
  guardStepUpOffer,
} from "./rp";

/** The registration response the native module returns (WebAuthn JSON). */
export interface RegistrationCredential {
  id: string;
  rawId: string;
  type: "public-key";
  response: { clientDataJSON: string; attestationObject: string };
}

/** The assertion response the native module returns (WebAuthn JSON). */
export interface AssertionCredential {
  id: string;
  rawId: string;
  type: "public-key";
  response: {
    clientDataJSON: string;
    authenticatorData: string;
    signature: string;
    userHandle?: string;
  };
}

export interface PasskeyNative {
  create(options: CreationOptions): Promise<RegistrationCredential | null>;
  get(options: RequestOptions): Promise<AssertionCredential | null>;
}

/** One server answer, reduced to what a decision needs. */
export type ServerAnswer =
  | { ok: true; status: number; body: unknown }
  | { ok: false; status: number; error: string; manualPath: boolean };

export interface PasskeyPorts {
  /** The native passkey module, or null where this phone/build has none. */
  native(): Promise<PasskeyNative | null>;
  registrationOptions(): Promise<ServerAnswer>;
  register(credential: RegistrationCredential): Promise<ServerAnswer>;
  stepUpOptions(action: StepUpAction): Promise<ServerAnswer>;
  stepUp(action: StepUpAction, credential: AssertionCredential): Promise<ServerAnswer>;
}

export type EnrolFailure =
  "unsupported" | "cancelled" | "unavailable" | "exists" | "refused" | "session";
export type EnrolResult = { ok: true } | { ok: false; reason: EnrolFailure };

export type StepUpResult =
  | { kind: "passkey"; grant: string }
  | { kind: "otp_session"; enrolment: "offered" | "unavailable" }
  | { kind: "refused"; manualPath: boolean }
  | { kind: "cancelled" };

function enrolFailure(answer: ServerAnswer & { ok: false }): EnrolFailure {
  if (answer.status === 503) {
    return "unavailable";
  }
  if (answer.status === 409) {
    return "exists";
  }
  if (answer.error === "passkey_otp_session_required" || answer.status === 401) {
    return "session";
  }
  return "refused";
}

/** Create a passkey on this phone and register its public half. */
export async function enrol(ports: PasskeyPorts): Promise<EnrolResult> {
  const native = await ports.native();
  if (native === null) {
    return { ok: false, reason: "unsupported" };
  }
  const answer = await ports.registrationOptions();
  if (!answer.ok) {
    return { ok: false, reason: enrolFailure(answer) };
  }
  const options = guardCreationOptions(answer.body);
  if (options === null) {
    return { ok: false, reason: "refused" };
  }
  let credential: RegistrationCredential | null;
  try {
    credential = await native.create(options);
  } catch {
    // the system sheet was dismissed, or the platform refused: no passkey
    return { ok: false, reason: "cancelled" };
  }
  if (credential === null) {
    return { ok: false, reason: "cancelled" };
  }
  const registered = await ports.register(credential);
  return registered.ok ? { ok: true } : { ok: false, reason: enrolFailure(registered) };
}

function grantOf(body: unknown): string | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }
  const grant = (body as Record<string, unknown>).grant;
  return typeof grant === "string" && grant.length > 0 ? grant : null;
}

/** Step up for one action: a grant, the OTP tier (not enrolled), or a refusal. */
export async function stepUpFor(action: StepUpAction, ports: PasskeyPorts): Promise<StepUpResult> {
  const answer = await ports.stepUpOptions(action);
  if (!answer.ok) {
    return { kind: "refused", manualPath: answer.manualPath };
  }
  const offer = guardStepUpOffer(answer.body);
  if (offer === null) {
    return { kind: "refused", manualPath: false };
  }
  if (!offer.enrolled) {
    return { kind: "otp_session", enrolment: offer.enrolment };
  }
  const native = await ports.native();
  if (native === null) {
    // the patient holds a passkey this build cannot reach: a person decides
    return { kind: "refused", manualPath: true };
  }
  let credential: AssertionCredential | null;
  try {
    credential = await native.get(offer.options);
  } catch {
    return { kind: "cancelled" };
  }
  if (credential === null) {
    return { kind: "cancelled" };
  }
  const finished = await ports.stepUp(action, credential);
  if (!finished.ok) {
    return { kind: "refused", manualPath: finished.manualPath };
  }
  const grant = grantOf(finished.body);
  return grant === null ? { kind: "refused", manualPath: false } : { kind: "passkey", grant };
}
