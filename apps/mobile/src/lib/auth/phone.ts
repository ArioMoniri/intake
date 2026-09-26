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

/** The registers after one field changed, and the register to focus next. */
export interface OtpUpdate {
  readonly digits: readonly string[];
  readonly focus: number;
}

const NON_DIGIT = /\D/g;

/**
 * What the patient added to a register that already showed `previous`. The
 * field's new text is that digit with the addition before or after it (where
 * the caret was), or the addition alone (the digit was selected). The digit
 * is taken out only when what remains is one digit or a whole code; any other
 * length reads as the addition alone.
 */
function addedTo(previous: string, incoming: string): string {
  if (previous === "" || incoming.length <= 1) {
    return incoming;
  }
  let rest: string | null = null;
  if (incoming.startsWith(previous)) {
    rest = incoming.slice(previous.length);
  } else if (incoming.endsWith(previous)) {
    rest = incoming.slice(0, incoming.length - previous.length);
  }
  return rest !== null && (rest.length === 1 || rest.length === OTP_LENGTH) ? rest : incoming;
}

/**
 * One register's field changed (INT-361; WCAG 2.2 SC 3.3.8). onChangeText
 * hands over the field's WHOLE new text, so it may be one typed digit, a digit
 * typed beside the one already there, or a whole code, pasted or filled by the
 * OS (iOS "From Messages", Android SMS autofill). Only digits count: spaces,
 * dashes and words in a pasted message are dropped.
 *
 * - A whole code fills every register from the first, whichever box it landed
 *   in. Digits past OTP_LENGTH are dropped.
 * - A shorter run fills forward from this register and stops at the last one.
 * - One digit sets this register only, which is how typing already worked.
 *
 * Focus moves to the register after the last one written, so typing carries
 * on; a whole code leaves it on the last register. Nothing here submits: the
 * patient still presses verify. Pure and silent, so the code cannot reach a
 * log line from here (invariant 6).
 */
export function enterOtp(digits: readonly string[], index: number, text: string): OtpUpdate {
  const previous = digits[index] ?? "";
  const incoming = text.replace(NON_DIGIT, "");
  if (incoming === previous) {
    return { digits, focus: index };
  }
  const added = addedTo(previous, incoming);
  if (added.length >= OTP_LENGTH) {
    return { digits: added.slice(0, OTP_LENGTH).split(""), focus: OTP_LENGTH - 1 };
  }
  const next = [...digits];
  if (added === "") {
    next[index] = "";
    return { digits: next, focus: index };
  }
  const run = added.slice(0, OTP_LENGTH - index);
  for (let k = 0; k < run.length; k += 1) {
    next[index + k] = run.charAt(k);
  }
  return { digits: next, focus: Math.min(index + run.length, OTP_LENGTH - 1) };
}
