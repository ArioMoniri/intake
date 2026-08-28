/**
 * Certificate-pinning status (INT-131) — honest by type.
 *
 * Pinning is an OS-LAYER control: the config plugin
 * (plugins/withCertificatePinning.js) writes Android
 * network_security_config pin-sets and iOS NSPinnedDomains into the NEXT
 * dev build, from `expo.extra.certificatePins`. JavaScript cannot observe
 * the OS trust evaluation, Expo Go never carries the plugin output, and no
 * pins exist yet (the production hosts and their SPKI hashes are
 * awaiting-human — docs/evidence/INT-131.md). So this module can only
 * report configuration state, and its type makes the honest part
 * structural: `active` is literally `false` — nothing in the JS layer may
 * ever claim live pinning.
 */
import Constants, { ExecutionEnvironment } from "expo-constants";

export interface PinnedDomain {
  host: string;
  pins: string[];
}

export interface PinningStatus {
  /** JS can never verify the OS trust path — by type, never true here. */
  active: false;
  configuredForNextBuild: boolean;
  reason: "expo_go" | "no_pins_configured" | "os_layer_not_verifiable";
}

function configuredPins(): PinnedDomain[] {
  const extra = (Constants.expoConfig?.extra ?? {}) as {
    certificatePins?: PinnedDomain[];
  };
  return extra.certificatePins ?? [];
}

export function pinningStatus(): PinningStatus {
  const expoGo = Constants.executionEnvironment === ExecutionEnvironment.StoreClient;
  if (expoGo) {
    return { active: false, configuredForNextBuild: false, reason: "expo_go" };
  }
  if (configuredPins().length === 0) {
    return { active: false, configuredForNextBuild: false, reason: "no_pins_configured" };
  }
  return { active: false, configuredForNextBuild: true, reason: "os_layer_not_verifiable" };
}
