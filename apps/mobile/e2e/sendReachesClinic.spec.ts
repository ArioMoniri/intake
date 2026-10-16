/**
 * INT-510 — the patient's send reaches the clinic (GitHub #872).
 *
 * From the INT-498 audit: "Gönder" marked the note `sent` on the phone and
 * nothing else happened. No client sent it, so the share centre and the Doctor
 * Link then called `/v1/visits/{local id}/…` — an id the server never saw — and
 * the server refused.
 *
 * Same split as every spec here (vitest runs on node, nothing renders): the
 * RULES are proved next to them — `src/lib/intake/noteSend.test.ts` (body,
 * outcome, reducer), `noteSendClient.test.ts` (the wire order),
 * `src/lib/shares/{issue,store}.test.ts` (server id on every share call) and
 * `tests/api/test_note_send.py` (the server's side of the same contract). What
 * THIS file holds is the wiring a refactor could quietly undo:
 *
 * 1. the session owns the local→server id map and the outbox, and reaches the
 *    network only through lazy imports (it stays node-importable);
 * 2. every screen that calls `/v1/visits/*` resolves through that map first —
 *    no screen hands a route param to a visit client;
 * 3. the review screen says "sent" only from the note's status, which only the
 *    server's 200 sets, and words every other state;
 * 4. the offline queue is the INT-142 sealed store, not a second one;
 * 5. the server still checks the share consent and audits every share
 *    (invariant 4) — verified here, not re-implemented.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

import { describe, expect, it } from "vitest";

import { en } from "../src/lib/i18n/en";
import { tr, type MessageKey } from "../src/lib/i18n/tr";

const MOBILE = join(__dirname, "..");
const SRC = join(MOBILE, "src");
const REPO = join(MOBILE, "..", "..");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

const TREE = walk(SRC)
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

/** Code without comments, so an explanation never satisfies or trips a control. */
function code(name: string): string {
  return file(name)
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/^\s*\/\/.*$/gm, " ")
    .replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, " ");
}

const SESSION = "src/lib/session.tsx";
const REVIEW = "src/app/(tabs)/visits/[visitId]/review.tsx";
const ISSUE_SCREEN = "src/app/(tabs)/visits/[visitId]/issue-link.tsx";
const SHARES_SCREEN = "src/app/(tabs)/visits/[visitId]/shares.tsx";
const RECORDS_SCREEN = "src/app/(tabs)/records.tsx";
const SEND_LIB = "src/lib/intake/noteSend.ts";
const SEND_CLIENT = "src/lib/intake/noteSendClient.ts";
const OUTBOX = "src/lib/intake/useNoteOutbox.ts";

describe("1 · the session owns the id map and the outbox", () => {
  const session = code(SESSION);
  const outbox = code(OUTBOX);

  it("reaches the send transport and the visit resolver through lazy imports only", () => {
    expect(outbox).toMatch(/import\(\s*["']\.\/noteSendClient["']\s*\)/);
    expect(session).toMatch(/import\(\s*["']\.\/records\/api["']\s*\)/);
    for (const source of [session, outbox]) {
      expect(source).not.toMatch(/from\s+["'][./]*(?:intake\/)?noteSendClient["']/);
      expect(source).not.toMatch(/from\s+["'][./@]*(?:lib\/)?records\/api["']/);
      expect(source).not.toContain("authedFetch");
      expect(source).not.toContain("expo-file-system");
    }
  });

  it("keeps the local→server map and exposes one resolver over it", () => {
    expect(session).toContain("resolveServerVisit");
    expect(session).toContain("rememberServerVisit(");
    // the outbox runs over the SAME map and generation, not copies of them
    expect(session).toMatch(/useNoteOutbox\(\{[^}]*serverVisits[^}]*sendGeneration[^}]*\}\)/);
  });

  it("settles each send on the note it was for, and retries a queued one", () => {
    expect(outbox).toContain("sendsDue(");
    expect(outbox).toContain("settleSend(");
    expect(outbox).toContain("retryQueuedSends");
    expect(outbox).toContain("rememberServerVisit(");
    expect(outbox).toMatch(/generation !== sendGeneration\.current/);
  });

  it("drops an outcome that lands after the patient changed (sign-out, wipe, kiosk)", () => {
    // every reset path bumps the generation, and an outcome from an older
    // generation is never applied — another patient's note cannot be marked sent
    const bumps = session.match(/sendGeneration\.current \+= 1/g) ?? [];
    expect(bumps.length).toBeGreaterThanOrEqual(5);
    // a resolve that lands after a reset is not remembered either
    expect(session).toMatch(/generation === sendGeneration\.current/);
  });

  it("keeps every module it touches inside the constitution's 500-line rule", () => {
    // note.ts is not listed: it stood at 567 lines before this issue, which
    // moved the send's own state out to noteDelivery.ts instead of growing it
    const touched = [
      SESSION,
      OUTBOX,
      SEND_LIB,
      SEND_CLIENT,
      REVIEW,
      "src/lib/intake/noteDelivery.ts",
    ];
    for (const name of touched) {
      expect(file(name).split("\n").length, name).toBeLessThan(500);
    }
  });

  it("forgets the map on every reset, so one patient's server ids never serve another", () => {
    const resets = session.match(/serverVisits\.current = \{\}/g) ?? [];
    expect(resets.length).toBeGreaterThanOrEqual(5);
  });
});

describe("2 · every /v1/visits/* call resolves through the map first", () => {
  it("no screen resolves a server visit on its own", () => {
    for (const entry of TREE.filter((f) => f.name.startsWith("src/app/"))) {
      expect(code(entry.name), entry.name).not.toContain("ensureServerVisit");
    }
  });

  it("the Doctor Link screen issues against the resolved id, never the route param", () => {
    const screen = code(ISSUE_SCREEN);
    expect(screen).toContain("issueDoctorLinkForVisit(");
    expect(screen).toContain("resolveServerVisit");
    expect(screen).not.toMatch(/issueDoctorLink\(\s*visit\b/);
  });

  it("the share centre loads through the resolver", () => {
    const screen = code(SHARES_SCREEN);
    expect(screen).toMatch(/loadShareCentre\(\s*visit,\s*\(id\)\s*=>\s*resolveServerVisit\(id/);
    expect(screen).toContain("resolveServerVisit");
  });

  it("records resolve their visit through the session too", () => {
    const screen = code(RECORDS_SCREEN);
    expect(screen).toContain("resolveServerVisit(");
  });

  it("issuing a link is still owned by one module (INT-311's confinement stands)", () => {
    const callers = TREE.filter(
      (f) => f.name !== "src/lib/shares/issue.ts" && /\bissueDoctorLink\(/.test(code(f.name)),
    ).map((f) => f.name);
    expect(callers).toEqual([]);
  });
});

describe("3 · 'sent' on the phone is the server's word", () => {
  it("the review screen words the send's state from the note, and adds no network", () => {
    const review = code(REVIEW);
    expect(review).toContain("deliveryLine(");
    expect(review).not.toMatch(/fetch\(|authedFetch|noteSendClient/);
  });

  it("the send transport PUTs the note to a server id with status sent", () => {
    const client = code(SEND_CLIENT);
    expect(client).toMatch(/method:\s*"PUT"/);
    expect(client).toContain("/note`");
    expect(client).toContain("encodeURIComponent(serverVisitId)");
    expect(code(SEND_LIB)).toContain('status: "sent"');
  });

  it("only the delivered action makes a note sent", () => {
    // the note builder sets no status at all; the send's module sets it once
    expect(code("src/lib/intake/note.ts")).not.toMatch(/status:\s*"sent"/);
    const delivery = code("src/lib/intake/noteDelivery.ts");
    expect(delivery.match(/status:\s*"sent"/g) ?? []).toHaveLength(1);
    const delivered = delivery.slice(delivery.indexOf('case "delivered"'));
    expect(delivered.slice(0, 120)).toContain('status: "sent"');
  });
});

describe("4 · an offline send waits in the INT-142 sealed store", () => {
  it("the delivery state is part of the note the sealed draft store persists", () => {
    expect(code("src/lib/intake/note.ts")).toMatch(/delivery:\s*NoteDelivery/);
    const drafts = code("src/lib/intake/offline/sessionDrafts.ts");
    expect(drafts).toContain("persistDraft(");
    expect(drafts).toContain("restoreNote(");
  });

  it("no second store holds a queued send", () => {
    for (const name of [SEND_LIB, SEND_CLIENT, OUTBOX]) {
      for (const banned of ["AsyncStorage", "SecureStore", "expo-file-system", "writeAsString"]) {
        expect(code(name), `${name} reaches ${banned}`).not.toContain(banned);
      }
    }
  });
});

describe("5 · the server still checks the share consent and audits every share", () => {
  const notes = readFileSync(
    join(REPO, "services", "api", "src", "intake_api", "notes.py"),
    "utf8",
  );

  it("a send enforces share:previsit_note before the share row exists", () => {
    const sent = notes.slice(notes.indexOf('if payload.status == "sent":'));
    expect(sent.indexOf("ensure_consent(")).toBeGreaterThan(-1);
    expect(sent.indexOf("scope=SHARE_SCOPE")).toBeLessThan(sent.indexOf("create_share("));
  });

  it("every share is written to the hash-chained audit", () => {
    expect(notes).toContain('action="api.note.share"');
  });
});

describe("6 · the copy (invariants 2 and 5)", () => {
  const KEYS = (Object.keys(tr) as MessageKey[]).filter((key) =>
    key.startsWith("review.delivery."),
  );

  it("words every state the send can be in", () => {
    expect(KEYS.sort()).toEqual(
      [
        "review.delivery.consent",
        "review.delivery.empty",
        "review.delivery.failed",
        "review.delivery.notAllowed",
        "review.delivery.queued",
        "review.delivery.sending",
        "review.delivery.synthetic",
      ].sort(),
    );
  });

  it("mirrors each into a distinct English line", () => {
    for (const key of KEYS) {
      expect(en[key], key).toBeDefined();
      expect(en[key], key).not.toBe(tr[key]);
    }
  });

  it("says siz, never sen, and asks nothing in the imperative", () => {
    // Status lines state what happened; they do not instruct. That keeps them
    // clear of both register gates (tests/release/test_i18n_complete.py): no
    // short `-in` in prose and no doubled `-iniz` anywhere.
    const IMPERATIVE =
      /(?:^|\s)(?:edin|girin|verin|deneyin|seçin|açın|yapın|gönderin|bekleyin|ediniz|deneyiniz|açınız|gönderiniz)(?=[\s.,;!?]|$)/iu;
    for (const key of KEYS) {
      expect(tr[key], key).not.toMatch(/\bsen\b|\bsana\b|\bsenin\b/iu);
      expect(tr[key], key).not.toMatch(IMPERATIVE);
    }
  });

  it("never alarms and never names a figure", () => {
    for (const key of KEYS) {
      expect(tr[key], key).not.toMatch(/acil|112|tehlike|risk|teşhis|tanı|tedavi|\d/i);
    }
  });

  it("a refused consent says the note did not go, and why", () => {
    expect(tr["review.delivery.consent"]).toMatch(/gönderilmedi/);
    expect(tr["review.delivery.consent"]).toMatch(/izni/);
    expect(tr["review.delivery.queued"]).toMatch(/henüz gönderilmedi/);
  });
});
