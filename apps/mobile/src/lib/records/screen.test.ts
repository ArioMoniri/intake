/**
 * INT-229 — Kayıtlarım source-fact pins.
 *
 * The vitest lane has no renderer (component rendering is exercised via Expo
 * tooling), so these tests pin the FACTS of the screen source the way
 * e2e/auth.spec.ts pins the clinical-privacy guards:
 * - the documents consent scope gates the screen (existing session consents);
 * - dev-tier accounts keep the honest fixture list — no upload affordance,
 *   a calm note instead (never a faked upload);
 * - the OTP branch carries the real upload flow (expo-document-picker
 *   limited to the server allow-list) and opens clean documents via
 *   expo-web-browser;
 * - scan states are WORDS in both catalogs — colour never the only carrier.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { en } from "@/lib/i18n/en";
import { tr } from "@/lib/i18n/tr";

const SCREEN = readFileSync(join(__dirname, "..", "..", "app", "(tabs)", "records.tsx"), "utf8");

function slice(src: string, from: string, to?: string): string {
  const start = src.indexOf(from);
  expect(start, `marker ${from}`).toBeGreaterThanOrEqual(0);
  if (to === undefined) {
    return src.slice(start);
  }
  const end = src.indexOf(to);
  expect(end, `marker ${to}`).toBeGreaterThan(start);
  return src.slice(start, end);
}

describe("consent gate — documents scope from the existing session consents", () => {
  it("keeps the clinical screen-privacy guard", () => {
    expect(SCREEN).toContain("useClinicalScreenPrivacy()");
  });

  it("gates on consents.documents and shows guidance, not a dead end", () => {
    expect(SCREEN).toMatch(/consents\?\.documents/);
    const gate = slice(SCREEN, "records.consent.kicker");
    expect(gate).toContain("records.consent.title");
    expect(SCREEN).toContain("records.consent.cta");
  });
});

describe("dev-tier honesty — fixture list, no upload, a calm note", () => {
  const dev = slice(SCREEN, "function DevRecords", "function OtpRecords");

  it("renders the fixture list with the synthetic footer", () => {
    expect(dev).toContain("records.synthetic");
  });

  it("carries the dev-tier note and NO upload affordance", () => {
    expect(dev).toContain("records.devNote");
    expect(dev).not.toContain("records.upload");
    expect(dev).not.toContain("DocumentPicker");
  });
});

describe("OTP branch — the real document flow", () => {
  const otp = slice(SCREEN, "function OtpRecords");

  it("uploads via expo-document-picker limited to the server allow-list", () => {
    expect(otp).toContain("getDocumentAsync");
    expect(otp).toContain("ALLOWED_DOCUMENT_TYPES");
    expect(otp).toContain("records.upload");
    expect(otp).toContain("records.uploading");
  });

  it("runs the client pre-check before any upload", () => {
    expect(otp).toContain("precheckFile");
  });

  it("opens clean documents via expo-web-browser (already a dependency)", () => {
    expect(SCREEN).toContain("expo-web-browser");
    expect(otp).toContain("openBrowserAsync");
  });

  it("shows the scan state as a worded chip on every row", () => {
    expect(otp).toContain("ScanChip");
    expect(SCREEN).toContain("SCAN_STATE_KEY");
  });

  it("handles the unreachable API with the guidance-block pattern", () => {
    expect(otp).toContain("records.offline.kicker");
    expect(otp).toContain("records.retry");
  });

  it("guides to visit creation when no visit exists (never a dead end)", () => {
    expect(otp).toContain("records.needVisit.kicker");
    expect(otp).toContain("/(tabs)/visits/new");
  });
});

describe("scan-state words — colour never the only carrier (tr first, en mirror)", () => {
  it("tr carries the three worded states", () => {
    expect(tr["records.state.scanning"]).toBe("Taranıyor");
    expect(tr["records.state.ready"]).toBe("Hazır");
    expect(tr["records.state.rejected"]).toBe("Reddedildi");
  });

  it("en mirrors them with distinct words", () => {
    const words = [
      en["records.state.scanning"],
      en["records.state.ready"],
      en["records.state.rejected"],
    ];
    for (const word of words) {
      expect(word.trim().length).toBeGreaterThan(0);
    }
    expect(new Set(words).size).toBe(3);
  });
});

describe("i18n — the INT-229 keys exist in both catalogs (invariant 5)", () => {
  const KEYS = [
    "records.devNote",
    "records.upload",
    "records.uploading",
    "records.state.scanning",
    "records.state.ready",
    "records.state.rejected",
    "records.doc.pdf",
    "records.doc.image",
    "records.scanningInfo",
    "records.err.type",
    "records.err.size",
    "records.err.network",
    "records.err.session",
    "records.err.consent",
    "records.err.scanUnavailable",
    "records.err.rejected",
    "records.err.generic",
    "records.consent.kicker",
    "records.consent.title",
    "records.consent.body",
    "records.consent.cta",
    "records.needVisit.kicker",
    "records.needVisit.title",
    "records.needVisit.body",
    "records.offline.kicker",
    "records.offline.title",
    "records.offline.body",
    "records.retry",
    "records.visit.kicker",
    "records.visit.choose",
  ] as const;

  it.each(KEYS)("%s exists in tr and en", (key) => {
    expect((tr as Record<string, string>)[key]?.trim().length).toBeGreaterThan(0);
    expect((en as Record<string, string>)[key]?.trim().length).toBeGreaterThan(0);
  });
});
