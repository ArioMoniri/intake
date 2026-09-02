/**
 * Phone + OTP form rules (INT-131) — pure and node-testable, mirroring the
 * server's normaliser exactly (services/api otp.normalise_tr_phone): the
 * SAME spelling variants must collapse to one E.164 form on both sides or
 * the rate buckets and pseudonyms fork.
 */

export const OTP_LENGTH = 6;

const TR_MOBILE = /^(?:\+90|90|0)?(5\d{9})$/;
const STRIP = /[\s\-().]/g;

/** Turkish mobile → canonical E.164 (+905xxxxxxxxx); null when it is not one. */
export function normaliseTrPhone(raw: string): string | null {
  if (raw.length > 32) {
    return null;
  }
  const stripped = raw.replace(STRIP, "");
  const match = TR_MOBILE.exec(stripped);
  return match ? `+90${match[1]}` : null;
}

/** Display form that never re-prints the middle digits: +90 5xx ··· ·· 55. */
export function maskPhone(e164: string): string {
  if (e164.length !== 13 || !e164.startsWith("+90")) {
    return e164;
  }
  return `+90 ${e164.slice(3, 6)} ··· ·· ${e164.slice(11)}`;
}

/** OTP entry state: exactly OTP_LENGTH digit registers. */
export function isCompleteOtp(digits: readonly string[]): boolean {
  return digits.length === OTP_LENGTH && digits.every((d) => /^\d$/.test(d));
}
