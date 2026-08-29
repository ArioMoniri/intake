/**
 * The adversarial scrub suite (INT-145; CLAUDE.md invariant 6).
 *
 * A crash report is the single most likely place for PHI to leave the device:
 * stack frames capture local variables, breadcrumbs capture screen text, and a
 * network breadcrumb captures a URL. So this suite does not check that a
 * blocklist caught some patterns — it plants four real identifiers into every
 * limb of a crash event and asserts that none of them appears anywhere in the
 * bytes the transport would send.
 *
 * The near-miss control matters as much as the plants: six legitimate,
 * allow-listed values must SURVIVE. Without them a scrubber that returned an
 * empty object would pass every leak assertion, and the suite could not fail.
 */
import { describe, expect, it } from "vitest";

import { buildEnvelopeBody } from "./envelope";
import {
  ALLOWED_TAG_KEYS,
  BREADCRUMB_CATEGORIES,
  UNCLASSIFIED_ERROR_CODE,
  buildCrashReport,
  type TelemetryIdentity,
} from "./scrub";

/** A Turkish symptom sentence — exactly what a breadcrumb of screen text or a
 * Pydantic-style error string would carry. */
const SYMPTOM_TR = "Üç gündür göğsümde baskı ve nefes darlığı var.";
/** A TR mobile number in the form intake_platform.redaction matches. */
const PHONE = "05321234567";
/** A checksum-valid TC Kimlik, the same fixture the server suite uses. */
const TCKN = "10000000146";
/** An uploaded document's file name: a patient name plus a date. */
const DOC_TITLE = "Ayşe Yılmaz kan tahlili 2026-03-12.pdf";

const PLANTED = [SYMPTOM_TR, PHONE, TCKN, DOC_TITLE] as const;

const IDENTITY: TelemetryIdentity = {
  appVersion: "0.1.0",
  buildId: "eas-1841",
  sbomDigest: `sha256:${"ab".repeat(32)}`,
  platform: "ios",
  osVersion: "18.4",
  deviceModel: "iPhone15,2",
  environment: "dev",
  releaseChannel: "preview",
  tenantId: "acibadem-maslak",
};

/** The near-miss control: every value here is legitimate and allow-listed, so
 * each one MUST come through. They are what makes a leak assertion falsifiable. */
const SESSION_HASH = "0f1e2d3c4b5a69788796a5b4c3d2e1f0";
const PROTOCOL_HASH = "9c".repeat(32);

/**
 * One crash event, shaped the way a crash reporter really hands them over —
 * every limb carrying a planted identifier next to a legitimate value.
 * Deliberately typed `unknown` at the boundary: the builder must read only the
 * paths it enumerates, never spread whatever it was given.
 */
function plantedEvent(): unknown {
  return {
    // The exception message: a SafeError boundary should have removed this
    // upstream, and the scrubber must not depend on that having happened.
    message: `extraction failed for "${SYMPTOM_TR}"`,
    errorCode: SYMPTOM_TR,
    level: "error",
    exception: {
      values: [
        {
          type: "DialogueStreamError",
          value: `${SYMPTOM_TR} (tckn ${TCKN})`,
          stacktrace: {
            frames: [
              {
                module: "src/lib/dialogue/stream.ts",
                function: "openStream",
                lineno: 182,
                colno: 11,
                in_app: true,
                // The captured local — the pcm-buffer leak class, files/10 §3.
                vars: { utterance: SYMPTOM_TR, phone: PHONE, pcm: "<960KB>" },
                context_line: `  const utterance = "${SYMPTOM_TR}";`,
                pre_context: [DOC_TITLE],
                post_context: [TCKN],
              },
              // A frame whose module is itself an identifier: dropped whole.
              { module: PHONE, function: TCKN, lineno: 1 },
            ],
          },
        },
      ],
    },
    breadcrumbs: {
      values: [
        {
          category: "navigation",
          event: "screen_opened",
          route: "/visits/{visitId}/intake",
          // Screen text riding along on a legitimate breadcrumb.
          message: SYMPTOM_TR,
          data: { title: DOC_TITLE, patientPhone: PHONE },
        },
        {
          category: "network",
          event: "request_failed",
          status: 502,
          // A real network breadcrumb's URL, query string and all.
          url: `https://api.example.test/records?title=${encodeURIComponent(DOC_TITLE)}&tckn=${TCKN}`,
          route: `/records/${TCKN}`,
        },
        // A breadcrumb whose category is not on the closed list: dropped whole.
        { category: "user_input", event: "typed", message: SYMPTOM_TR },
      ],
    },
    tags: {
      session_id_hash: SESSION_HASH,
      protocol_hash: PROTOCOL_HASH,
      prompt_version: "v3",
      screen_id: "visit_intake",
      // Planted onto allow-listed keys, and onto keys that are not on the list.
      app_version: PHONE,
      patient_phone: PHONE,
      tckn: TCKN,
      complaint: SYMPTOM_TR,
      document: DOC_TITLE,
    },
    extra: { transcript: SYMPTOM_TR, document: DOC_TITLE, tckn: TCKN, phone: PHONE },
    contexts: { patient: { name: "Ayşe Yılmaz", phone: PHONE } },
    user: { id: TCKN, username: "Ayşe Yılmaz", email: "ayse@example.test" },
    request: {
      url: `https://api.example.test/visits?q=${encodeURIComponent(SYMPTOM_TR)}`,
      data: { transcript: SYMPTOM_TR },
      headers: { Authorization: "Bearer secret", Cookie: `tckn=${TCKN}` },
    },
    attachments: [{ filename: DOC_TITLE, data: SYMPTOM_TR }],
    timestampMs: 1_772_000_000_000,
  };
}

describe("buildCrashReport — deny by default", () => {
  it("emits nothing the allow-list does not name, across every limb", () => {
    const report = buildCrashReport(IDENTITY, plantedEvent());
    const serialised = JSON.stringify(report);
    for (const secret of PLANTED) {
      expect(serialised, `planted value escaped into the report: ${secret}`).not.toContain(secret);
    }
  });

  it("leaks none of the four plants into the bytes actually sent", () => {
    const report = buildCrashReport(IDENTITY, plantedEvent());
    const body = buildEnvelopeBody(
      { publicKey: "f00d", projectId: "1", envelopeUrl: "http://127.0.0.1:8010/api/1/envelope/" },
      report,
    );
    for (const secret of PLANTED) {
      expect(body, `planted value escaped into the envelope: ${secret}`).not.toContain(secret);
    }
    // Percent-encoded and JSON-escaped forms too: a URL-encoded transcript is
    // still a transcript.
    expect(body).not.toContain(encodeURIComponent(SYMPTOM_TR));
    expect(body).not.toContain(encodeURIComponent(DOC_TITLE));
    // Nothing outside printable ASCII survives at all: every allow-listed
    // value is an id, a code or a number, so a letter with a Turkish
    // diacritic anywhere in the body means free text escaped through a limb
    // nobody thought about.
    const nonAscii = [...body].filter((ch) => ch.codePointAt(0)! > 126);
    expect(nonAscii).toEqual([]);
  });

  it("NEAR-MISS CONTROL: the legitimate values do survive", () => {
    const report = buildCrashReport(IDENTITY, plantedEvent());
    // If this block ever passes vacuously the leak assertions above prove
    // nothing — an empty report leaks nothing.
    expect(report.tags.session_id_hash).toBe(SESSION_HASH);
    expect(report.tags.protocol_hash).toBe(PROTOCOL_HASH);
    expect(report.tags.prompt_version).toBe("v3");
    expect(report.tags.screen_id).toBe("visit_intake");
    expect(report.tags.app_version).toBe("0.1.0");
    expect(report.tags.tenant_id).toBe("acibadem-maslak");
    expect(report.exceptionType).toBe("DialogueStreamError");
    expect(report.frames).toEqual([
      { module: "src/lib/dialogue/stream.ts", function: "openStream", lineno: 182, colno: 11 },
    ]);
    expect(report.breadcrumbs).toEqual([
      { category: "navigation", event: "screen_opened", route: "/visits/{visitId}/intake" },
      { category: "network", event: "request_failed", status: 502 },
    ]);
  });

  it("an unreadable error code becomes the unclassified code, never the text", () => {
    const report = buildCrashReport(IDENTITY, plantedEvent());
    expect(report.errorCode).toBe(UNCLASSIFIED_ERROR_CODE);
    const coded = buildCrashReport(IDENTITY, { errorCode: "dialogue_stream_failed" });
    expect(coded.errorCode).toBe("dialogue_stream_failed");
  });

  it("a tag key off the allow-list cannot appear even with a harmless value", () => {
    const report = buildCrashReport(IDENTITY, { tags: { locale: "tr-TR", feature: "intake" } });
    expect(Object.keys(report.tags)).not.toContain("feature");
    expect(Object.keys(report.tags)).not.toContain("locale");
    for (const key of Object.keys(report.tags)) {
      expect(ALLOWED_TAG_KEYS, `${key} is not on the allow-list`).toContain(key);
    }
  });

  it("drops an allow-listed tag whose value does not match that key's shape", () => {
    // The key is on the list; the value is a phone number. Per-key shapes are
    // what stop an identifier riding in on a legitimate key name.
    const report = buildCrashReport(IDENTITY, { tags: { session_id_hash: PHONE } });
    expect(report.tags.session_id_hash).toBeUndefined();
  });

  it("the fingerprint is derived from allow-listed fields only", () => {
    const a = buildCrashReport(IDENTITY, plantedEvent());
    const b = buildCrashReport(IDENTITY, {
      ...(plantedEvent() as Record<string, unknown>),
      message: "a completely different message",
      extra: { transcript: "something else entirely" },
    });
    // Changing only fields the builder never reads cannot change the
    // fingerprint — so the fingerprint cannot be a hash of patient text.
    expect(a.fingerprint).toBe(b.fingerprint);
    expect(a.fingerprint).toMatch(/^[0-9a-f]{16}$/);
  });

  it("has no field for a message, a user, a request or an attachment", () => {
    const report = buildCrashReport(IDENTITY, plantedEvent());
    for (const forbidden of ["message", "user", "request", "extra", "contexts", "attachments"]) {
      expect(Object.keys(report), `${forbidden} must not exist on a report`).not.toContain(
        forbidden,
      );
    }
  });

  it("keeps the breadcrumb category list closed", () => {
    expect([...BREADCRUMB_CATEGORIES]).toEqual([
      "lifecycle",
      "navigation",
      "network",
      "permission",
    ]);
  });

  it("never runs a shape against an unbounded string", () => {
    // Structurally a valid route template, but 800 characters of it. The
    // length check happens before the regex, so nothing spins.
    const long = "/a".repeat(400);
    const report = buildCrashReport(IDENTITY, {
      breadcrumbs: { values: [{ category: "network", event: "request_failed", route: long }] },
    });
    expect(report.breadcrumbs).toEqual([{ category: "network", event: "request_failed" }]);
  });

  it("survives hostile shapes without throwing", () => {
    for (const hostile of [null, undefined, 42, "a string", [], { exception: 7 }, { tags: [] }]) {
      expect(() => buildCrashReport(IDENTITY, hostile)).not.toThrow();
    }
    expect(buildCrashReport(IDENTITY, null).frames).toEqual([]);
  });
});

describe("identity fields", () => {
  it("drops an identity field that fails its shape rather than sending it", () => {
    const report = buildCrashReport({ ...IDENTITY, appVersion: PHONE, deviceModel: TCKN }, {});
    expect(report.tags.app_version).toBeUndefined();
    expect(report.tags.device_model).toBeUndefined();
    expect(report.tags.build_id).toBe("eas-1841");
  });

  it("platform and environment are closed enumerations", () => {
    const report = buildCrashReport({ ...IDENTITY, platform: "ios", environment: "dev" }, {});
    expect(report.tags.platform).toBe("ios");
    expect(report.tags.environment).toBe("dev");
  });
});
