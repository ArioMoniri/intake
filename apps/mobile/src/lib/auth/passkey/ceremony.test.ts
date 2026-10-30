/**
 * INT-582 (D36) — enrolment and the step-up ceremony, over fake ports.
 *
 * The properties a screen cannot be trusted to keep: a patient without a
 * passkey is told so and never locked out; a cancelled system sheet is the
 * patient's choice and never reported as a refusal; a refusal carries the
 * manual path when the server names one; nothing passes on an answer the
 * guards in ./rp refuse.
 */
import { describe, expect, it, vi } from "vitest";

import {
  type AssertionCredential,
  type PasskeyNative,
  type PasskeyPorts,
  type RegistrationCredential,
  type ServerAnswer,
  enrol,
  stepUpFor,
} from "./ceremony";
import { PASSKEY_RP_ID } from "./rp";

const CREATION = {
  publicKey: {
    rp: { id: PASSKEY_RP_ID, name: "Önvizit" },
    user: { id: "aGFuZGxl", name: "Önvizit", displayName: "Önvizit" },
    challenge: "Y2hhbGxlbmdl",
    pubKeyCredParams: [{ type: "public-key", alg: -7 }],
    excludeCredentials: [],
    authenticatorSelection: {
      authenticatorAttachment: "platform",
      residentKey: "required",
      userVerification: "required",
    },
    attestation: "none",
  },
};

const OFFER = {
  enrolled: true,
  publicKey: {
    challenge: "Y2hhbGxlbmdl",
    rpId: PASSKEY_RP_ID,
    allowCredentials: [{ type: "public-key", id: "Y3JlZA" }],
    userVerification: "required",
  },
};

const REGISTRATION: RegistrationCredential = {
  id: "Y3JlZA",
  rawId: "Y3JlZA",
  type: "public-key",
  response: { clientDataJSON: "e30", attestationObject: "oA" },
};

const ASSERTION: AssertionCredential = {
  id: "Y3JlZA",
  rawId: "Y3JlZA",
  type: "public-key",
  response: { clientDataJSON: "e30", authenticatorData: "AA", signature: "AA" },
};

const ok = (body: unknown, status = 200): ServerAnswer => ({ ok: true, status, body });
const no = (status: number, error = "", manualPath = false): ServerAnswer => ({
  ok: false,
  status,
  error,
  manualPath,
});

function native(overrides: Partial<PasskeyNative> = {}): PasskeyNative {
  return {
    create: vi.fn(async () => REGISTRATION),
    get: vi.fn(async () => ASSERTION),
    ...overrides,
  };
}

function ports(overrides: Partial<PasskeyPorts> = {}, phone: PasskeyNative | null = native()) {
  return {
    native: vi.fn(async () => phone),
    registrationOptions: vi.fn(async () => ok(CREATION)),
    register: vi.fn(async () => ok({ passkey_id: "p" }, 201)),
    stepUpOptions: vi.fn(async () => ok(OFFER)),
    stepUp: vi.fn(async () => ok({ grant: "grant-value", action: "data_delete", expires_in: 120 })),
    ...overrides,
  } satisfies PasskeyPorts;
}

describe("enrolment", () => {
  it("creates the passkey on the phone and registers what the phone returned", async () => {
    const wired = ports();
    expect(await enrol(wired)).toEqual({ ok: true });
    expect(wired.register).toHaveBeenCalledWith(REGISTRATION, {});
  });

  it("a phone without passkeys asks the server nothing", async () => {
    const wired = ports({}, null);
    expect(await enrol(wired)).toEqual({ ok: false, reason: "unsupported" });
    expect(wired.registrationOptions).not.toHaveBeenCalled();
  });

  it.each([
    [503, "passkey_not_configured", "unavailable"],
    [403, "passkey_otp_session_required", "session"],
    [400, "anything", "refused"],
  ])("a %s %s at the options is %s", async (status, error, reason) => {
    const wired = ports({ registrationOptions: vi.fn(async () => no(status, error)) });
    expect(await enrol(wired)).toEqual({ ok: false, reason });
  });

  it("options for another relying party never reach the native sheet", async () => {
    const phone = native();
    const wired = ports(
      {
        registrationOptions: vi.fn(async () =>
          ok({ publicKey: { ...CREATION.publicKey, rp: { id: "evil.example", name: "x" } } }),
        ),
      },
      phone,
    );
    expect(await enrol(wired)).toEqual({ ok: false, reason: "refused" });
    expect(phone.create).not.toHaveBeenCalled();
  });

  it("a dismissed sheet is a cancellation, whether it throws or returns nothing", async () => {
    const thrown = ports({}, native({ create: vi.fn(async () => Promise.reject(new Error("x"))) }));
    expect(await enrol(thrown)).toEqual({ ok: false, reason: "cancelled" });
    const empty = ports({}, native({ create: vi.fn(async () => null) }));
    expect(await enrol(empty)).toEqual({ ok: false, reason: "cancelled" });
    expect(empty.register).not.toHaveBeenCalled();
  });

  it("a passkey the server already holds is named as such", async () => {
    const wired = ports({ register: vi.fn(async () => no(409, "passkey_exists")) });
    expect(await enrol(wired)).toEqual({ ok: false, reason: "exists" });
  });
});

describe("the step-up", () => {
  it("returns the grant the server mints for this action", async () => {
    const wired = ports();
    expect(await stepUpFor("data_delete", wired)).toEqual({
      kind: "passkey",
      grant: "grant-value",
    });
    expect(wired.stepUpOptions).toHaveBeenCalledWith("data_delete");
    expect(wired.stepUp).toHaveBeenCalledWith("data_delete", ASSERTION);
  });

  it("a patient without a passkey stays on the OTP tier and is offered one", async () => {
    const phone = native();
    const wired = ports(
      {
        stepUpOptions: vi.fn(async () =>
          ok({ enrolled: false, tier: "otp_session", enrolment: "offered" }),
        ),
      },
      phone,
    );
    expect(await stepUpFor("data_delete", wired)).toEqual({
      kind: "otp_session",
      enrolment: "offered",
    });
    expect(phone.get).not.toHaveBeenCalled();
  });

  it("a refusal carries the manual path the server names", async () => {
    const wired = ports({
      stepUp: vi.fn(async () => no(403, "step_up_refused", true)),
    });
    expect(await stepUpFor("data_delete", wired)).toEqual({ kind: "refused", manualPath: true });
  });

  it("an enrolled patient on a phone without passkeys is sent to a person", async () => {
    const wired = ports({}, null);
    expect(await stepUpFor("data_delete", wired)).toEqual({ kind: "refused", manualPath: true });
  });

  it("an unconfigured tier refusing an enrolled patient keeps its manual path", async () => {
    const wired = ports({
      stepUpOptions: vi.fn(async () => no(503, "passkey_not_configured", true)),
    });
    expect(await stepUpFor("data_delete", wired)).toEqual({ kind: "refused", manualPath: true });
  });

  it("a dismissed sheet is a cancellation and the server hears nothing", async () => {
    const wired = ports({}, native({ get: vi.fn(async () => Promise.reject(new Error("x"))) }));
    expect(await stepUpFor("data_delete", wired)).toEqual({ kind: "cancelled" });
    const empty = ports({}, native({ get: vi.fn(async () => null) }));
    expect(await stepUpFor("data_delete", empty)).toEqual({ kind: "cancelled" });
    expect(empty.stepUp).not.toHaveBeenCalled();
  });

  it("an answer the guard refuses, or a success with no grant, is no pass", async () => {
    const odd = ports({ stepUpOptions: vi.fn(async () => ok({ enrolled: true })) });
    expect(await stepUpFor("data_delete", odd)).toEqual({ kind: "refused", manualPath: false });
    const empty = ports({ stepUp: vi.fn(async () => ok({ grant: "" })) });
    expect(await stepUpFor("data_delete", empty)).toEqual({ kind: "refused", manualPath: false });
  });
});

describe("INT-582 review B1: a second passkey is a passkey_add step-up", () => {
  const GRANT = { "X-Intake-Step-Up-Grant": "grant-value" };

  it("asks the patient's passkey first, then enrols with the grant on both calls", async () => {
    const registrationOptions = vi.fn(async (headers?: Record<string, string>) =>
      headers && "X-Intake-Step-Up-Grant" in headers
        ? ok(CREATION)
        : no(403, "step_up_required", true),
    );
    const wired = ports({ registrationOptions });
    expect(await enrol(wired)).toEqual({ ok: true });
    expect(wired.stepUpOptions).toHaveBeenCalledWith("passkey_add");
    expect(registrationOptions).toHaveBeenLastCalledWith(GRANT);
    expect(wired.register).toHaveBeenCalledWith(REGISTRATION, GRANT);
  });

  it("near miss: a patient with no passkey enrols with no step-up and no header", async () => {
    const wired = ports();
    expect(await enrol(wired)).toEqual({ ok: true });
    expect(wired.stepUpOptions).not.toHaveBeenCalled();
    expect(wired.register).toHaveBeenCalledWith(REGISTRATION, {});
  });

  it("a passkey that cannot confirm the addition is the step-up refusal; a closed sheet is a cancel", async () => {
    const demanding = vi.fn(async () => no(403, "step_up_required", true));
    const refused = ports({
      registrationOptions: demanding,
      stepUp: vi.fn(async () => no(403, "step_up_refused", true)),
    });
    expect(await enrol(refused)).toEqual({ ok: false, reason: "step_up" });
    const closed = ports(
      { registrationOptions: demanding },
      native({ get: vi.fn(async () => null) }),
    );
    expect(await enrol(closed)).toEqual({ ok: false, reason: "cancelled" });
  });
});
