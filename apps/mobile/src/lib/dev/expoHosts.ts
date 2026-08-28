/**
 * Reads the Metro hostUri and the app.json `extra.asrHosts` list (one list —
 * both dev daemons sit on the same box behind the same Mac) and derives the
 * candidate bases for a given port. Kept apart from hosts.ts so the pure
 * helpers stay node-testable without an expo import.
 */
import Constants from "expo-constants";

import { serviceCandidates } from "./hosts";

export function configuredServiceCandidates(port: number): string[] {
  const extra = (Constants.expoConfig?.extra ?? {}) as { asrHosts?: string[] };
  return serviceCandidates(Constants.expoConfig?.hostUri, extra.asrHosts ?? [], port);
}
