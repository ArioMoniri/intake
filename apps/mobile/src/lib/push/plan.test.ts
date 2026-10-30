/**
 * INT-583 — when this device asks for new-sign-in notices, and what a token
 * has to look like before it leaves the phone.
 *
 * The rule the planner exists to hold: the system prompt appears only after
 * the patient taps the enable button. A cold prompt at launch is the one
 * permission request a patient refuses without reading, and iOS never shows
 * it twice.
 */
import { describe, expect, it } from "vitest";

import {
  isApnsDeviceToken,
  planAfterPrompt,
  planPushRegistration,
  toPushPermission,
  type PushPermission,
} from "./plan";

const HEX_64 = "a".repeat(32) + "0123456789abcdef".repeat(2);

describe("the planner: permission x whether the patient asked", () => {
  const cases: [PushPermission, boolean, string][] = [
    ["granted", false, "register"],
    ["granted", true, "register"],
    ["undetermined", false, "skip"],
    ["undetermined", true, "ask"],
    ["denied", false, "skip"],
    ["denied", true, "explain-denied"],
    ["unavailable", false, "skip"],
    ["unavailable", true, "skip"],
  ];

  it.each(cases)("%s, asked=%s -> %s", (permission, asked, step) => {
    expect(planPushRegistration(permission, asked)).toBe(step);
  });

  it("never asks the system on its own: no unasked input yields `ask`", () => {
    for (const permission of ["granted", "denied", "undetermined", "unavailable"] as const) {
      expect(planPushRegistration(permission, false)).not.toBe("ask");
    }
  });

  it("a shared clinic device never registers or asks, whatever the permission", () => {
    for (const permission of ["granted", "denied", "undetermined", "unavailable"] as const) {
      for (const asked of [false, true]) {
        expect(planPushRegistration(permission, asked, { sharedDevice: true })).toBe("skip");
      }
    }
  });

  it("a personal device is the default (near miss: sharedDevice false behaves as omitted)", () => {
    expect(planPushRegistration("granted", false, { sharedDevice: false })).toBe("register");
    expect(planPushRegistration("undetermined", true, { sharedDevice: false })).toBe("ask");
  });
});

describe("after the system prompt answers", () => {
  it("granted registers, denied explains, anything else stops without asking again", () => {
    expect(planAfterPrompt("granted")).toBe("register");
    expect(planAfterPrompt("denied")).toBe("explain-denied");
    expect(planAfterPrompt("undetermined")).toBe("skip");
    expect(planAfterPrompt("unavailable")).toBe("skip");
  });
});

describe("reading the native permission answer", () => {
  it("granted is granted", () => {
    expect(toPushPermission({ status: "granted", granted: true, canAskAgain: true })).toBe(
      "granted",
    );
  });

  it("undetermined that may still be asked is undetermined", () => {
    expect(toPushPermission({ status: "undetermined", granted: false, canAskAgain: true })).toBe(
      "undetermined",
    );
  });

  it("undetermined that can no longer be asked reads as denied (near miss)", () => {
    expect(toPushPermission({ status: "undetermined", granted: false, canAskAgain: false })).toBe(
      "denied",
    );
  });

  it("denied is denied", () => {
    expect(toPushPermission({ status: "denied", granted: false, canAskAgain: false })).toBe(
      "denied",
    );
  });

  it("an unknown status fails closed to denied, never to granted", () => {
    expect(toPushPermission({ status: "provisional-ish", granted: false, canAskAgain: true })).toBe(
      "denied",
    );
  });

  it("the granted flag wins over a status string the module did not expect", () => {
    expect(toPushPermission({ status: "denied", granted: true, canAskAgain: false })).toBe(
      "granted",
    );
  });
});

describe("the APNs device token shape, checked before anything is sent", () => {
  it("accepts lowercase hex of 64 characters", () => {
    expect(HEX_64).toHaveLength(64);
    expect(isApnsDeviceToken(HEX_64)).toBe(true);
  });

  it("accepts lowercase hex of 200 characters", () => {
    expect(isApnsDeviceToken("f".repeat(200))).toBe(true);
  });

  it("refuses 63 characters (near miss below the floor)", () => {
    expect(isApnsDeviceToken(HEX_64.slice(1))).toBe(false);
  });

  it("refuses 201 characters (near miss above the ceiling)", () => {
    expect(isApnsDeviceToken("f".repeat(201))).toBe(false);
  });

  it("refuses uppercase hex (near miss: same digits, wrong case)", () => {
    expect(isApnsDeviceToken(HEX_64.toUpperCase())).toBe(false);
    expect(isApnsDeviceToken("A" + HEX_64.slice(1))).toBe(false);
  });

  it("refuses a non-hex letter anywhere (near miss: one g)", () => {
    expect(isApnsDeviceToken(HEX_64.slice(0, 63) + "g")).toBe(false);
  });

  it("refuses an Expo relay token, which is not an APNs token at all", () => {
    expect(isApnsDeviceToken(`ExponentPushToken[${HEX_64}]`)).toBe(false);
  });

  it("refuses spaces, a newline and the empty string", () => {
    expect(isApnsDeviceToken(` ${HEX_64}`)).toBe(false);
    expect(isApnsDeviceToken(`${HEX_64}\n`)).toBe(false);
    expect(isApnsDeviceToken("")).toBe(false);
  });

  it("refuses what is not a string", () => {
    expect(isApnsDeviceToken(null)).toBe(false);
    expect(isApnsDeviceToken(undefined)).toBe(false);
    expect(isApnsDeviceToken(42)).toBe(false);
    expect(isApnsDeviceToken({ data: HEX_64 })).toBe(false);
  });
});
