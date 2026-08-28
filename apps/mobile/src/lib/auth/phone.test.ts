import { describe, expect, it } from "vitest";

import { OTP_LENGTH, isCompleteOtp, maskPhone, normaliseTrPhone } from "./phone";

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
