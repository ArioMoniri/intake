/**
 * INT-138 — Kayıtlarım: camera + file upload, AV/processing states,
 * confirm-before-use, provenance boxes.
 *
 * INT-229 built the upload half against the INT-197 endpoints and this issue
 * finishes the acceptance line. React Native has no DOM and the vitest lane
 * has no renderer, so what CAN be proved here is the wiring and the arithmetic
 * — the same shape `overflow.spec.ts` and `typed_intake.spec.ts` use, and for
 * the same reason.
 *
 * Two of the four clauses land whole. The other two land as a MECHANISM behind
 * a shut gate, and the file says so out loud rather than pretending otherwise:
 * nothing publishes document extraction over the API today, so the only
 * production `ExtractionSource` is the one that refuses. The cards and the
 * provenance panel are real, typed and exercised against a stub source here;
 * on a device they render when a feed exists. That is
 * HUMAN_BLOCKERS.md rule 2 applied to an unbuilt dependency rather than an
 * unanswered question: build the mechanism, wire the gate, make it fail
 * closed, leave the content empty.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { readFontMetrics } from "./fontMetrics";
import { en } from "@/lib/i18n/en";
import { tr } from "@/lib/i18n/tr";
import { APP_STEPS } from "@/lib/prefs/appearance";
import { scaledSize, spacing } from "@/lib/theme";

const MOBILE = join(__dirname, "..");
const SCREEN = "src/app/(tabs)/records.tsx";
const READING = "src/components/RecordReading.tsx";
const CARD = "src/components/ConfirmCard.tsx";
const PANEL = "src/components/SourceBoxPanel.tsx";
const API = "src/lib/records/api.ts";
const EXTRACTION = "src/lib/records/extraction.ts";

const metrics = readFontMetrics(
  join(MOBILE, "node_modules/@expo-google-fonts/inter/400Regular/Inter_400Regular.ttf"),
);

function read(relativePath: string): string {
  const source = readFileSync(join(MOBILE, relativePath), "utf8");
  expect(source.length, `${relativePath} is empty`).toBeGreaterThan(0);
  return source;
}

/** Code only, comments dropped — a module that documents a ban is not guilty of it. */
function code(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

/* ------------------------------------------------------------------ */
/* 1. "camera+file upload"                                             */
/* ------------------------------------------------------------------ */

describe("the patient can photograph a report as well as pick a file", () => {
  const screen = code(read(SCREEN));

  it("offers the camera and the file picker as two distinct affordances", () => {
    expect(screen).toContain("launchCameraAsync");
    expect(screen).toContain("getDocumentAsync");
    expect(screen).toContain("records.camera");
    expect(screen).toContain("records.upload");
  });

  it("asks for the camera permission and answers a refusal honestly", () => {
    expect(screen).toContain("requestCameraPermissionsAsync");
    expect(screen).toContain("records.err.camera");
  });

  it("puts a capture through the SAME pre-check and upload as a picked file", () => {
    // A second upload path is a second place the allow-list can be forgotten.
    expect(screen).toContain("cameraFile");
    expect(code(read(API))).toContain("export function cameraFile");
    expect(screen.match(/await upload\(/g) ?? []).toHaveLength(1);
  });

  it("declares the camera and asks for no broad storage access", () => {
    // `expo-image-picker`'s own library manifest declares READ_/WRITE_EXTERNAL
    // _STORAGE for the camera-roll path this app never invokes, so the voice
    // plugin blocks both with tools:node="remove" (INT-138).
    const app = JSON.parse(read("app.json")) as {
      expo: { plugins: unknown[]; android: { permissions: string[] } };
    };
    expect(app.expo.android.permissions).toContain("android.permission.CAMERA");
    const plugin = read("plugins/withVoiceAudio.js");
    expect(plugin).toContain("android.permission.READ_EXTERNAL_STORAGE");
    expect(plugin).toContain("android.permission.WRITE_EXTERNAL_STORAGE");
    // The picker's config plugin is deliberately NOT registered: its
    // `microphonePermission: false` would block RECORD_AUDIO app-wide.
    expect(JSON.stringify(app.expo.plugins)).not.toContain("expo-image-picker");
  });

  it("localises the camera usage string the way the microphone one is", () => {
    // Invariant 5, and the mechanism withVoiceAudio.js already names: the
    // Info.plist string comes from `expo.locales`, so tr stays the source of
    // truth and Apple shows the patient's own language.
    const trPlist = JSON.parse(read("src/locales/app-tr.json")) as Record<string, string>;
    const enPlist = JSON.parse(read("src/locales/app-en.json")) as Record<string, string>;
    expect(trPlist.NSCameraUsageDescription?.trim().length).toBeGreaterThan(0);
    expect(enPlist.NSCameraUsageDescription?.trim().length).toBeGreaterThan(0);
    expect(trPlist.NSCameraUsageDescription).not.toBe(enPlist.NSCameraUsageDescription);
  });

  it("pins MAXIMUM_QUALITY so the document's pixels are not re-encoded", () => {
    // `quality: 1` routes Android to RawImageExporter (a straight copyFile).
    // Compressing a photograph of printed text degrades the one thing the
    // extraction pipeline exists to read; the metadata that rides along with a
    // raw copy is handled by the JPEG strip instead. Behaviour of the strip
    // itself is asserted in api.test.ts against real bytes, not in source text.
    const camera = screen.slice(screen.indexOf("launchCameraAsync"));
    expect(camera.slice(0, 200)).toContain("quality: 1");
  });
});

/* ------------------------------------------------------------------ */
/* 2. "AV/processing states"                                           */
/* ------------------------------------------------------------------ */

describe("two different states, told apart in words", () => {
  it("keeps the three AV scan states as worded chips (INT-229)", () => {
    const screen = code(read(SCREEN));
    expect(screen).toContain("SCAN_STATE_KEY");
    for (const key of ["records.state.scanning", "records.state.ready", "records.state.rejected"]) {
      expect(tr[key as keyof typeof tr]?.trim().length).toBeGreaterThan(0);
    }
  });

  it("carries a SEPARATE processing state for reading the document", () => {
    // Scanned-for-malware and read-for-content are different questions with
    // different answers, and one chip cannot say both.
    const reading = code(read(READING));
    expect(reading).toContain("records.state.reading");
    expect(reading).toContain("records.reading.title");
  });

  it("says a document that could not be read was not read, without alarm", () => {
    const reading = code(read(READING));
    expect(reading).toContain("records.reading.refused");
    for (const word of ["hata", "başarısız", "uyarı"]) {
      expect(tr["records.reading.refused"].toLowerCase()).not.toContain(word);
    }
  });

  it("reads only documents the scanner passed", () => {
    expect(code(read(READING))).toContain('"clean"');
  });
});

/* ------------------------------------------------------------------ */
/* 3. "confirm-before-use"                                             */
/* ------------------------------------------------------------------ */

describe("the patient agrees with a line, and cannot rewrite it", () => {
  const card = code(read(CARD));

  it("offers exactly two verdicts and no editor", () => {
    expect(card).toContain("records.card.yes");
    expect(card).toContain("records.card.no");
  });

  it("has no text entry of any kind on the card", () => {
    // Invariant 22: no free numeric text entry on the clinical critical path.
    // A confirm card that let a patient retype a lab value would be exactly
    // that, and would also mint a value `confirm_record_item` cannot accept —
    // it carries the observation over unchanged.
    for (const token of ["TextInput", "keyboardType", "onChangeText", "numeric", "editable"]) {
      expect(card, `ConfirmCard reaches ${token}`).not.toContain(token);
    }
  });

  it("shows a card as confirmed only once the write was acknowledged", () => {
    expect(code(read(READING))).toContain("applyDecision");
    expect(code(read(EXTRACTION))).toContain("acknowledged");
  });

  it("surfaces the unit conflict on the card rather than tidying it away", () => {
    // INT-121: the magnitude stays unscaled and the flag rides along. A screen
    // that hid the flag behind a clean-looking value would undo the guard.
    expect(card).toContain("unitConflict");
    expect(card).toContain("records.card.unitConflict");
  });

  it("never truncates a card line — a Turkish tail carries the negation", () => {
    for (const token of ["numberOfLines", "ellipsizeMode", "adjustsFontSizeToFit"]) {
      expect(card, `ConfirmCard/${token}`).not.toContain(token);
      expect(code(read(PANEL)), `SourceBoxPanel/${token}`).not.toContain(token);
    }
  });

  it("offers no cards at all on the dev tier — never a faked extraction", () => {
    const screen = code(read(SCREEN));
    const dev = screen.slice(screen.indexOf("function DevRecords"), screen.indexOf("type Phase"));
    expect(dev).not.toContain("RecordReading");
  });
});

/* ------------------------------------------------------------------ */
/* 4. "provenance boxes"                                               */
/* ------------------------------------------------------------------ */

describe("where on the page this came from, not how sure the machine is", () => {
  const panel = code(read(PANEL));

  it("draws the box from the extraction's own normalised rectangle", () => {
    expect(panel).toContain("boxFrame");
    // The page number renders through the shared atom helper, which is where
    // `records.prov.page` and the useGrouping rule live.
    expect(panel).toContain("pageAtom");
    expect(code(read(EXTRACTION))).toContain("records.prov.page");
  });

  it("says in words where the box sits, for a reader who cannot see it", () => {
    expect(panel).toContain("boxRegionKey");
    for (const key of ["records.prov.top", "records.prov.middle", "records.prov.bottom"]) {
      expect(tr[key as keyof typeof tr]?.trim().length).toBeGreaterThan(0);
    }
  });

  it("offers the document itself, which is the full-fidelity provenance", () => {
    expect(panel).toContain("records.prov.open");
  });

  it("expresses no confidence, anywhere", () => {
    // Invariant 20 and HB-A13: no accuracy figure has been measured, so the
    // screen expresses PROVENANCE instead. A percentage here would be a
    // performance claim invented by a designer.
    for (const source of [panel, code(read(CARD)), code(read(EXTRACTION))]) {
      for (const token of ["confidence", "certainty", "score", "accuracy", "probability"]) {
        expect(source, `records surface reaches ${token}`).not.toContain(token);
      }
    }
    for (const [key, value] of Object.entries(tr)) {
      if (key.startsWith("records.")) {
        expect(value, key).not.toMatch(/%|yüzde/);
      }
    }
  });
});

/* ------------------------------------------------------------------ */
/* 5. Invariant 6 — a source box is a coordinate into a patient's page  */
/* ------------------------------------------------------------------ */

describe("nothing on this path reaches a log, a trace or an analytics event", () => {
  it.each([EXTRACTION, CARD, PANEL, READING])("%s writes to no console", (module) => {
    expect(code(read(module))).not.toContain("console.");
  });

  it.each([EXTRACTION, CARD, PANEL, READING])("%s emits no telemetry", (module) => {
    const source = code(read(module));
    for (const token of ["telemetry", "captureError", "trackEvent", "metrics"]) {
      expect(source, `${module} reaches ${token}`).not.toContain(token);
    }
  });

  it("keeps the picked filename on the device, as INT-229 left it", () => {
    const api = code(read(API));
    expect(api).toContain("const docNames = new Map<string, string>()");
    expect(api).not.toContain("file_name");
  });

  it("speaks none of this — no numeral on this screen reaches a TTS lane", () => {
    // Invariant 22's first clause. The records path has no speech at all, and
    // this is the assertion that keeps it that way.
    for (const module of [EXTRACTION, CARD, PANEL, READING, SCREEN]) {
      const source = code(read(module));
      for (const token of ["speak", "Tts", "tts", "expo-speech", "voice/"]) {
        expect(source, `${module} reaches ${token}`).not.toContain(token);
      }
    }
  });
});

/* ------------------------------------------------------------------ */
/* 6. Reachability across the app's own text steps (INT-136, INT-295)   */
/* ------------------------------------------------------------------ */

const PHONE_WIDTHS = [375, 402] as const;
/** The pill's own horizontal chrome: `paddingHorizontal: spacing.lg` a side. */
const BUTTON_CHROME = 2 * spacing.lg;

const NEW_LABEL_KEYS = [
  "records.camera",
  "records.card.yes",
  "records.card.no",
  "records.card.show",
  "records.card.hide",
  "records.prov.open",
] as const;

describe("every new control label is reachable at every APP_STEPS size", () => {
  it("has at least one label that does NOT fit a row at the largest step", () => {
    // The bound has to be shown to be needed, or wrapping is decoration.
    const row = Math.min(...PHONE_WIDTHS) - 2 * spacing.screen;
    const widest = Math.max(
      ...NEW_LABEL_KEYS.flatMap((key) => [tr[key], en[key]]).map(
        (label) => BUTTON_CHROME + metrics.advance(label, scaledSize("body", 2.0)),
      ),
    );
    expect(widest).toBeGreaterThan(row);
  });

  it("leaves room for a glyph beside the chrome at every step, so the label can wrap", () => {
    for (const phone of PHONE_WIDTHS) {
      const row = phone - 2 * spacing.screen;
      for (const scale of APP_STEPS) {
        const widestGlyph = Math.max(
          ...NEW_LABEL_KEYS.flatMap((key) => [...tr[key], ...en[key]]).map((glyph) =>
            metrics.advance(glyph, scaledSize("body", scale)),
          ),
        );
        expect(BUTTON_CHROME + widestGlyph, `${phone}pt @${scale}`).toBeLessThanOrEqual(row);
      }
    }
  });

  it("stacks the two verdicts instead of splitting the row between them", () => {
    // Half a row at 2.0 is 148 pt of usable width; "Hayır, doğru değil" needs
    // more than that on its own line, and a row that cannot wrap would push it
    // off-screen with no horizontal scroll to reach it (the INT-295 defect).
    const card = code(read(CARD));
    const decisions = /decisions:\s*\{[\s\S]*?\}/.exec(card);
    expect(decisions, "ConfirmCard has no `decisions` style to inspect").not.toBeNull();
    expect(decisions![0]).not.toContain('flexDirection: "row"');
  });
});

/* ------------------------------------------------------------------ */
/* 7. Invariant 5 — tr is the source of truth, en mirrors it            */
/* ------------------------------------------------------------------ */

const NEW_KEYS = [
  "records.camera",
  "records.err.camera",
  "records.state.reading",
  "records.reading.kicker",
  "records.reading.title",
  "records.reading.body",
  "records.reading.refused",
  "records.confirm.kicker",
  "records.confirm.intro",
  "records.card.yes",
  "records.card.no",
  "records.card.yesHint",
  "records.card.noHint",
  "records.card.show",
  "records.card.hide",
  "records.card.showHint",
  "records.card.unitConflict",
  "records.card.confirmed",
  "records.card.declined",
  "records.card.notSaved",
  "records.prov.page",
  "records.prov.figure",
  "records.prov.top",
  "records.prov.middle",
  "records.prov.bottom",
  "records.prov.open",
] as const;

describe("the INT-138 copy exists in both catalogues", () => {
  it.each(NEW_KEYS)("%s is present, non-empty and not left in English", (key) => {
    expect(tr[key]?.trim().length, `tr/${key}`).toBeGreaterThan(0);
    expect(en[key]?.trim().length, `en/${key}`).toBeGreaterThan(0);
    expect(tr[key], `${key} was never translated`).not.toBe(en[key]);
  });

  it("addresses the patient as siz, in the -in register for in-flow controls", () => {
    for (const key of ["records.camera", "records.card.show", "records.prov.open"]) {
      expect(tr[key as keyof typeof tr]).toMatch(/(in|ın|un|ün)\b/);
    }
  });
});

/* ------------------------------------------------------------------ */
/* 8. The gate that is shut, and the fact that it is shut              */
/* ------------------------------------------------------------------ */

describe("nothing publishes extraction yet, and the screen says so", () => {
  it("wires the screen to the refusing source", () => {
    expect(code(read(SCREEN))).toContain("noExtractionFeed");
  });

  it("has exactly one production source, and it is the one that refuses", () => {
    const extraction = code(read(EXTRACTION));
    const sources = extraction.match(/:\s*ExtractionSource\s*=/g) ?? [];
    expect(sources, "a second production ExtractionSource appeared").toHaveLength(1);
    expect(extraction).toContain("noExtractionFeed");
  });

  it("keeps the consent gate INT-229 put in front of the whole screen", () => {
    const screen = code(read(SCREEN));
    expect(screen).toContain("useClinicalScreenPrivacy()");
    expect(screen).toMatch(/consents\?\.documents/);
  });
});
