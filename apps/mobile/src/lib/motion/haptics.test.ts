/**
 * INT-340 (MOTION-11; docs/design/motion/motion-verification.md §2.1 #9–#11
 * and #19, §3 S-3, §4 MOTION-11; ADR-033 §6) — one haptic policy, sticky
 * suppression, and a success that only the server can confirm.
 *
 * Two pure modules are held here without a device:
 *
 * - `hapticFor(event, ctx)` (haptics.ts): the whole policy. A haptic fires
 *   only when the voice session is closed, the microphone is cold, no RED is
 *   on screen and nothing in this session has made silence permanent; only on
 *   a surface that owns that event; `select` only on a real change; `success`
 *   only on the server's word. What it returns is a `HapticCall`, a union with
 *   no member that could mean an error, a warning or a heavy impact.
 * - `createHapticGate` (hapticGate.ts): the live half. It reads the session,
 *   the microphone and the RED layer AT FIRE TIME through probes their owners
 *   register, keeps the SILENT/third-party flag for the rest of the session,
 *   and lets one haptic through per commit and per action.
 *
 * The device adapter (native/hapticsEngine.ts) is never imported here: the
 * gate takes an engine as a dependency, and these tests hand it a fake.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, expectTypeOf, it, vi } from "vitest";

import type { RedRegister } from "../livekit/red";
import {
  createHapticGate,
  type HapticEngine,
  type HapticGate,
  type HapticRequest,
} from "./hapticGate";
import {
  HAPTIC_EVENTS,
  HAPTIC_SURFACES,
  SURFACE_EVENTS,
  hapticFor,
  type AndroidHapticType,
  type GateRedRegister,
  type HapticCall,
  type HapticContext,
  type HapticEvent,
  type HapticPlatform,
  type HapticSurface,
} from "./haptics";

const PLATFORMS = ["ios", "android"] as const satisfies readonly HapticPlatform[];

/** Every register the schema defines; `satisfies` fails the build if one is added. */
const REGISTERS = ["ALERT", "CALM", "SILENT", "DEFERRED_CLINICIAN"] as const;
expectTypeOf<(typeof REGISTERS)[number]>().toEqualTypeOf<RedRegister>();
// The gate spells the registers itself so it never imports the RED path
// (MOTION-4); this keeps its spelling equal to livekit's.
expectTypeOf<GateRedRegister>().toEqualTypeOf<RedRegister>();

/** The four live conditions, each of which alone must silence every haptic. */
const BLOCKERS = [
  "voiceSessionActive",
  "micHot",
  "redPresented",
  "silentOrThirdPartyThisSession",
] as const;

const CLEAR = {
  voiceSessionActive: false,
  micHot: false,
  redPresented: false,
  silentOrThirdPartyThisSession: false,
} as const;

function ctx(over: Partial<HapticContext> = {}): HapticContext {
  return { platform: "ios", surface: "settings", ...CLEAR, ...over };
}

/** Every (event, surface) pair the policy admits, with the evidence each needs. */
const ELIGIBLE = HAPTIC_SURFACES.flatMap((surface) =>
  SURFACE_EVENTS[surface].map((event) => ({ event, surface })),
);

const PROOF = { valueChanged: true, serverConfirmed: true } as const;

/** Every call the policy can ever return, over the whole context space. */
function everyCall(): HapticCall[] {
  const flags = [false, true, undefined];
  return PLATFORMS.flatMap((platform) =>
    HAPTIC_SURFACES.flatMap((surface) =>
      HAPTIC_EVENTS.flatMap((event) =>
        flags.flatMap((valueChanged) =>
          flags.flatMap((serverConfirmed) => {
            const call = hapticFor(
              event,
              ctx({ platform, surface, valueChanged, serverConfirmed }),
            );
            return call === null ? [] : [call];
          }),
        ),
      ),
    ),
  );
}

interface Harness {
  readonly gate: HapticGate;
  readonly played: HapticCall[];
}

function harness(platform: HapticPlatform = "ios"): Harness {
  const played: HapticCall[] = [];
  const engine: HapticEngine = {
    platform,
    play: async (call) => {
      played.push(call);
    },
  };
  return { gate: createHapticGate({ loadEngine: async () => engine }), played };
}

/** One eligible request per admitted pair, each its own action. */
async function requestEvery(gate: HapticGate): Promise<(HapticCall | null)[]> {
  const results: (HapticCall | null)[] = [];
  for (const { event, surface } of ELIGIBLE) {
    results.push(await gate.request(event, { surface, ...PROOF }));
  }
  return results;
}

describe("MOTION-11 — the policy admits something (positive control)", () => {
  it("every admitted pair fires on both platforms when nothing forbids it", () => {
    expect(ELIGIBLE.length).toBeGreaterThanOrEqual(7);
    for (const platform of PLATFORMS) {
      for (const { event, surface } of ELIGIBLE) {
        expect(
          hapticFor(event, ctx({ platform, surface, ...PROOF })),
          `${event}@${surface}`,
        ).not.toBeNull();
      }
    }
  });
});

describe("MOTION-11 — the gate conditions", () => {
  it("no haptic while the voice audio session is active", async () => {
    for (const platform of PLATFORMS) {
      for (const { event, surface } of ELIGIBLE) {
        expect(
          hapticFor(event, ctx({ platform, surface, ...PROOF, voiceSessionActive: true })),
        ).toBeNull();
      }
    }
    const { gate, played } = harness();
    let open = true;
    const release = gate.register({ voiceSessionActive: () => open });
    expect((await requestEvery(gate)).every((r) => r === null)).toBe(true);
    // The session closing is read on the next request: nothing is cached.
    open = false;
    expect(
      await gate.request("select", { surface: "settings", valueChanged: true }),
    ).not.toBeNull();
    open = true;
    expect(await gate.request("select", { surface: "settings", valueChanged: true })).toBeNull();
    release();
    expect(
      await gate.request("select", { surface: "settings", valueChanged: true }),
    ).not.toBeNull();
    expect(played).toHaveLength(2);
    // Fail closed: a probe that cannot answer counts as an open session.
    gate.register({
      voiceSessionActive: () => {
        throw new Error("released");
      },
    });
    expect(await gate.request("select", { surface: "settings", valueChanged: true })).toBeNull();
  });

  it("no haptic while the microphone is hot, read at fire time", async () => {
    for (const { event, surface } of ELIGIBLE) {
      expect(hapticFor(event, ctx({ surface, ...PROOF, micHot: true }))).toBeNull();
    }
    const { gate, played } = harness();
    let hot = false;
    gate.register({ micHot: () => hot });
    expect(await gate.request("toggleOn", { surface: "settings" })).not.toBeNull();
    hot = true;
    expect(await gate.request("toggleOn", { surface: "settings" })).toBeNull();

    // Near miss 1: cold when the handler asks, hot by the time the engine is
    // ready. The second read, just before the native call, refuses it.
    let ready: (engine: HapticEngine) => void = () => undefined;
    const late: HapticCall[] = [];
    const slow = createHapticGate({
      loadEngine: () => new Promise<HapticEngine>((resolve) => (ready = resolve)),
    });
    let mic = false;
    slow.register({ micHot: () => mic });
    const pending = slow.request("select", { surface: "visits", valueChanged: true });
    mic = true;
    ready({ platform: "ios", play: async (call) => void late.push(call) });
    expect(await pending).toBeNull();
    expect(late).toEqual([]);

    // Near miss 2: hot when asked, cold a moment later. Nothing is queued to
    // play once the microphone closes.
    hot = true;
    const refused = gate.request("select", { surface: "visits", valueChanged: true });
    hot = false;
    expect(await refused).toBeNull();

    // Near miss 3: a caller cannot hand in a microphone state captured
    // earlier. The request has no such field, and a stray one is ignored.
    expectTypeOf<keyof HapticRequest>().toEqualTypeOf<
      "surface" | "actionId" | "valueChanged" | "serverConfirmed"
    >();
    hot = true;
    const stale = { surface: "visits", valueChanged: true, micHot: false } as HapticRequest;
    expect(await gate.request("select", stale)).toBeNull();
    expect(played).toHaveLength(1);
  });

  it("no RED register fires a haptic", async () => {
    // A RED has no event to ask with: the union is the five feedback events.
    expectTypeOf<HapticEvent>().toEqualTypeOf<
      "select" | "toggleOn" | "toggleOff" | "arm" | "success"
    >();
    for (const { event, surface } of ELIGIBLE) {
      expect(hapticFor(event, ctx({ surface, ...PROOF, redPresented: true }))).toBeNull();
    }
    for (const register of REGISTERS) {
      const { gate, played } = harness();
      const dismiss = gate.presentRed(register);
      // Presenting the RED plays nothing of its own, in any register.
      await Promise.resolve();
      expect(played, register).toEqual([]);
      const during = await requestEvery(gate);
      dismiss();
      if (register === "DEFERRED_CLINICIAN") {
        // Invisible to the patient, so invisible here (ADR-033 §5): nothing
        // the patient can feel changes, or the haptics would be a side channel.
        expect(
          during.every((r) => r !== null),
          register,
        ).toBe(true);
      } else {
        expect(
          during.every((r) => r === null),
          register,
        ).toBe(true);
        expect(played, register).toEqual([]);
      }
    }
    // Fail closed on a register the schema does not define.
    const { gate } = harness();
    gate.presentRed("LOUD" as RedRegister);
    expect(await gate.request("select", { surface: "settings", valueChanged: true })).toBeNull();
  });

  it("no haptic for the rest of a session in which a SILENT RED or a third party occurred", async () => {
    for (const { event, surface } of ELIGIBLE) {
      expect(
        hapticFor(event, ctx({ surface, ...PROOF, silentOrThirdPartyThisSession: true })),
      ).toBeNull();
    }
    const silent = harness();
    silent.gate.presentRed("SILENT")();
    expect(silent.gate.silentOrThirdPartyThisSession()).toBe(true);
    expect((await requestEvery(silent.gate)).every((r) => r === null)).toBe(true);

    const thirdParty = harness();
    thirdParty.gate.markSilentOrThirdParty();
    expect((await requestEvery(thirdParty.gate)).every((r) => r === null)).toBe(true);
    // Nothing on the gate can clear it: there is no such method.
    expectTypeOf<keyof HapticGate>().toEqualTypeOf<
      | "request"
      | "action"
      | "register"
      | "presentRed"
      | "markSilentOrThirdParty"
      | "silentOrThirdPartyThisSession"
    >();
    expect([...silent.played, ...thirdParty.played]).toEqual([]);

    // Near miss: ALERT and CALM hold haptics only while they are on screen.
    for (const register of ["ALERT", "CALM"] as const) {
      const { gate } = harness();
      gate.presentRed(register)();
      expect(gate.silentOrThirdPartyThisSession(), register).toBe(false);
      expect(
        await gate.request("select", { surface: "settings", valueChanged: true }),
      ).not.toBeNull();
    }
    // Only a new session starts clean.
    expect(await harness().gate.request("arm", { surface: "shareRevoke" })).not.toBeNull();
  });

  it("a companion or a third party declared on the phone marks the app's session", async () => {
    for (const declare of [{ thirdPartyPresent: true }, { role: "companion" as const }]) {
      vi.resetModules();
      const store = await import("../profile/store");
      const { appHaptics } = await import("./appHaptics");
      // Near miss: the patient alone, edited but still alone, marks nothing.
      store.setCompanionDeclaration({ role: "self", thirdPartyPresent: false });
      expect(appHaptics.silentOrThirdPartyThisSession()).toBe(false);
      store.setCompanionDeclaration(declare);
      expect(appHaptics.silentOrThirdPartyThisSession(), JSON.stringify(declare)).toBe(true);
      // Taking it back does not take the silence back.
      store.resetCompanionDeclaration();
      expect(appHaptics.silentOrThirdPartyThisSession()).toBe(true);
    }
  });
});

describe("MOTION-11 — surfaces", () => {
  it("ADR-038 A2: an answer chip and the composer mic own one event, the selection tick", () => {
    // INT-462. Every option gives the same tick, so no answer is rewarded over
    // another; the mic's tick is the tap that opens the microphone.
    expect(SURFACE_EVENTS.intakeChip).toEqual(["select"]);
    expect(SURFACE_EVENTS.dialogueMic).toEqual(["select"]);
    for (const surface of ["intakeChip", "dialogueMic"] as const) {
      for (const platform of ["ios", "android"] as const) {
        const call = hapticFor("select", {
          platform,
          surface,
          ...CLEAR,
          ...PROOF,
          valueChanged: true,
        });
        expect(call, `${surface}/${platform}`).toEqual(
          platform === "ios"
            ? { platform: "ios", method: "selectionAsync" }
            : { platform: "android", method: "performAndroidHapticsAsync", type: "segment-tick" },
        );
        for (const event of HAPTIC_EVENTS.filter((e) => e !== "select")) {
          expect(hapticFor(event, { platform, surface, ...CLEAR, ...PROOF })).toBeNull();
        }
      }
    }
  });

  it("ADR-038 A2: never while speech plays or the mic is hot, never on RED, never after silence", () => {
    const blocked = [
      { ...CLEAR, voiceSessionActive: true }, // the agent is speaking
      { ...CLEAR, micHot: true }, // the patient is talking
      { ...CLEAR, redPresented: true },
      { ...CLEAR, silentOrThirdPartyThisSession: true },
    ];
    for (const surface of ["intakeChip", "dialogueMic"] as const) {
      for (const platform of PLATFORMS) {
        for (const lane of blocked) {
          expect(
            hapticFor("select", { platform, surface, ...lane, ...PROOF, valueChanged: true }),
            `${surface} ${JSON.stringify(lane)}`,
          ).toBeNull();
        }
      }
    }
  });

  it("ADR-038 A2: a validated instrument's options are never felt", () => {
    expect(SURFACE_EVENTS.instrumentOption).toEqual([]);
    for (const platform of PLATFORMS) {
      for (const event of HAPTIC_EVENTS) {
        expect(
          hapticFor(event, {
            platform,
            surface: "instrumentOption",
            ...CLEAR,
            ...PROOF,
            valueChanged: true,
          }),
        ).toBeNull();
      }
    }
  });

  it("near miss: a chip tap that changes nothing is not felt", () => {
    expect(
      hapticFor("select", {
        platform: "ios",
        surface: "intakeChip",
        ...CLEAR,
        ...PROOF,
        valueChanged: false,
      }),
    ).toBeNull();
  });

  it("consent grant and withdraw never fire a haptic", () => {
    for (const surface of ["consent", "legal"] as const) {
      expect(SURFACE_EVENTS[surface]).toEqual([]);
      for (const platform of PLATFORMS) {
        for (const event of HAPTIC_EVENTS) {
          // toggleOn is a grant and toggleOff a withdrawal; neither is felt,
          // so the two directions cannot feel different either.
          expect(
            hapticFor(event, ctx({ platform, surface, ...PROOF })),
            `${event}@${surface}`,
          ).toBeNull();
        }
      }
    }
  });

  it("an error never fires a haptic", () => {
    expect(SURFACE_EVENTS.error).toEqual([]);
    for (const platform of PLATFORMS) {
      for (const event of HAPTIC_EVENTS) {
        expect(hapticFor(event, ctx({ platform, surface: "error", ...PROOF }))).toBeNull();
      }
    }
  });

  it("an unknown surface, event or missing flag fails closed", () => {
    const loose = (value: unknown) => value as never;
    expect(hapticFor("select", ctx({ surface: loose("toast"), valueChanged: true }))).toBeNull();
    expect(hapticFor(loose("warning"), ctx({ surface: "settings", ...PROOF }))).toBeNull();
    for (const blocker of BLOCKERS) {
      const partial: Record<string, unknown> = {
        ...ctx({ surface: "settings", valueChanged: true }),
      };
      delete partial[blocker];
      expect(hapticFor("select", partial as unknown as HapticContext), blocker).toBeNull();
    }
    expect(
      hapticFor("select", ctx({ platform: "other", surface: "settings", valueChanged: true })),
    ).toBeNull();
    expect(
      hapticFor("success", ctx({ surface: "dsar", serverConfirmed: loose("yes") })),
    ).toBeNull();
  });
});

describe("MOTION-11 — what fires, and when", () => {
  it("success fires only on a server-confirmed outcome, never on press", async () => {
    const successes = HAPTIC_SURFACES.filter((s) => SURFACE_EVENTS[s].includes("success"));
    expect(successes).toEqual(["shareIssue", "shareRevoke", "dsar"]);
    for (const platform of PLATFORMS) {
      for (const surface of successes) {
        for (const serverConfirmed of [undefined, false]) {
          expect(hapticFor("success", ctx({ platform, surface, serverConfirmed }))).toBeNull();
        }
      }
    }
    expect(hapticFor("success", ctx({ surface: "dsar", serverConfirmed: true }))).toEqual({
      platform: "ios",
      method: "notificationAsync",
      type: "success",
    });
    // The press asks for nothing; the handler that receives the answer does.
    const { gate, played } = harness("android");
    const press = gate.action();
    expect(await gate.request("success", { surface: "shareRevoke", actionId: press })).toBeNull();
    const refusedByServer = gate.action();
    expect(
      await gate.request("success", {
        surface: "shareRevoke",
        actionId: refusedByServer,
        serverConfirmed: false,
      }),
    ).toBeNull();
    const confirmed = gate.action();
    expect(
      await gate.request("success", {
        surface: "shareRevoke",
        actionId: confirmed,
        serverConfirmed: true,
      }),
    ).toEqual({ platform: "android", method: "performAndroidHapticsAsync", type: "confirm" });
    expect(played).toHaveLength(1);
  });

  it("issuing and revoking a link give the same feedback", () => {
    // Every combination of the four live conditions: suppression is symmetric too.
    const combos = BLOCKERS.reduce<Partial<HapticContext>[]>(
      (acc, key) =>
        acc.flatMap((c) => [
          { ...c, [key]: false },
          { ...c, [key]: true },
        ]),
      [{}],
    );
    expect(combos).toHaveLength(16);
    for (const platform of PLATFORMS) {
      for (const combo of combos) {
        for (const serverConfirmed of [false, true]) {
          const base = ctx({ platform, serverConfirmed, ...combo });
          const issue = hapticFor("success", { ...base, surface: "shareIssue" });
          const revoke = hapticFor("success", { ...base, surface: "shareRevoke" });
          expect(revoke, JSON.stringify({ platform, combo, serverConfirmed })).toEqual(issue);
        }
      }
      expect(
        hapticFor("success", ctx({ platform, surface: "shareIssue", serverConfirmed: true })),
      ).not.toBeNull();
    }
    // The arm step is the revoke's own two-step; issuing has none to arm.
    expect(SURFACE_EVENTS.shareIssue).toEqual(["success"]);
    expect(SURFACE_EVENTS.shareRevoke).toEqual(["arm", "success"]);
  });

  it("select fires only when the value changes", () => {
    const selectable = HAPTIC_SURFACES.filter((s) => SURFACE_EVENTS[s].includes("select"));
    // ADR-038 A2 (INT-462) adds the answer chip and the composer mic.
    expect(selectable).toEqual(["settings", "visits", "intakeChip", "dialogueMic"]);
    for (const platform of PLATFORMS) {
      for (const surface of selectable) {
        expect(hapticFor("select", ctx({ platform, surface, valueChanged: false }))).toBeNull();
        expect(hapticFor("select", ctx({ platform, surface }))).toBeNull();
        expect(hapticFor("select", ctx({ platform, surface, valueChanged: true }))).toEqual(
          platform === "ios"
            ? { platform, method: "selectionAsync" }
            : { platform, method: "performAndroidHapticsAsync", type: "segment-tick" },
        );
      }
    }
  });
});

describe("MOTION-11 — what a haptic can be", () => {
  it("HapticCall has no error, warning or heavy member", () => {
    expectTypeOf<HapticCall["method"]>().toEqualTypeOf<
      "selectionAsync" | "impactAsync" | "notificationAsync" | "performAndroidHapticsAsync"
    >();
    // iOS: the lightest impact only, and the success notification only.
    expectTypeOf<
      Extract<HapticCall, { method: "impactAsync" }>["style"]
    >().toEqualTypeOf<"light">();
    expectTypeOf<
      Extract<HapticCall, { method: "notificationAsync" }>["type"]
    >().toEqualTypeOf<"success">();
    // Android: no reject (a double click) and nothing AOSP maps to a heavy
    // click (long press, drag start).
    expectTypeOf<AndroidHapticType>().toEqualTypeOf<
      "segment-tick" | "toggle-on" | "toggle-off" | "context-click" | "confirm"
    >();

    const calls = everyCall();
    expect(calls.length).toBeGreaterThan(0);
    const forbidden = /error|warning|heavy|rigid|reject|long-press|drag-start/i;
    expect(calls.filter((call) => forbidden.test(JSON.stringify(call)))).toEqual([]);
  });

  it("Android never uses Vibrator-backed calls", async () => {
    expectTypeOf<
      Extract<HapticCall, { platform: "android" }>["method"]
    >().toEqualTypeOf<"performAndroidHapticsAsync">();
    const android = everyCall().filter((call) => call.platform === "android");
    expect(android.length).toBeGreaterThan(0);
    expect(new Set(android.map((call) => call.method))).toEqual(
      new Set(["performAndroidHapticsAsync"]),
    );

    const { gate, played } = harness("android");
    await requestEvery(gate);
    expect(played.length).toBe(ELIGIBLE.length);
    expect(played.every((call) => call.method === "performAndroidHapticsAsync")).toBe(true);

    // The adapter plays an Android call through View.performHapticFeedback
    // alone, and refuses a call built for the other platform.
    const engine = readFileSync(join(__dirname, "native", "hapticsEngine.ts"), "utf8");
    const androidBody = /function playAndroid\([^)]*\)[^{]*\{([\s\S]*?)\n\}/.exec(engine);
    expect(androidBody, "playAndroid in native/hapticsEngine.ts").not.toBeNull();
    expect(androidBody![1]).toContain("performAndroidHapticsAsync(");
    expect(androidBody![1]).not.toMatch(/selectionAsync|impactAsync|notificationAsync|vibrate/i);
    expect(engine).toMatch(/call\.platform\s*!==\s*platform/);
  });

  it("one haptic per commit, deduplicated by action id", async () => {
    const { gate, played } = harness();
    // One commit, the same action asked for twice: one haptic.
    const action = gate.action();
    const twice = await Promise.all([
      gate.request("success", { surface: "dsar", actionId: action, serverConfirmed: true }),
      gate.request("success", { surface: "dsar", actionId: action, serverConfirmed: true }),
    ]);
    expect(twice.filter((r) => r !== null)).toHaveLength(1);
    // The same action again in a later commit (a confirmation handled twice).
    expect(
      await gate.request("success", { surface: "dsar", actionId: action, serverConfirmed: true }),
    ).toBeNull();
    // Two different actions in one commit: still one haptic, the first.
    const [first, second] = await Promise.all([
      gate.request("select", { surface: "visits", valueChanged: true }),
      gate.request("toggleOff", { surface: "settings" }),
    ]);
    expect(first).not.toBeNull();
    expect(second).toBeNull();
    // A new commit is free again, and minted actions never repeat.
    expect(await gate.request("toggleOff", { surface: "settings" })).not.toBeNull();
    expect(gate.action()).not.toBe(gate.action());
    expect(played).toHaveLength(3);
    // A refused request does not hold the commit, so the next one can play.
    const [refused, next] = await Promise.all([
      gate.request("select", { surface: "visits", valueChanged: false }),
      gate.request("select", { surface: "visits", valueChanged: true }),
    ]);
    expect(refused).toBeNull();
    expect(next).not.toBeNull();
  });

  it("a failing engine never reaches the handler", async () => {
    const unavailable = createHapticGate({
      loadEngine: () => Promise.reject(new Error("no native module")),
    });
    await expect(
      unavailable.request("select", { surface: "visits", valueChanged: true }),
    ).resolves.toBeNull();
    const refusing = createHapticGate({
      loadEngine: async () => ({
        platform: "android",
        play: () => Promise.reject(new Error("HapticsNotSupportedException")),
      }),
    });
    await expect(refusing.request("toggleOn", { surface: "settings" })).resolves.toBeNull();
    const web = harness("other");
    expect(await web.gate.request("select", { surface: "visits", valueChanged: true })).toBeNull();
    expect(web.played).toEqual([]);
  });
});

/** Compile-time only: a surface list that drifts from the union fails `tsc`. */
expectTypeOf<(typeof HAPTIC_SURFACES)[number]>().toEqualTypeOf<HapticSurface>();
