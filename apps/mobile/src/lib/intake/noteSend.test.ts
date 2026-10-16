/**
 * INT-510 — the patient's send reaches the clinic.
 *
 * Before this issue "Gönder" only flipped the note to `sent` on the phone: no
 * client sent it, so the share centre and the Doctor Link then asked the
 * server about a visit id it had never seen. What this file pins is the pure
 * half of the fix — the body the phone builds, the rule that reads the
 * server's answer, and the reducer that will only say "sent" once the server
 * has said so:
 *
 * - the PUT body carries exactly the scoped-on sections; a section the
 *   patient turned off never leaves the phone, and its id is recorded as
 *   withheld (`scopes[id] = false`) so the server still has the choice;
 * - the PUT goes to the SERVER visit id, never the local one, and the server
 *   visit is resolved first;
 * - 200 with `status: "sent"` is the only path to `sent`; a refused share
 *   consent is a worded refusal, an unreachable server is a queued send, and
 *   neither touches the status;
 * - the reducer freezes the note while a send is in flight and treats an edit
 *   to a queued note as a cancelled send, so what goes is what was confirmed.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { emptyNoteState, noteReducer, restoreNote, type NoteAction, type NoteState } from "./note";
import {
  classifyPut,
  deliverNote,
  deliveryLine,
  hasQueuedSend,
  notePutBody,
  retryQueuedSends,
  sendsDue,
  settleSend,
  type NotePutBody,
  type NoteSendPorts,
  type PutResult,
  type ResolveResult,
} from "./noteSend";

const LOCAL_ID = "v-local-1";
const SERVER_ID = "6b0f2c1e-4d7a-4a51-9c3e-0d1f2a3b4c5d";
const OTHER_SERVER_ID = "0c9e8d7f-1a2b-4c3d-8e9f-a0b1c2d3e4f5";

/** A phone-verified account with nothing carried forward (INT-131). */
const PATIENT = { kind: "otp" as const, carriedFacts: [] };
const SYNTHETIC = { kind: "dev" as const, carriedFacts: [] };

/** The shared contract: the body the server's own test PUTs (tests/api/test_note_send.py). */
const APP_NOTE_PUT = JSON.parse(
  readFileSync(
    join(
      __dirname,
      "..",
      "..",
      "..",
      "..",
      "..",
      "tests",
      "fixtures",
      "note_send",
      "app_note_put.json",
    ),
    "utf8",
  ),
) as NotePutBody;

function apply(state: NoteState, ...actions: NoteAction[]): NoteState {
  return actions.reduce(noteReducer, state);
}

/** Complaint + duration shared, past surgery answered and then scoped OFF. */
function withheldPmhNote(): NoteState {
  return apply(
    emptyNoteState(),
    { type: "answer", questionId: "complaint", values: ["pain"] },
    { type: "answer", questionId: "duration", values: ["days"] },
    { type: "answer", questionId: "pmh_surgery", values: ["yes"] },
    { type: "scope", sectionId: "pmh", shared: false },
  );
}

function answered(status: number, error = "", noteStatus: string | null = null): PutResult {
  return { status, error, noteStatus };
}

interface FakePorts extends NoteSendPorts {
  resolves: number;
  puts: { serverVisitId: string; body: NotePutBody }[];
}

function ports(
  resolve: ResolveResult | (() => ResolveResult),
  put: PutResult | ((serverVisitId: string) => PutResult),
): FakePorts {
  const fake: FakePorts = {
    resolves: 0,
    puts: [],
    async resolveServerVisit() {
      fake.resolves += 1;
      return typeof resolve === "function" ? resolve() : resolve;
    },
    async putNote(serverVisitId, body) {
      fake.puts.push({ serverVisitId, body });
      return typeof put === "function" ? put(serverVisitId) : put;
    },
  };
  return fake;
}

describe("the body the phone sends", () => {
  it("is exactly the shared contract the server's own test accepts", () => {
    expect(notePutBody(withheldPmhNote(), PATIENT)).toEqual(APP_NOTE_PUT);
  });

  it("carries only the scoped-on sections — a withheld section never leaves the phone", () => {
    const body = notePutBody(withheldPmhNote(), PATIENT)!;
    expect(body.sections.map((s) => s.id)).toEqual(["chief_complaint", "hpi"]);
    // the near miss: the withheld content is nowhere in the serialised body
    expect(JSON.stringify(body)).not.toContain("ameliyat");
    // ...but the CHOICE is: the server records the withholding affirmatively
    expect(body.scopes.pmh).toBe(false);
    expect(body.status).toBe("sent");
  });

  it("names every section the note built, so default-on stays explicit", () => {
    const body = notePutBody(withheldPmhNote(), PATIENT)!;
    expect(Object.keys(body.scopes).sort()).toEqual(["chief_complaint", "hpi", "pmh"]);
    expect(body.scopes.chief_complaint).toBe(true);
  });

  it("is nothing at all when every section is scoped off — there is nothing to share", () => {
    const off = apply(
      withheldPmhNote(),
      { type: "scope", sectionId: "chief_complaint", shared: false },
      { type: "scope", sectionId: "hpi", shared: false },
    );
    expect(notePutBody(off, PATIENT)).toBeNull();
  });
});

describe("reading the server's answer", () => {
  it("only a 200 that says sent is a delivery", () => {
    expect(classifyPut({ status: 200, error: "", noteStatus: "sent" })).toBe("delivered");
    // the near miss: a 200 that came back as a draft is not "sent"
    expect(classifyPut({ status: 200, error: "", noteStatus: "draft" })).toBe("failed");
  });

  it("a refused share consent is its own worded refusal", () => {
    expect(classifyPut({ status: 403, error: "consent_required", noteStatus: null })).toBe(
      "consent",
    );
  });

  it("the age gate's three codes are a refusal, never a retry", () => {
    for (const code of [
      "guardian_consent_required",
      "dob_unverified",
      "jurisdiction_unsupported",
    ]) {
      expect(classifyPut({ status: 403, error: code, noteStatus: null })).toBe("not_allowed");
    }
  });

  it("an expired session asks for a sign-in, not a retry", () => {
    expect(classifyPut({ status: 401, error: "", noteStatus: null })).toBe("session");
  });

  it("a visit the server does not know is stale, so it is resolved again", () => {
    expect(classifyPut({ status: 404, error: "not_found", noteStatus: null })).toBe("stale");
  });

  it("a server that is busy or down keeps the send queued", () => {
    for (const status of [408, 429, 500, 502, 503, 504]) {
      expect(classifyPut({ status, error: "", noteStatus: null }), String(status)).toBe("queued");
    }
  });

  it("a body the server refuses is a failure, not a queue that never drains", () => {
    expect(classifyPut({ status: 422, error: "validation_error", noteStatus: null })).toBe(
      "failed",
    );
  });
});

describe("delivering one note", () => {
  it("resolves the server visit first and PUTs to the server id, never the local one", async () => {
    const fake = ports({ id: SERVER_ID }, answered(200, "", "sent"));
    const outcome = await deliverNote(
      { note: withheldPmhNote(), account: PATIENT, knownServerVisitId: null },
      fake,
    );
    expect(outcome).toEqual({ kind: "delivered", serverVisitId: SERVER_ID });
    expect(fake.resolves).toBe(1);
    expect(fake.puts).toHaveLength(1);
    expect(fake.puts[0].serverVisitId).toBe(SERVER_ID);
    expect(fake.puts[0].serverVisitId).not.toBe(LOCAL_ID);
    expect(fake.puts[0].body).toEqual(APP_NOTE_PUT);
  });

  it("reuses the id the session already holds — one PUT, no second lookup", async () => {
    const fake = ports({ id: OTHER_SERVER_ID }, answered(200, "", "sent"));
    const outcome = await deliverNote(
      { note: withheldPmhNote(), account: PATIENT, knownServerVisitId: SERVER_ID },
      fake,
    );
    expect(outcome).toEqual({ kind: "delivered", serverVisitId: SERVER_ID });
    expect(fake.resolves).toBe(0);
  });

  it("a send without consent is refused in words and never delivered", async () => {
    const fake = ports({ id: SERVER_ID }, answered(403, "consent_required"));
    const outcome = await deliverNote(
      { note: withheldPmhNote(), account: PATIENT, knownServerVisitId: null },
      fake,
    );
    expect(outcome).toEqual({ kind: "refused", reason: "consent", serverVisitId: SERVER_ID });
    // one attempt: a consent refusal is not retried behind the patient's back
    expect(fake.puts).toHaveLength(1);
  });

  it("queues when the server cannot be reached to resolve the visit", async () => {
    const fake = ports("unreachable", answered(200, "", "sent"));
    const outcome = await deliverNote(
      { note: withheldPmhNote(), account: PATIENT, knownServerVisitId: null },
      fake,
    );
    expect(outcome).toEqual({ kind: "queued", serverVisitId: null });
    expect(fake.puts).toHaveLength(0);
  });

  it("queues when the PUT itself does not land, keeping the resolved id", async () => {
    const fake = ports({ id: SERVER_ID }, "unreachable");
    const outcome = await deliverNote(
      { note: withheldPmhNote(), account: PATIENT, knownServerVisitId: null },
      fake,
    );
    expect(outcome).toEqual({ kind: "queued", serverVisitId: SERVER_ID });
  });

  it("re-resolves once when the held id has gone stale, then sends to the fresh one", async () => {
    const fake = ports({ id: OTHER_SERVER_ID }, (id) =>
      id === SERVER_ID ? answered(404, "not_found") : answered(200, "", "sent"),
    );
    const outcome = await deliverNote(
      { note: withheldPmhNote(), account: PATIENT, knownServerVisitId: SERVER_ID },
      fake,
    );
    expect(outcome).toEqual({ kind: "delivered", serverVisitId: OTHER_SERVER_ID });
    expect(fake.puts.map((p) => p.serverVisitId)).toEqual([SERVER_ID, OTHER_SERVER_ID]);
  });

  it("does not loop on a visit the server keeps refusing to know", async () => {
    const fake = ports({ id: SERVER_ID }, answered(404, "not_found"));
    const outcome = await deliverNote(
      { note: withheldPmhNote(), account: PATIENT, knownServerVisitId: null },
      fake,
    );
    expect(outcome).toEqual({ kind: "refused", reason: "failed", serverVisitId: null });
    expect(fake.puts).toHaveLength(1);
  });

  it("a session the server no longer honours is a refusal, not a queue", async () => {
    expect(
      await deliverNote(
        { note: withheldPmhNote(), account: PATIENT, knownServerVisitId: null },
        ports("session", answered(200, "", "sent")),
      ),
    ).toEqual({ kind: "refused", reason: "session", serverVisitId: null });
    expect(
      await deliverNote(
        { note: withheldPmhNote(), account: PATIENT, knownServerVisitId: SERVER_ID },
        ports({ id: SERVER_ID }, "session"),
      ),
    ).toEqual({ kind: "refused", reason: "session", serverVisitId: SERVER_ID });
  });

  it("the synthetic dev session sends nothing anywhere", async () => {
    const fake = ports({ id: SERVER_ID }, answered(200, "", "sent"));
    const outcome = await deliverNote(
      { note: withheldPmhNote(), account: SYNTHETIC, knownServerVisitId: null },
      fake,
    );
    expect(outcome).toEqual({ kind: "refused", reason: "synthetic", serverVisitId: null });
    expect(fake.resolves + fake.puts.length).toBe(0);
  });

  it("a note with nothing shared reaches no network and says why", async () => {
    const off = apply(
      withheldPmhNote(),
      { type: "scope", sectionId: "chief_complaint", shared: false },
      { type: "scope", sectionId: "hpi", shared: false },
    );
    const fake = ports({ id: SERVER_ID }, answered(200, "", "sent"));
    const outcome = await deliverNote(
      { note: off, account: PATIENT, knownServerVisitId: null },
      fake,
    );
    expect(outcome).toEqual({ kind: "refused", reason: "nothing_shared", serverVisitId: null });
    expect(fake.resolves + fake.puts.length).toBe(0);
  });

  it("a consent refused while making the server visit is still a consent refusal", async () => {
    const fake = ports("consent", answered(200, "", "sent"));
    expect(
      await deliverNote(
        { note: withheldPmhNote(), account: PATIENT, knownServerVisitId: null },
        fake,
      ),
    ).toEqual({ kind: "refused", reason: "consent", serverVisitId: null });
    expect(fake.puts).toHaveLength(0);
  });

  it("a visit the server refuses to create is a failure", async () => {
    expect(
      await deliverNote(
        { note: withheldPmhNote(), account: PATIENT, knownServerVisitId: null },
        ports("refused", answered(200, "", "sent")),
      ),
    ).toEqual({ kind: "refused", reason: "failed", serverVisitId: null });
  });
});

describe("the note's own state: 'sent' only on the server's word", () => {
  it("Gönder starts a send; the note stays a draft", () => {
    const s = apply(withheldPmhNote(), { type: "send" });
    expect(s.status).toBe("draft");
    expect(s.delivery).toEqual({ phase: "sending" });
  });

  it("only the server's confirmation makes it sent", () => {
    const s = apply(withheldPmhNote(), { type: "send" }, { type: "delivered" });
    expect(s.status).toBe("sent");
    expect(s.delivery).toEqual({ phase: "idle" });
  });

  it("an unreachable server leaves it queued — and still a draft", () => {
    const s = apply(withheldPmhNote(), { type: "send" }, { type: "queued" });
    expect(s.status).toBe("draft");
    expect(s.delivery).toEqual({ phase: "queued" });
  });

  it("a refused consent leaves it a draft and keeps the reason to word", () => {
    const s = apply(withheldPmhNote(), { type: "send" }, { type: "refused", reason: "consent" });
    expect(s.status).toBe("draft");
    expect(s.delivery).toEqual({ phase: "refused", reason: "consent" });
  });

  it("a confirmation with no send in flight changes nothing", () => {
    const draft = withheldPmhNote();
    expect(noteReducer(draft, { type: "delivered" })).toBe(draft);
    expect(noteReducer(draft, { type: "queued" })).toBe(draft);
    expect(noteReducer(draft, { type: "refused", reason: "consent" })).toBe(draft);
  });

  it("the note is frozen while the send is in flight — what goes is what was confirmed", () => {
    const sending = apply(withheldPmhNote(), { type: "send" });
    expect(noteReducer(sending, { type: "scope", sectionId: "pmh", shared: true })).toBe(sending);
    expect(
      noteReducer(sending, { type: "answer", questionId: "complaint", values: ["fever"] }),
    ).toBe(sending);
  });

  it("an edit to a queued note cancels the queued send, so it is confirmed again", () => {
    const queued = apply(withheldPmhNote(), { type: "send" }, { type: "queued" });
    const edited = noteReducer(queued, { type: "scope", sectionId: "pmh", shared: true });
    expect(edited.scopes.pmh).toBe(true);
    expect(edited.delivery).toEqual({ phase: "idle" });
  });

  it("pressing Gönder again on a queued or refused note tries again", () => {
    const queued = apply(withheldPmhNote(), { type: "send" }, { type: "queued" });
    expect(noteReducer(queued, { type: "send" }).delivery).toEqual({ phase: "sending" });
    const refused = apply(
      withheldPmhNote(),
      { type: "send" },
      { type: "refused", reason: "consent" },
    );
    expect(noteReducer(refused, { type: "send" }).delivery).toEqual({ phase: "sending" });
  });

  it("a sent note does not send again", () => {
    const sent = apply(withheldPmhNote(), { type: "send" }, { type: "delivered" });
    expect(noteReducer(sent, { type: "send" })).toBe(sent);
  });

  it("retry moves a queued send back into flight, and touches nothing else", () => {
    const queued = apply(withheldPmhNote(), { type: "send" }, { type: "queued" });
    expect(noteReducer(queued, { type: "retry" }).delivery).toEqual({ phase: "sending" });
    const draft = withheldPmhNote();
    expect(noteReducer(draft, { type: "retry" })).toBe(draft);
  });
});

describe("restoring a sealed draft", () => {
  it("a draft written before INT-510 gains an idle delivery", () => {
    const { delivery: _dropped, ...old } = withheldPmhNote();
    expect(restoreNote(old as NoteState).delivery).toEqual({ phase: "idle" });
  });

  it("a 'sent' written before INT-510 never reached a server, so it is a draft again", () => {
    // No build before this issue had a note-sync client: every stored "sent"
    // without a delivery record is a send the clinic never received.
    const { delivery: _dropped, ...old } = apply(
      withheldPmhNote(),
      { type: "send" },
      { type: "delivered" },
    );
    const restored = restoreNote(old as NoteState);
    expect(restored.status).toBe("draft");
    expect(restored.delivery).toEqual({ phase: "idle" });
  });

  it("a queued send survives the restart as queued", () => {
    const queued = apply(withheldPmhNote(), { type: "send" }, { type: "queued" });
    expect(restoreNote(queued)).toEqual(queued);
  });

  it("a confirmed send survives the restart as sent", () => {
    const sent = apply(withheldPmhNote(), { type: "send" }, { type: "delivered" });
    expect(restoreNote(sent).status).toBe("sent");
  });
});

describe("the session's outbox, as pure rules", () => {
  const notes = (): Record<string, NoteState> => ({
    [LOCAL_ID]: apply(withheldPmhNote(), { type: "send" }),
    "v-local-2": apply(withheldPmhNote(), { type: "send" }, { type: "queued" }),
    "v-local-3": withheldPmhNote(),
  });

  it("sends what is in flight and not already being sent", () => {
    expect(sendsDue(notes(), new Set())).toEqual([LOCAL_ID]);
    expect(sendsDue(notes(), new Set([LOCAL_ID]))).toEqual([]);
  });

  it("knows when a queued send is waiting, and retries all of them at once", () => {
    expect(hasQueuedSend(notes())).toBe(true);
    const retried = retryQueuedSends(notes());
    expect(retried["v-local-2"].delivery).toEqual({ phase: "sending" });
    expect(hasQueuedSend(retried)).toBe(false);
    // the in-flight send and the idle draft are left exactly as they were
    expect(retried[LOCAL_ID]).toEqual(notes()[LOCAL_ID]);
    expect(retried["v-local-3"]).toEqual(notes()["v-local-3"]);
  });

  it("with nothing queued, retry hands back the very same notes", () => {
    const idle = { "v-local-3": withheldPmhNote() };
    expect(hasQueuedSend(idle)).toBe(false);
    expect(retryQueuedSends(idle)).toBe(idle);
  });

  it("settles an outcome onto the note it was for", () => {
    const settled = settleSend(notes(), LOCAL_ID, { kind: "delivered", serverVisitId: SERVER_ID });
    expect(settled[LOCAL_ID].status).toBe("sent");
  });

  it("never brings back a note the session wiped while the send was in flight", () => {
    const wiped: Record<string, NoteState> = {};
    expect(settleSend(wiped, LOCAL_ID, { kind: "delivered", serverVisitId: SERVER_ID })).toBe(
      wiped,
    );
  });
});

describe("the line the review screen shows", () => {
  it("says nothing while idle", () => {
    expect(deliveryLine({ phase: "idle" })).toBeNull();
  });

  it("speaks a sending or queued send as status, and a refusal as an error", () => {
    expect(deliveryLine({ phase: "sending" })).toEqual({
      tone: "status",
      key: "review.delivery.sending",
    });
    expect(deliveryLine({ phase: "queued" })).toEqual({
      tone: "status",
      key: "review.delivery.queued",
    });
    expect(deliveryLine({ phase: "refused", reason: "consent" })).toEqual({
      tone: "error",
      key: "review.delivery.consent",
    });
  });

  it("gives every refusal its own true sentence", () => {
    const keys = (
      ["consent", "not_allowed", "session", "nothing_shared", "synthetic", "failed"] as const
    ).map((reason) => deliveryLine({ phase: "refused", reason })?.key);
    expect(new Set(keys).size).toBe(keys.length);
  });
});

describe("no PHI reaches a log (invariant 6)", () => {
  it("the send path logs nothing", () => {
    const source = readFileSync(join(__dirname, "noteSend.ts"), "utf8");
    expect(source).not.toMatch(/console\.(log|info|warn|error|debug)/);
  });
});
