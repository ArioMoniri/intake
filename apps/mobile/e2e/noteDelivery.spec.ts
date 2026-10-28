/**
 * INT-587 — the note reaches the clinician from a release build.
 *
 * Before this issue "Gönder" changed local state and nothing else: no client
 * called `PUT /v1/visits/{id}/note`, the app could not grant the share consent
 * the server checks on that PUT, and the review screen said "Notunuz
 * gönderildi" on no evidence. The behaviour of the pure modules is proved next
 * to them (src/lib/intake/delivery/*.test.ts, src/lib/consent/share.test.ts,
 * src/lib/shares/stepUp.test.ts). This file is the part a unit test cannot
 * see: the client pinned to the server it talks to, the screens wired to the
 * outbox, and the shortcuts that would make any of it untrue held absent.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

import { en } from "../src/lib/i18n/en";
import { tr, type MessageKey } from "../src/lib/i18n/tr";
import { SHARE_SCOPE } from "../src/lib/consent/ledger";
import { effectiveStatus, emptyNoteState, noteReducer } from "../src/lib/intake/note";
import { NOTE_LIMITS } from "../src/lib/intake/delivery/payload";
import { notePath } from "../src/lib/intake/delivery/transport";

const MOBILE = join(__dirname, "..");
const SRC = join(MOBILE, "src");
const REPO = join(MOBILE, "..", "..");
const API = join(REPO, "services", "api", "src", "intake_api");

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
  }));

function file(name: string): string {
  const found = TREE.find((f) => f.name === name);
  expect(found, `${name} is missing`).toBeDefined();
  return found!.source;
}

/** Code only, comments dropped — prose about a rule is not the rule. */
function code(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

const REVIEW = "src/app/(tabs)/visits/[visitId]/review.tsx";
const DETAIL = "src/app/(tabs)/visits/[visitId]/index.tsx";
const ISSUE_SCREEN = "src/app/(tabs)/visits/[visitId]/issue-link.tsx";
const HUB = "src/app/(tabs)/visits/[visitId]/shares.tsx";
const SESSION = "src/lib/session.tsx";
const DELIVERY_CARD = "src/components/NoteDelivery.tsx";
const SHARE_CONSENT = "src/components/ShareConsentControl.tsx";
const DELIVERY_DIR = "src/lib/intake/delivery/";
const NATIVE = "src/lib/intake/delivery/native.ts";

const DELIVERY_MODULES = () => TREE.filter((f) => f.name.startsWith(DELIVERY_DIR));

/* ------------------------------------------------------------------ */
/* 1 · The client is pinned to the server it talks to                   */
/* ------------------------------------------------------------------ */

describe("the note-sync client speaks the server's existing contract", () => {
  const notes = readFileSync(join(API, "notes.py"), "utf8");
  const schemas = readFileSync(join(API, "schemas.py"), "utf8");

  it("PUTs to the route notes.write_note serves", () => {
    expect(notes).toContain('prefix="/v1/visits/{visit_id}/note"');
    expect(notes).toMatch(/@router\.put\(\s*""/);
    expect(notePath("{visit_id}").replace("%7B", "{").replace("%7D", "}")).toBe(
      "/v1/visits/{visit_id}/note",
    );
    expect(code(file(`${DELIVERY_DIR}transport.ts`))).toContain('method: "PUT"');
  });

  it("grants exactly the share scope the server checks on a send", () => {
    const declared = notes.match(/SHARE_SCOPE = "([^"]+)"/);
    expect(declared, "notes.py no longer declares SHARE_SCOPE").not.toBeNull();
    expect(SHARE_SCOPE).toBe(declared![1]);
  });

  it("refuses locally exactly what the server's NotePut bounds refuse", () => {
    expect(schemas).toMatch(
      /Line = Annotated\[str, StringConstraints\(min_length=1, max_length=2000\)\]/,
    );
    expect(schemas).toMatch(
      /Title = Annotated\[str, StringConstraints\(min_length=1, max_length=200\)\]/,
    );
    expect(schemas).toMatch(/lines: list\[Line\] = Field\(min_length=1, max_length=100\)/);
    expect(NOTE_LIMITS).toMatchObject({ lineChars: 2000, titleChars: 200, linesPerSection: 100 });
  });

  it("asks for a confirmed send, the one status that creates a share", () => {
    expect(schemas).toContain('status: Literal["draft", "sent"]');
    expect(code(file(`${DELIVERY_DIR}payload.ts`))).toContain('status: "sent"');
  });

  it("changes nothing on the server: no new route, no field-level crypto of its own", () => {
    for (const entry of DELIVERY_MODULES()) {
      const source = code(entry.source);
      expect(source, entry.name).not.toMatch(/encrypt_field|EncryptedField|kek|dek_for/i);
    }
  });
});

/* ------------------------------------------------------------------ */
/* 2 · Only a confirmed delivery may say "sent"                         */
/* ------------------------------------------------------------------ */

describe("only a confirmed delivery says the note was sent", () => {
  const frozen = noteReducer(
    noteReducer(emptyNoteState(), { type: "answer", questionId: "complaint", values: ["pain"] }),
    { type: "send" },
  );

  it("a note the patient sent but the server has not confirmed is still a draft", () => {
    expect(effectiveStatus(null, frozen, false)).toBe("draft");
    expect(effectiveStatus("draft", frozen, false)).toBe("draft");
  });

  it("a confirmed delivery is sent", () => {
    expect(effectiveStatus(null, frozen, true)).toBe("sent");
    expect(effectiveStatus("draft", frozen, true)).toBe("sent");
  });

  it("the review screen gates its sent branch on the delivery stage", () => {
    const review = code(file(REVIEW));
    expect(review).toMatch(/const sent =[^;]*"delivered"/);
    expect(review).toContain("<NoteDelivery");
  });

  it("the visit detail passes the delivery to the status it renders", () => {
    const detail = code(file(DETAIL));
    expect(detail).toMatch(/effectiveStatus\([^)]*delivered/);
  });

  it("every 'sent' sentence renders only behind that gate", () => {
    const review = code(file(REVIEW));
    // the exact gate, not the first "sent ? (" anywhere in the file
    const gate = review.indexOf("{sent ? (");
    expect(gate).toBeGreaterThan(-1);
    expect(review.lastIndexOf("{sent ? (")).toBe(gate);
    for (const marker of ['t("review.sentInfo")', "<CsatPrompt", "<StatusLadder"]) {
      expect(review.indexOf(marker), marker).toBeGreaterThan(gate);
    }
  });
});

/* ------------------------------------------------------------------ */
/* 3 · The share consent: docs/legal text, hash-bound, in context       */
/* ------------------------------------------------------------------ */

describe("the share consent is granted in context against the served text", () => {
  it("renders the loader's body, version and binding — never catalog copy", () => {
    const card = code(file(DELIVERY_CARD));
    expect(card).toContain(".body");
    expect(card).toContain(".version");
    expect(card).toContain(".textHash");
    expect(card).toContain("grantShareLocal(");
  });

  it("queues a note only with the receipt a grant returns", () => {
    const card = code(file(DELIVERY_CARD));
    expect(card).toMatch(/enqueueDelivery\([\s\S]*?receipt\)/);
  });

  it("has no İzinleriniz row — the share is asked at the send, never as a toggle", () => {
    expect(code(file("src/lib/consent/purposes.ts"))).not.toMatch(/id: "share/);
  });

  it("the patient can withdraw it from the share centre, apart from the stop control", () => {
    const hub = code(file(HUB));
    expect(hub).toContain("<ShareConsentControl");
    expect(code(file(SHARE_CONSENT))).toContain("withdrawShareLocal(");
  });
});

/* ------------------------------------------------------------------ */
/* 4 · Doctor Link: the server visit, and the step-up seam              */
/* ------------------------------------------------------------------ */

describe("Doctor Link from the app", () => {
  it("issues and lists against the server visit the note was delivered to", () => {
    expect(code(file(ISSUE_SCREEN))).toContain("serverVisitIdOf(");
    expect(code(file(HUB))).toContain("serverVisitIdOf(");
  });

  it("authorises through the typed step-up seam before issuing", () => {
    const screen = code(file(ISSUE_SCREEN));
    const authorise = screen.indexOf("authorizeIssue(");
    const issue = screen.indexOf("issueDoctorLink(");
    expect(authorise).toBeGreaterThan(-1);
    expect(issue).toBeGreaterThan(authorise);
    expect(code(file("src/lib/shares/issue.ts"))).toMatch(/proof: StepUpProof/);
  });
});

/* ------------------------------------------------------------------ */
/* 5 · Native code stays behind a lazy import; nothing is logged        */
/* ------------------------------------------------------------------ */

describe("wiring", () => {
  it("the session reaches the outbox only through a lazy import", () => {
    const session = code(file(SESSION));
    expect(session).toMatch(/import\(\s*["']\.\/intake\/delivery\/native["']\s*\)/);
    expect(session).not.toMatch(/from\s+["']\.\/intake\/delivery/);
  });

  it("only the native module touches a native, auth or records import", () => {
    for (const entry of DELIVERY_MODULES()) {
      if (entry.name === NATIVE) continue;
      const source = code(entry.source);
      expect(source, entry.name).not.toMatch(
        /from "(?:expo-|react-native|@\/lib\/auth|@\/lib\/records)/,
      );
    }
  });

  it("INT-142's sync no longer says no note-sync client ships", () => {
    expect(file("src/lib/intake/offline/sync.ts")).not.toContain("no note-sync client ships");
  });
});

describe("no PHI reaches a log (invariant 6)", () => {
  it("no delivery or consent-step module calls the console or telemetry", () => {
    for (const name of [...DELIVERY_MODULES().map((f) => f.name), DELIVERY_CARD, SHARE_CONSENT]) {
      const source = code(file(name));
      expect(source, name).not.toMatch(/console\.(log|info|warn|error|debug)/);
      expect(source, name).not.toMatch(/captureException|captureMessage|lib\/telemetry/);
    }
  });
});

/* ------------------------------------------------------------------ */
/* 6 · Copy: tr first, mirrored, siz, calm                              */
/* ------------------------------------------------------------------ */

describe("the copy", () => {
  const KEYS = (Object.keys(tr) as MessageKey[]).filter(
    (key) => key.startsWith("delivery.") || key.startsWith("shares.consent."),
  );

  it("exists, and every key is mirrored into English", () => {
    expect(KEYS.length).toBeGreaterThanOrEqual(10);
    for (const key of KEYS) {
      expect(en[key], key).toBeDefined();
      expect(en[key].trim().length, key).toBeGreaterThan(0);
    }
  });

  it("addresses the patient as siz, never sen", () => {
    for (const key of KEYS) {
      expect(tr[key], key).not.toMatch(/\bsen\b|\bsana\b|\bsenin\b/iu);
    }
  });

  it("never says a note waiting on the phone was sent", () => {
    for (const key of KEYS.filter((k) => k.startsWith("delivery."))) {
      expect(tr[key], key).not.toMatch(/gönderildi/i);
      expect(en[key], key).not.toMatch(/\bwas sent\b|\bhas been sent\b/i);
    }
  });

  it("carries no clinical, urgency or numeric wording", () => {
    for (const key of KEYS) {
      expect(tr[key], key).not.toMatch(/acil|112|tehlike|teşhis|tanı|tedavi|\d/i);
    }
  });
});
