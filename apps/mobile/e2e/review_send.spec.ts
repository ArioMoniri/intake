/**
 * INT-137 — Review & send + Doctor Link QR + CSAT prompt.
 *
 * Acceptance (docs/backlog/issues.yaml): *"section-level scope UI; consent
 * summary; send; status timeline; one-tap CSAT with reason chips; never
 * blocks send"*.
 *
 * Same shape and the same reason as me.spec.ts and nav.spec.ts: React Native
 * has no DOM, so a rendered assertion needs a device. What CAN be proved from
 * the tree is that the wiring exists and that the dangerous shortcuts are
 * absent. The behaviour of the two pure modules is proved next to them
 * (`src/lib/intake/share.test.ts`, `src/lib/intake/csat.test.ts`); this file
 * is the acceptance the backlog names, plus the negative controls that make
 * "never blocks send" and "no invented Doctor Link" hold structurally rather
 * than by inspection.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

import { en } from "../src/lib/i18n/en";
import { tr, type MessageKey } from "../src/lib/i18n/tr";
import { NOTE_SECTION_IDS } from "../src/lib/intake/note";

const MOBILE = join(__dirname, "..");
const SRC = join(MOBILE, "src");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

const TREE: { name: string; source: string }[] = walk(SRC)
  .filter((p) => /\.tsx?$/.test(p) && !p.includes(".test."))
  .map((path) => ({
    name: relative(MOBILE, path).split(sep).join("/"),
    source: readFileSync(path, "utf8"),
  }))
  .sort((a, b) => a.name.localeCompare(b.name));

function file(name: string): string {
  const found = TREE.find((f) => f.name === name);
  expect(found, `${name} is missing`).toBeDefined();
  return found!.source;
}

/**
 * The file with its comments removed. The negative controls below look for
 * things that must not EXIST — a bearer token, a base64 payload, an average.
 * A doc comment that says "no bearer token is minted here" is the opposite of
 * a violation, and matching it would make the control fire on its own
 * explanation. So the controls read code, and the one control that is *about*
 * the prose reads the raw source instead.
 */
function code(name: string): string {
  return file(name)
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/^\s*\/\/.*$/gm, " ");
}

const REVIEW = "src/app/(tabs)/visits/[visitId]/review.tsx";
const CSAT_PROMPT = "src/components/CsatPrompt.tsx";
const CSAT_LIB = "src/lib/intake/csat.ts";
const SHARE_LIB = "src/lib/intake/share.ts";

/** The send CTA's `onPress` body, as source — the object the safety claims sit on. */
function sendHandler(): string {
  const source = file(REVIEW);
  const start = source.indexOf('label={t("review.send")}');
  expect(start, "the send CTA is gone from review.tsx").toBeGreaterThan(-1);
  const open = source.indexOf("onPress={", start);
  expect(open, "the send CTA has no onPress").toBeGreaterThan(-1);
  // Balance the braces of the JSX expression container so the slice is the
  // handler and nothing after it.
  let depth = 0;
  let i = source.indexOf("{", open);
  for (; i < source.length; i += 1) {
    if (source[i] === "{") depth += 1;
    if (source[i] === "}") {
      depth -= 1;
      if (depth === 0) break;
    }
  }
  return source.slice(open, i + 1);
}

/* ------------------------------------------------------------------ */
/* 1. Section-level scope UI                                           */
/* ------------------------------------------------------------------ */

describe("section-level scope UI", () => {
  it("gives every section a switch that names the section it governs", () => {
    const source = file(REVIEW);
    expect(source).toContain('accessibilityRole="switch"');
    expect(source).toContain('type: "scope"');
    expect(source).toContain("withContext(");
  });

  it("keeps the scope switch out of the send path — the CTA never reads a scope", () => {
    expect(sendHandler()).not.toMatch(/scopes|shared|summary/);
  });
});

/* ------------------------------------------------------------------ */
/* 2. Consent summary — what, with whom, until when                    */
/* ------------------------------------------------------------------ */

describe("consent summary above Gönder (02 §5.4)", () => {
  it("exists as its own derivation, not a second reading of the scopes", () => {
    expect(file(SHARE_LIB)).toContain("export function shareSummary");
    expect(file(SHARE_LIB)).toContain("sentSections");
  });

  it("is rendered on the review screen with all three of §5.4's parts", () => {
    const source = file(REVIEW);
    expect(source).toContain("shareSummary(");
    expect(source).toContain('t("review.consent.sections")');
    expect(source).toContain('t("review.consent.recipient")');
    expect(source).toContain('t("review.consent.until")');
  });

  it("states the expiry ANCHOR and renders no countdown (02 §2)", () => {
    expect(file(SHARE_LIB)).toContain('"visit_datetime"');
    expect(file(SHARE_LIB)).not.toMatch(/new Date|Date\.now/);
    expect(tr["review.consent.untilValue"]).not.toMatch(/\d/);
  });
});

/* ------------------------------------------------------------------ */
/* 3. Status timeline after send                                       */
/* ------------------------------------------------------------------ */

describe("status timeline (02 §5.4 'after send')", () => {
  it("shows the ladder on this screen instead of navigating away from it", () => {
    const source = file(REVIEW);
    expect(source).toContain("StatusLadder");
    expect(source).toContain("effectiveStatus(");
  });

  it("the send handler no longer replaces the route — §5.4's surface must be reachable", () => {
    expect(sendHandler()).not.toMatch(/router\.(replace|push|back|navigate)/);
  });
});

/* ------------------------------------------------------------------ */
/* 4. One-tap CSAT with reason chips                                   */
/* ------------------------------------------------------------------ */

describe("one-tap CSAT with reason chips", () => {
  it("renders the question and the chips through the proven Segmented control", () => {
    const source = file(CSAT_PROMPT);
    expect(source).toContain("Segmented");
    expect(source).toContain("CSAT_SCORES");
    expect(source).toContain("CSAT_REASONS");
  });

  it("is mounted only from the review screen's already-sent branch", () => {
    const source = file(REVIEW);
    expect(source).toContain("<CsatPrompt");
    const sentBranch = source.slice(source.indexOf("sent ? ("));
    expect(sentBranch).toContain("<CsatPrompt");
  });

  it("owns its own consent gate and renders nothing without a grant", () => {
    const source = file(CSAT_PROMPT);
    expect(source).toContain("csatCollectable");
    expect(source).toContain("return null");
  });

  it("never renders a score back — no average, rate or target (invariant 20)", () => {
    const source = code(CSAT_PROMPT) + code(CSAT_LIB);
    expect(source).not.toMatch(/average|ortalama|toFixed|percent|yüzde|hedef/i);
  });

  it("speaks the scale in words, so no numeral reaches the patient (invariant 22)", () => {
    for (const choice of [
      "csat.score.veryBad",
      "csat.score.bad",
      "csat.score.ok",
      "csat.score.good",
      "csat.score.veryGood",
    ] as MessageKey[]) {
      expect(tr[choice], choice).not.toMatch(/\d/);
    }
  });
});

/* ------------------------------------------------------------------ */
/* 5. Never blocks send — held structurally, not by inspection         */
/* ------------------------------------------------------------------ */

describe("never blocks send", () => {
  it("the CTA carries no disabled state", () => {
    const source = file(REVIEW);
    const cta = source.slice(source.indexOf('label={t("review.send")}') - 200);
    expect(cta.slice(0, 600)).not.toContain("disabled");
  });

  it("the handler mentions no consent, no CSAT and no satisfaction", () => {
    expect(sendHandler()).not.toMatch(/csat|consent|satisfaction|Csat/i);
  });

  it("the handler is one dispatch behind one id guard — no branch, no return, no await", () => {
    const handler = sendHandler();
    expect(handler).toContain('updateNote(visitId, { type: "send" })');
    expect(handler).not.toMatch(/await|then\(|catch\(|return |else/);
  });

  it("the screen reaches no network, so an offline device still sends", () => {
    const source = code(REVIEW) + code(CSAT_PROMPT) + code(CSAT_LIB) + code(SHARE_LIB);
    expect(source).not.toMatch(/fetch\(|authedFetch|XMLHttpRequest|axios/);
  });

  it("the CSAT modules hold nothing the note path reads", () => {
    expect(file(CSAT_LIB)).not.toContain('from "./note"');
    expect(file(CSAT_PROMPT)).not.toContain("useSession");
  });
});

/* ------------------------------------------------------------------ */
/* 6. Doctor Link QR — the negative control                            */
/* ------------------------------------------------------------------ */

describe("no Doctor Link payload is invented while INT-150 is open", () => {
  const SURFACE = () => code(REVIEW) + code(CSAT_PROMPT) + code(CSAT_LIB) + code(SHARE_LIB);

  it("emits no link, scheme or token of any kind", () => {
    expect(SURFACE()).not.toMatch(/https?:\/\/|intake:\/\/|doctorLink|doctor_link|bearer/i);
  });

  it("serialises no part of the note into a scannable payload", () => {
    expect(SURFACE()).not.toMatch(/JSON\.stringify|btoa\(|base64|toBase64|encodeURI/);
  });

  it("pulls in no QR or barcode dependency — a licence audit nobody ran (invariant 19)", () => {
    const manifest = readFileSync(join(MOBILE, "package.json"), "utf8");
    expect(manifest).not.toMatch(/qr|barcode/i);
    expect(TREE.some((f) => /qr/i.test(f.name))).toBe(false);
  });

  it("says in the file why it is absent, so the next reader does not add one", () => {
    expect(file(REVIEW)).toContain("INT-150");
  });
});

/* ------------------------------------------------------------------ */
/* 7. Strings — invariants 2 and 5                                     */
/* ------------------------------------------------------------------ */

describe("every new string is Turkish-first and mirrored", () => {
  const NEW_KEYS = (Object.keys(tr) as MessageKey[]).filter(
    (key) => key.startsWith("csat.") || key.startsWith("review.consent."),
  );

  it("carries all of §5.4's chips and all three summary parts", () => {
    expect(NEW_KEYS.length).toBeGreaterThanOrEqual(16);
  });

  it("has an en mirror for every one of them (invariant 5)", () => {
    for (const key of NEW_KEYS) {
      expect(en[key], key).toBeDefined();
      expect(en[key].trim().length, key).toBeGreaterThan(0);
    }
  });

  it("addresses the patient as siz, never sen (invariant 2)", () => {
    for (const key of NEW_KEYS) {
      expect(tr[key], key).not.toMatch(/\bsen\b|\bsana\b|\bsenin\b/iu);
    }
  });

  it("makes the optionality of the CSAT question explicit in the copy itself", () => {
    expect(tr["csat.optional"]).toMatch(/isteğe bağlı/i);
    expect(tr["csat.optional"]).toMatch(/gönderildi/i);
  });

  it("never alarms beyond the triage action — no clinical or urgency wording", () => {
    for (const key of NEW_KEYS) {
      expect(tr[key], key).not.toMatch(/acil|112|tehlike|risk|teşhis|tanı|tedavi/i);
    }
  });
});

/* ------------------------------------------------------------------ */
/* 8. Invariant 6 — no PHI anywhere near a log                         */
/* ------------------------------------------------------------------ */

describe("no answer, score or section reaches a log", () => {
  it("the new surface logs nothing at all", () => {
    for (const name of [REVIEW, CSAT_PROMPT, CSAT_LIB, SHARE_LIB]) {
      expect(code(name), name).not.toMatch(/console\.(log|info|warn|error|debug)/);
    }
  });
});

/* ------------------------------------------------------------------ */
/* 9. INT-304 — one section vocabulary, note builder ↔ server scope     */
/* ------------------------------------------------------------------ */

/** The server's `SectionId` literal, parsed from the FastAPI schema source. */
function serverSectionIds(): string[] {
  const schemaPath = join(
    __dirname,
    "..",
    "..",
    "..",
    "services",
    "api",
    "src",
    "intake_api",
    "schemas.py",
  );
  const src = readFileSync(schemaPath, "utf8");
  const block = src.match(/SectionId = Literal\[([\s\S]*?)\]/);
  expect(block, "SectionId Literal not found in services/api schemas.py").not.toBeNull();
  return [...block![1].matchAll(/"([a-z_]+)"/g)].map((m) => m[1]);
}

describe("the share scope covers every section the note emits", () => {
  it("declares the full set as one vocabulary with no drift or duplication", () => {
    expect(NOTE_SECTION_IDS.length).toBe(9);
    expect(new Set(NOTE_SECTION_IDS).size).toBe(NOTE_SECTION_IDS.length);
  });

  it("keeps NOTE_SECTION_IDS equal to the ids buildNote actually emits", () => {
    // Every `id: "..."` in note.ts is a section buildNote pushes; the declared
    // vocabulary must be exactly that set, or the summary and scope UI would key
    // on a section the note never produces (or miss one it does).
    const emitted = new Set(
      [...file("src/lib/intake/note.ts").matchAll(/\bid:\s*"([a-z_]+)"/g)].map((m) => m[1]),
    );
    expect(emitted).toEqual(new Set(NOTE_SECTION_IDS));
  });

  it("mirrors the server-side SectionId exactly, in note order (02 §5.4)", () => {
    // The consent summary a patient reads before Gönder is the set the server
    // scope check enforces afterwards — so the two lists must be identical.
    expect(serverSectionIds()).toEqual([...NOTE_SECTION_IDS]);
  });
});
