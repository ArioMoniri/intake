/**
 * Which signed-in session is synthetic, and so which may carry a synthetic
 * label (INT-421). Owner directive: "in production don't include deneme
 * hastası".
 *
 * Only the INT-130 dev fixture, signed in through the INT-197 `__DEV__` card,
 * is synthetic. A phone-verified (`otp`, INT-131) account is a real patient
 * and never wears the label, whatever its display name says: the name is the
 * masked phone or, after INT-318, the hospital feed's name, and neither tells
 * a fixture from a person. The session's `kind` does. Anything that is not
 * exactly `dev` gets no label, so an unexpected kind fails closed.
 *
 * Pure (a type-only session import), so the vitest lane checks the rule
 * without rendering a screen.
 */
import type { MessageKey } from "../i18n";
import type { SessionAccount } from "../session";

/** What the rule reads: the session's kind, and nothing else. */
export type SessionKind = Pick<SessionAccount, "kind">;

const SYNTHETIC_BADGE: MessageKey = "me.syntheticBadge";

/** True only for the synthetic dev session. */
export function isSyntheticSession(account: SessionKind | null): boolean {
  return account?.kind === "dev";
}

/** The catalogue key for the account row's sublabel, or null for none. */
export function accountBadgeKey(account: SessionKind | null): MessageKey | null {
  return isSyntheticSession(account) ? SYNTHETIC_BADGE : null;
}
