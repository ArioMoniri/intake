/**
 * RED decoding and resolution (INT-103; invariant 21). The data channel is
 * untrusted input, so the near-miss negative controls matter as much as the
 * happy path: a message that cannot be understood must be REFUSED, never
 * coerced into a plausible RED and never into a plausible non-RED.
 */
import { describe, expect, it } from "vitest";

import { decodeRedTrigger, resolveRed, type RedScriptCatalog } from "./red";

const encode = (value: unknown) => new TextEncoder().encode(JSON.stringify(value));

const VALID = {
  kind: "red_trigger",
  ruleId: "life_threat.chest_pain",
  register: "ALERT",
  location: "REMOTE",
  scriptId: "life_threat.chest_pain.remote",
};

const CATALOG: RedScriptCatalog = {
  "life_threat.chest_pain.remote": {
    primary: "CALL_112",
    show112: true,
    actionTr: "Hemen 112'yi arayın.",
    doNotsTr: ["Araç kullanmayın.", "Aspirin almayın."],
    whyTr: "Belirtileriniz acil değerlendirme gerektirebilir.",
  },
  "life_threat.chest_pain.on_site": {
    primary: "GO_TO_IN_HOUSE_ACIL",
    show112: true,
    actionTr: "En yakın görevliye hemen haber verin.",
    doNotsTr: [],
    whyTr: null,
  },
};

describe("decodeRedTrigger", () => {
  it("decodes a fully specified trigger", () => {
    expect(decodeRedTrigger(encode(VALID))).toEqual({
      kind: "red_trigger",
      ruleId: "life_threat.chest_pain",
      register: "ALERT",
      location: "REMOTE",
      scriptId: "life_threat.chest_pain.remote",
    });
  });

  it("accepts every register and every location the schema defines", () => {
    for (const register of ["ALERT", "CALM", "SILENT", "DEFERRED_CLINICIAN"]) {
      for (const location of ["REMOTE", "ON_SITE", "UNKNOWN"]) {
        const decoded = decodeRedTrigger(encode({ ...VALID, register, location }));
        expect(decoded?.register).toBe(register);
        expect(decoded?.location).toBe(location);
      }
    }
  });

  // --- near-miss negative controls -------------------------------------------

  it("refuses a trigger with no register — there is no permitted default", () => {
    const { register: _dropped, ...withoutRegister } = VALID;
    expect(decodeRedTrigger(encode(withoutRegister))).toBeNull();
  });

  it("refuses a trigger with no location — there is no permitted default", () => {
    const { location: _dropped, ...withoutLocation } = VALID;
    expect(decodeRedTrigger(encode(withoutLocation))).toBeNull();
  });

  it("refuses an unknown register or location rather than coercing it", () => {
    expect(decodeRedTrigger(encode({ ...VALID, register: "URGENT" }))).toBeNull();
    expect(decodeRedTrigger(encode({ ...VALID, location: "HOME" }))).toBeNull();
    expect(decodeRedTrigger(encode({ ...VALID, register: "alert" }))).toBeNull();
  });

  it("ignores other message kinds", () => {
    expect(decodeRedTrigger(encode({ kind: "transcript", text: "merhaba" }))).toBeNull();
    expect(decodeRedTrigger(encode({ ruleId: "x" }))).toBeNull();
  });

  it("refuses non-JSON, arrays and primitives without throwing", () => {
    expect(decodeRedTrigger(new TextEncoder().encode("not json{"))).toBeNull();
    expect(decodeRedTrigger(encode([VALID]))).toBeNull();
    expect(decodeRedTrigger(encode("red_trigger"))).toBeNull();
    expect(decodeRedTrigger(encode(null))).toBeNull();
  });

  it("refuses ids that are not id-shaped, so free text cannot ride in", () => {
    expect(decodeRedTrigger(encode({ ...VALID, ruleId: "Ahmet Yılmaz" }))).toBeNull();
    expect(decodeRedTrigger(encode({ ...VALID, scriptId: "has space" }))).toBeNull();
    expect(decodeRedTrigger(encode({ ...VALID, ruleId: "" }))).toBeNull();
    expect(decodeRedTrigger(encode({ ...VALID, ruleId: "-leading-dash" }))).toBeNull();
  });

  it("carries no script text on the wire — the words come from the device", () => {
    const decoded = decodeRedTrigger(encode({ ...VALID, actionTr: "Kendi metnim" }));
    expect(decoded).not.toBeNull();
    expect(Object.keys(decoded ?? {}).sort()).toEqual([
      "kind",
      "location",
      "register",
      "ruleId",
      "scriptId",
    ]);
  });
});

describe("resolveRed", () => {
  it("resolves against the pre-positioned catalog verbatim", () => {
    const trigger = decodeRedTrigger(encode(VALID));
    const presentation = resolveRed(trigger!, CATALOG);
    expect(presentation?.script.actionTr).toBe("Hemen 112'yi arayın.");
    expect(presentation?.script.doNotsTr).toEqual(["Araç kullanmayın.", "Aspirin almayın."]);
    expect(presentation?.show112).toBe(true);
  });

  it("suppresses 112 under ON_SITE even when the pack sets show112", () => {
    const trigger = decodeRedTrigger(
      encode({ ...VALID, location: "ON_SITE", scriptId: "life_threat.chest_pain.on_site" }),
    );
    const presentation = resolveRed(trigger!, CATALOG);
    expect(presentation?.script.show112).toBe(true); // the pack said yes
    expect(presentation?.show112).toBe(false); // the patient is on site
  });

  it("returns null for a script that is not on the device", () => {
    const trigger = decodeRedTrigger(encode({ ...VALID, scriptId: "not.here" }));
    expect(resolveRed(trigger!, CATALOG)).toBeNull();
  });

  it("keeps 112 under UNKNOWN — only ON_SITE suppresses it", () => {
    const trigger = decodeRedTrigger(encode({ ...VALID, location: "UNKNOWN" }));
    expect(resolveRed(trigger!, CATALOG)?.show112).toBe(true);
  });
});
