import { afterEach, describe, expect, it, vi } from "vitest";

import { OTP_LENGTH, enterOtp, isCompleteOtp, maskPhone, normaliseTrPhone } from "./phone";

describe("normaliseTrPhone mirrors the server normaliser", () => {
  it.each([
    ["+905321114455", "+905321114455"],
    ["05321114455", "+905321114455"],
    ["905321114455", "+905321114455"],
    ["5321114455", "+905321114455"],
    ["+90 532 111 44 55", "+905321114455"],
    ["0 (532) 111-44-55", "+905321114455"],
  ])("%s → %s", (raw, expected) => {
    expect(normaliseTrPhone(raw)).toBe(expected);
  });

  it.each(["1234", "+15551234567", "0212 111 22 33", "532", "", "05321114455X"])(
    "rejects %s",
    (raw) => {
      expect(normaliseTrPhone(raw)).toBeNull();
    },
  );
});

describe("maskPhone", () => {
  it("keeps only the operator prefix and the last two digits", () => {
    const masked = maskPhone("+905321114455");
    expect(masked).toBe("+90 532 ··· ·· 55");
    expect(masked).not.toContain("111");
    expect(masked).not.toContain("44");
  });
});

describe("otp entry", () => {
  it("six digit registers complete the code", () => {
    expect(OTP_LENGTH).toBe(6);
    expect(isCompleteOtp(["1", "2", "3", "4", "5", "6"])).toBe(true);
    expect(isCompleteOtp(["1", "2", "3", "4", "5", ""])).toBe(false);
    expect(isCompleteOtp(["1", "2", "3", "4", "5"])).toBe(false);
    expect(isCompleteOtp(["1", "2", "3", "4", "5", "a"])).toBe(false);
  });
});

/**
 * INT-361 (WCAG 2.2 SC 3.3.8): a pasted or OS-autofilled code fills the
 * registers, so the patient never has to transcribe it digit by digit.
 * onChangeText hands the helper the field's WHOLE new text; these cases are
 * the shapes that text takes.
 */
describe("enterOtp distributes what one register receives", () => {
  const EMPTY = ["", "", "", "", "", ""] as const;
  const CODE = "730418";
  const WHOLE = ["7", "3", "0", "4", "1", "8"];

  it("a whole code pasted into the first box fills all six", () => {
    const entry = enterOtp(EMPTY, 0, CODE);
    expect(entry.digits).toEqual(WHOLE);
    expect(isCompleteOtp(entry.digits)).toBe(true);
    expect(entry.focus).toBe(OTP_LENGTH - 1);
  });

  it.each([1, 3, 5])("a whole code pasted into box %i still fills all six from the first", (at) => {
    const entry = enterOtp(EMPTY, at, CODE);
    expect(entry.digits).toEqual(WHOLE);
    expect(entry.focus).toBe(OTP_LENGTH - 1);
  });

  it("a whole code replaces a half-typed one rather than merging with it", () => {
    const entry = enterOtp(["9", "9", "", "", "", ""], 2, CODE);
    expect(entry.digits).toEqual(WHOLE);
  });

  it.each([
    ["spaces", "730 418"],
    ["dashes", "730-418"],
    ["a label and punctuation", "Kod: 730418."],
    ["a newline from a copied message", "730418\n"],
  ])("only digits count — %s are dropped", (_what, pasted) => {
    expect(enterOtp(EMPTY, 0, pasted).digits).toEqual(WHOLE);
  });

  it("more than six digits keeps the first six", () => {
    // A copied SMS body: the code first, then its validity window.
    const entry = enterOtp(EMPTY, 0, "730418 kodu 3 dakika geçerlidir");
    expect(entry.digits).toEqual(WHOLE);
    expect(enterOtp(EMPTY, 4, "73041899").digits).toEqual(WHOLE);
  });

  it("letters alone change nothing and move nothing", () => {
    const start = ["1", "", "", "", "", ""];
    const entry = enterOtp(start, 1, "abc");
    expect(entry.digits).toEqual(start);
    expect(entry.focus).toBe(1);
    // A letter typed beside a digit already there is not a new digit either.
    const beside = enterOtp(start, 0, "1a");
    expect(beside.digits).toEqual(start);
    expect(beside.focus).toBe(0);
  });

  it("a code pasted beside the digit a box already shows fills all six", () => {
    // The box held "5"; the paste lands after it or before it, depending on
    // where the caret was.
    const filled = ["", "", "", "5", "", ""];
    expect(enterOtp(filled, 3, `5${CODE}`).digits).toEqual(WHOLE);
    expect(enterOtp(filled, 3, `${CODE}5`).digits).toEqual(WHOLE);
  });

  it("a shorter run fills forward from the box it landed in, clipped at the last", () => {
    const entry = enterOtp(EMPTY, 1, "730");
    expect(entry.digits).toEqual(["", "7", "3", "0", "", ""]);
    // Focus goes where the next digit belongs, so typing carries on.
    expect(entry.focus).toBe(4);
    const clipped = enterOtp(EMPTY, 4, "730");
    expect(clipped.digits).toEqual(["", "", "", "", "7", "3"]);
    expect(clipped.focus).toBe(OTP_LENGTH - 1);
  });

  it("typing one digit is unchanged: this box only, then the next box", () => {
    const entry = enterOtp(EMPTY, 2, "4");
    expect(entry.digits).toEqual(["", "", "4", "", "", ""]);
    expect(entry.focus).toBe(3);
    const last = enterOtp(EMPTY, 5, "4");
    expect(last.digits).toEqual(["", "", "", "", "", "4"]);
    expect(last.focus).toBe(5);
  });

  it("a digit typed beside the one already there replaces it", () => {
    const filled = ["", "", "3", "", "", ""];
    expect(enterOtp(filled, 2, "37").digits).toEqual(["", "", "7", "", "", ""]);
    expect(enterOtp(filled, 2, "73").digits).toEqual(["", "", "7", "", "", ""]);
    expect(enterOtp(filled, 2, "33").digits).toEqual(["", "", "3", "", "", ""]);
    expect(enterOtp(filled, 2, "37").focus).toBe(3);
  });

  it("clearing a box empties that box only and keeps focus there", () => {
    const entry = enterOtp(["7", "3", "0", "", "", ""], 1, "");
    expect(entry.digits).toEqual(["7", "", "0", "", "", ""]);
    expect(entry.focus).toBe(1);
  });

  it("never mutates the registers it was given", () => {
    const start = ["", "", "", "", "", ""];
    enterOtp(start, 0, CODE);
    enterOtp(start, 2, "4");
    expect(start).toEqual(["", "", "", "", "", ""]);
  });
});

describe("the code never reaches a log line (invariant 6)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("distributing a code writes nothing to the console, on any path", () => {
    const methods = ["log", "info", "warn", "error", "debug", "trace"] as const;
    const spies = methods.map((m) => vi.spyOn(console, m).mockImplementation(() => undefined));
    const start = ["", "", "", "5", "", ""];
    for (const [at, text] of [
      [0, "730418"],
      [3, "5730418"],
      [3, "730-418"],
      [1, "730"],
      [2, "abc"],
      [3, ""],
      [0, "730418 kodu 3 dakika geçerlidir"],
    ] as const) {
      enterOtp(start, at, text);
    }
    for (const spy of spies) {
      expect(spy).not.toHaveBeenCalled();
    }
  });
});
