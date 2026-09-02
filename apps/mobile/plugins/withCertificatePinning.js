/**
 * Certificate pinning config plugin (INT-131, files/10 §4).
 *
 * Pins at the OS layer — the only layer that covers ALL PHI traffic
 * (fetch, LiveKit WebRTC/DTLS, expo-file-system uploads, OTel exporters);
 * a JS fetch shim would silently miss most of it (files/10 §4). The plugin
 * reads `expo.extra.certificatePins` (an array of {host, pins[]} with
 * base64 SPKI SHA-256 values) and writes:
 *   - Android: res/xml/network_security_config.xml with <pin-set> entries,
 *     wired via android:networkSecurityConfig on the application tag;
 *   - iOS: NSPinnedDomains with NSPinnedLeafIdentities in Info.plist.
 *
 * With NO pins configured it deliberately writes NOTHING: the production
 * hosts and their SPKI hashes are awaiting-human (docs/evidence/INT-131.md)
 * and an empty pin-set would either no-op or brick TLS depending on the
 * platform — neither is acceptable silently. Expo Go never runs plugin
 * output, so pinning is only ever claimed for dev builds carrying this
 * config (see src/lib/auth/pinning.ts for the honest runtime status).
 */
const { withAndroidManifest, withDangerousMod, withInfoPlist } = require("expo/config-plugins");
const fs = require("fs");
const path = require("path");

const NETWORK_CONFIG_FILE = "network_security_config.xml";

function readPins(config) {
  const extra = (config.expo ?? config).extra ?? {};
  const pins = extra.certificatePins ?? [];
  return pins.filter(
    (entry) =>
      entry && typeof entry.host === "string" && Array.isArray(entry.pins) && entry.pins.length > 0,
  );
}

function androidXml(domains) {
  const sets = domains
    .map((d) => {
      const pins = d.pins.map((p) => `      <pin digest="SHA-256">${p}</pin>`).join("\n");
      return [
        `  <domain-config cleartextTrafficPermitted="false">`,
        `    <domain includeSubdomains="true">${d.host}</domain>`,
        `    <pin-set>`,
        pins,
        `    </pin-set>`,
        `  </domain-config>`,
      ].join("\n");
    })
    .join("\n");
  return `<?xml version="1.0" encoding="utf-8"?>\n<network-security-config>\n${sets}\n</network-security-config>\n`;
}

function withAndroidPinning(config, domains) {
  config = withDangerousMod(config, [
    "android",
    (modConfig) => {
      const resXml = path.join(
        modConfig.modRequest.platformProjectRoot,
        "app",
        "src",
        "main",
        "res",
        "xml",
      );
      fs.mkdirSync(resXml, { recursive: true });
      fs.writeFileSync(path.join(resXml, NETWORK_CONFIG_FILE), androidXml(domains));
      return modConfig;
    },
  ]);
  return withAndroidManifest(config, (modConfig) => {
    const application = modConfig.modResults.manifest.application?.[0];
    if (application) {
      application.$["android:networkSecurityConfig"] = "@xml/network_security_config";
    }
    return modConfig;
  });
}

function withIosPinning(config, domains) {
  return withInfoPlist(config, (modConfig) => {
    const pinned = {};
    for (const domain of domains) {
      pinned[domain.host] = {
        NSIncludesSubdomains: true,
        NSPinnedLeafIdentities: domain.pins.map((p) => ({ "SPKI-SHA256-BASE64": p })),
      };
    }
    modConfig.modResults.NSAppTransportSecurity = {
      ...(modConfig.modResults.NSAppTransportSecurity ?? {}),
      NSPinnedDomains: pinned,
    };
    return modConfig;
  });
}

module.exports = function withCertificatePinning(config) {
  const domains = readPins(config);
  if (domains.length === 0) {
    // awaiting-human: no pins recorded yet — emit nothing, claim nothing
    return config;
  }
  return withIosPinning(withAndroidPinning(config, domains), domains);
};
