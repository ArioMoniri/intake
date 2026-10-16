/**
 * INT-551 (the RED-UI review of #842, item 2): the haptic gate's RED hold has
 * a caller (ADR-033 Q2's fail-closed default; motion S-3; files/02 §5.3).
 *
 * `appHaptics.presentRed` and `markSilentOrThirdParty` were never called, so
 * a server-confirmed success could buzz under an ALERT or CALM takeover, and
 * haptics went on after a SILENT RED, whose cue a buzz on the table would be.
 * The root layout now mounts one subscriber on the app's RED store. These
 * tests drive it with the real store, fed the catalog the route serves, and
 * the real gate over a fake engine, so what is proved is what the app runs.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import type { RedLocation, RedRegister } from "../livekit/red";
import type { RedTrigger } from "../livekit/types";
import { createHapticGate, type HapticEngine } from "../motion/hapticGate";
import type { HapticCall } from "../motion/haptics";
import { RED_LOCATIONS } from "../motion/red";
import { holdHapticsUnderRed } from "./hapticHold";
import { decodeRedCatalog, scriptIdFor, type PrePositionedRed, type RedOrigin } from "./hop";
import { createRedStore } from "./store";

const FIXTURES = join(__dirname, "..", "..", "..", "..", "..", "tests", "fixtures", "triage_hop");
const CATALOG = decodeRedCatalog(
  new Uint8Array(readFileSync(join(FIXTURES, "red_catalog.json"))),
) as PrePositionedRed;
const RULE = "rf.sentetik_yasamsal";
const ORIGIN: RedOrigin = { sessionId: "visit-1", visitId: "visit-1" };

function trigger(register: RedRegister, location: RedLocation = "REMOTE"): RedTrigger {
  return {
    kind: "red_trigger",
    ruleId: RULE,
    register,
    location,
    scriptId: scriptIdFor(RULE, location),
  };
}

/** The app's two halves, fresh: the RED store and the haptic gate over a fake engine. */
function app() {
  const played: HapticCall[] = [];
  const engine: HapticEngine = {
    platform: "ios",
    play: async (call) => {
      played.push(call);
    },
  };
  const gate = createHapticGate({ loadEngine: async () => engine });
  const store = createRedStore();
  /** A server-confirmed success: the one haptic a share's answer may ask for. */
  const success = () => gate.request("success", { surface: "shareIssue", serverConfirmed: true });
  return { gate, store, played, success };
}

describe("ALERT and CALM hold every haptic while they stand", () => {
  for (const register of ["ALERT", "CALM"] as const) {
    for (const location of RED_LOCATIONS) {
      it(`${register} at ${location}: a server-confirmed success is not felt under it`, async () => {
        const { gate, store, played, success } = app();
        const release = holdHapticsUnderRed(store, gate);
        // Positive control: with no RED the same request is felt.
        expect(await success()).not.toBeNull();
        store.present(trigger(register, location), CATALOG, ORIGIN);
        // Read in the same pass the store notified in: no wait, no frame.
        const held = success();
        expect(await held).toBeNull();
        expect(played).toHaveLength(1);
        // A takeover holds; it does not make the session silent.
        expect(gate.silentOrThirdPartyThisSession()).toBe(false);
        release();
      });
    }
  }

  it("the location answer keeps the hold: the RED still stands", async () => {
    const { gate, store, success } = app();
    holdHapticsUnderRed(store, gate);
    store.present(trigger("ALERT", "UNKNOWN"), CATALOG, ORIGIN);
    store.answerLocation("notInHospital");
    expect(await success()).toBeNull();
  });

  it("a RED already standing when the hold mounts is held at once", async () => {
    const { gate, store, success } = app();
    store.present(trigger("CALM"), CATALOG, ORIGIN);
    holdHapticsUnderRed(store, gate);
    expect(await success()).toBeNull();
  });

  it("a clinician-only finding followed by a takeover: the takeover holds", async () => {
    const { gate, store, success } = app();
    holdHapticsUnderRed(store, gate);
    store.present(trigger("DEFERRED_CLINICIAN"), CATALOG, ORIGIN);
    expect(await success()).not.toBeNull();
    store.present(trigger("ALERT"), CATALOG, ORIGIN);
    expect(await success()).toBeNull();
  });
});

describe("a SILENT RED makes silence permanent", () => {
  for (const location of RED_LOCATIONS) {
    it(`SILENT at ${location}: no haptic for the rest of the session, even after the hold unmounts`, async () => {
      const { gate, store, played, success } = app();
      const release = holdHapticsUnderRed(store, gate);
      store.present(trigger("SILENT", location), CATALOG, ORIGIN);
      expect(gate.silentOrThirdPartyThisSession()).toBe(true);
      expect(await success()).toBeNull();
      release();
      expect(await success()).toBeNull();
      expect(await gate.request("select", { surface: "settings", valueChanged: true })).toBeNull();
      expect(played).toEqual([]);
    });
  }
});

describe("what the hold asks of the gate, call for call", () => {
  /** A gate that records what it is told, for the calls the review named. */
  function spy() {
    const calls: string[] = [];
    const gate = {
      presentRed: (register: RedRegister) => {
        calls.push(`presentRed:${register}`);
        return () => {
          calls.push(`release:${register}`);
        };
      },
      markSilentOrThirdParty: () => {
        calls.push("markSilentOrThirdParty");
      },
    };
    return { gate, calls };
  }

  it("ALERT and CALM are presented once each; SILENT marks the session; DEFERRED_CLINICIAN asks nothing", () => {
    for (const register of ["ALERT", "CALM"] as const) {
      const { gate, calls } = spy();
      const store = createRedStore();
      const release = holdHapticsUnderRed(store, gate);
      store.present(trigger(register, "UNKNOWN"), CATALOG, ORIGIN);
      store.answerLocation("inHospital");
      expect(calls).toEqual([`presentRed:${register}`]);
      release();
      expect(calls).toEqual([`presentRed:${register}`, `release:${register}`]);
    }
    const silent = spy();
    const silentStore = createRedStore();
    holdHapticsUnderRed(silentStore, silent.gate);
    silentStore.present(trigger("SILENT"), CATALOG, ORIGIN);
    expect(silent.calls).toEqual(["markSilentOrThirdParty"]);
    const deferred = spy();
    const deferredStore = createRedStore();
    holdHapticsUnderRed(deferredStore, deferred.gate);
    deferredStore.present(trigger("DEFERRED_CLINICIAN"), CATALOG, ORIGIN);
    expect(deferred.calls).toEqual([]);
  });
});

describe("near misses: nothing the patient sees, nothing held", () => {
  it("DEFERRED_CLINICIAN changes nothing on the patient's side, so haptics go on", async () => {
    const { gate, store, played, success } = app();
    holdHapticsUnderRed(store, gate);
    store.present(trigger("DEFERRED_CLINICIAN"), CATALOG, ORIGIN);
    expect(await success()).not.toBeNull();
    expect(played).toHaveLength(1);
    expect(gate.silentOrThirdPartyThisSession()).toBe(false);
  });

  it("with no RED at all the hold is invisible", async () => {
    const { gate, store, success } = app();
    holdHapticsUnderRed(store, gate);
    expect(await success()).not.toBeNull();
    expect(gate.silentOrThirdPartyThisSession()).toBe(false);
  });

  it("an unmounted hold releases its takeover and stops listening", async () => {
    const { gate, store, success } = app();
    const release = holdHapticsUnderRed(store, gate);
    store.present(trigger("ALERT"), CATALOG, ORIGIN);
    release();
    expect(await success()).not.toBeNull();
  });
});
