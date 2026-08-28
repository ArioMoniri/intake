/**
 * Onboarding flow state (INT-131): the phone waiting for its OTP lives in
 * module memory ONLY — never in route params, deep links or storage
 * (files/10 §4: no PHI in deep links; a phone number is personal data).
 * Losing it on a cold start simply restarts the two-screen flow.
 */

let pendingPhone: string | null = null;

export function setPendingPhone(phoneE164: string | null): void {
  pendingPhone = phoneE164;
}

export function getPendingPhone(): string | null {
  return pendingPhone;
}
