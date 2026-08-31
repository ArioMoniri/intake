/**
 * INT-137 acceptance — "section-level scope UI; consent summary; send; status
 * timeline; one-tap CSAT with reason chips; never blocks send".
 *
 * Three of those six clauses were already standing when this issue opened, and
 * this file says which and pins them rather than rebuilding them:
 *
 *   - **section-level scope UI** — INT-179. One `accessibilityRole="switch"`
 *     chip per `buildNote` section, `scope` in the reducer, `sentSections`
 *     doing the exclusion. Pinned in §1.
 *   - **send** — INT-179. `noteReducer` `send` flips the 02 §5.1 ladder.
 *     Pinned in §3.
 *   - **status timeline** — INT-179 built `StatusLadder` and put it on the
 *     visit detail. What was missing is 02 §5.4's *"after send: status
 *     timeline"* on the review surface itself, which is §4.
 *
 * What this file adds is the consent summary (§2), the CSAT prompt (§5), the
 * safety property that nothing optional can ever gate the send (§6), and the
 * Doctor Link decision recorded as a negative control (§7).
 *
 * WHAT THIS FILE CANNOT DO, said plainly and in the idiom the other specs in
 * this folder already use: the vitest lane runs in `node` with no renderer,
 * `react-native` ships Flow source it cannot import, and this container has no
 * simulator. Nothing here is rendered and nothing here is a device
 * observation. Two kinds of assertion are made instead — behaviour of the pure
 * modules, which is real behaviour, and STRUCTURE read out of the screen
 * source, which proves what the screen declares and never what it looks like.
 * Where a clause can only be settled by a device run it is named as such in
 * docs/evidence/INT-137.md and not asserted here.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { getTestAccount } from "../src/lib/dev/accounts";
import { freshLedger, grant, applyTexts, type LedgerState } from "../src/lib/consent/ledger";
import { en } from "../src/lib/i18n/en";
import { t } from "../src/lib/i18n";
import { tr, type MessageKey } from "../src/lib/i18n/tr";
import {
  CSAT_REASONS,
  CSAT_SCORES,
  csatCollectable,
  csatReducer,
  csatResponse,
  emptyCsat,
} from "../src/lib/intake/csat";
import { buildNote, emptyNoteState, noteReducer, sentSections } from "../src/lib/intake/note";
import { SHARE_EXPIRY_ANCHOR, shareSummary } from "../src/lib/intake/share";

const MOBILE = join(__dirname, "..");
const APP = join(MOBILE, "src", "app");
const COMPONENTS = join(MOBILE, "src", "components");
const REPO = join(MOBILE, "..", "..");

const read = (...segments: string[]) => readFileSync(join(...segments), "utf8");

/**
 * Comments are prose ABOUT the code, and several assertions below are about
 * what the code does — a docstring that explains why no bearer token is
 * encoded must not read as a bearer token being encoded. Same technique
 * `tests/release/test_i18n_complete.py` uses on the same tree.
 */
function code(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

const REVIEW = read(APP, "(tabs)/visits/[visitId]", "review.tsx");
const REVIEW_CODE = code(REVIEW);
const CSAT_PROMPT = read(COMPONENTS, "CsatPrompt.tsx");
const CSAT_PROMPT_CODE = code(CSAT_PROMPT);

const ayse = getTestAccount("ayse")!;
const VISIT = { hospital: "Ankara Şehir Hastanesi", department: "İç Hastalıkları" };

/** A note with something in every section the scope chips govern. */
function answeredDraft() {
  let state = emptyNoteState();
  for (const answer of [
    { questionId: "complaint", values: ["pain"] },
    { questionId: "duration", values: ["days"] },
    { questionId: "extra", values: ["Merdiven çıkarken artıyor."] },
  ]) {
    state = noteReducer(state, { type: "answer", ...answer });
  }
  return state;
}

/* ------------------------------------------------------------------ */
/* §1 — section-level scope UI (ALREADY DELIVERED, INT-179)            */
/* ------------------------------------------------------------------ */

describe("§1 section-level scope UI — delivered by INT-179, pinned here", () => {
  it("every note section carries its own scope switch, named with the section", () => {
    // The chip is a switch with a state, and its accessible name is composed
    // through lib/a11y/labels so three chips are distinguishable in the rotor.
    expect(REVIEW_CODE).toContain('accessibilityRole="switch"');
    expect(REVIEW_CODE).toContain("accessibilityState={{ checked: shared, disabled: sent }}");
    expect(REVIEW_CODE).toContain("withContext(");
    expect(REVIEW_CODE).toContain('t("review.shared")');
    expect(REVIEW_CODE).toContain('t("review.notShared")');
    // One chip per section, driven by the section list rather than a
    // hand-kept set — a new note section arrives with its own scope control.
    expect(REVIEW_CODE).toContain("sections.map(");
    expect(REVIEW_CODE).toContain("note.scopes[section.id] !== false");
  });

  it("scope is per SECTION id, and default-on with a visible label", () => {
    const state = noteReducer(answeredDraft(), {
      type: "scope",
      sectionId: "hpi",
      shared: false,
    });
    // absent means shared: there is no representable pre-tick to undo
    expect(state.scopes.chief_complaint).toBeUndefined();
    expect(state.scopes.hpi).toBe(false);
  });

  it("a scope-off section leaves what is sent, and nothing else does", () => {
    const state = noteReducer(answeredDraft(), {
      type: "scope",
      sectionId: "hpi",
      shared: false,
    });
    const ids = sentSections(state, ayse).map((s) => s.id);
    expect(ids).not.toContain("hpi");
    expect(ids).toContain("chief_complaint");
  });
});

/* ------------------------------------------------------------------ */
/* §2 — consent summary (what · with whom · until when)                */
/* ------------------------------------------------------------------ */

describe("§2 consent summary — 02 §5.4 'what is shared, with whom, until when'", () => {
  it("names exactly the sections that are scoped ON, in note order", () => {
    const state = noteReducer(answeredDraft(), {
      type: "scope",
      sectionId: "hpi",
      shared: false,
    });
    const summary = shareSummary(state, ayse, VISIT);
    const expected = sentSections(state, ayse).map((s) => s.titleKey);
    expect(summary.sections).toEqual(expected);
    expect(summary.sections).not.toContain("review.section.hpi");
  });

  it("says WHO, from the visit the patient already sees", () => {
    const summary = shareSummary(answeredDraft(), ayse, VISIT);
    expect(summary.recipient).toEqual(VISIT);
  });

  it("a visit with no recipient yields null rather than an invented one", () => {
    expect(shareSummary(answeredDraft(), ayse, null).recipient).toBeNull();
  });

  it("scoping every section off is a real state the summary can express", () => {
    let state = answeredDraft();
    for (const id of ["chief_complaint", "hpi", "medications", "allergies"]) {
      state = noteReducer(state, { type: "scope", sectionId: id, shared: false });
    }
    expect(shareSummary(state, ayse, VISIT).sections).toEqual([]);
  });

  it("the expiry is ANCHORED to the appointment, never computed from now", () => {
    // 02 §2: "Doctor Link expiry is pinned to visit_datetime + 72 h, never
    // issue_time + 72 h. A note prepared five days early currently expires
    // before the clinician opens it." The app therefore states the anchor and
    // computes no timestamp of its own — the clock belongs to the issuer.
    expect(SHARE_EXPIRY_ANCHOR).toBe("visit_datetime");
    const summary = shareSummary(answeredDraft(), ayse, VISIT);
    expect(summary.expiryAnchor).toBe(SHARE_EXPIRY_ANCHOR);
    expect(Object.keys(summary).sort()).toEqual(["expiryAnchor", "recipient", "sections"]);
  });

  it("the share module reaches no clock at all", () => {
    const source = code(read(MOBILE, "src", "lib", "intake", "share.ts"));
    expect(source).not.toMatch(/\bDate\b|Date\.now|getTime\(|setHours|\+\s*72/);
  });

  it("the review screen renders the summary from those three parts", () => {
    expect(REVIEW).toContain("shareSummary(");
    for (const key of [
      "review.consent.title",
      "review.consent.sections",
      "review.consent.nothing",
      "review.consent.recipient",
      "review.consent.until",
      "review.consent.untilValue",
    ] as MessageKey[]) {
      expect(REVIEW, key).toContain(`t("${key}")`);
      expect(tr[key]?.length ?? 0, key).toBeGreaterThan(0);
      expect(en[key]?.length ?? 0, key).toBeGreaterThan(0);
    }
  });
});

/* ------------------------------------------------------------------ */
/* §3 — send (ALREADY DELIVERED, INT-179)                              */
/* ------------------------------------------------------------------ */

describe("§3 send — delivered by INT-179, pinned here", () => {
  it("flips the 02 §5.1 ladder draft → sent", () => {
    const state = noteReducer(answeredDraft(), { type: "send" });
    expect(state.status).toBe("sent");
  });

  it("a sent note is frozen: the scope chips are disabled, not hidden", () => {
    expect(REVIEW).toContain("disabled={sent}");
  });
});

/* ------------------------------------------------------------------ */
/* §4 — status timeline on the review surface, after send              */
/* ------------------------------------------------------------------ */

describe("§4 status timeline — 02 §5.4 'after send: status timeline'", () => {
  it("the review screen shows the ladder itself once the note is sent", () => {
    expect(REVIEW).toContain("StatusLadder");
    expect(REVIEW).toContain("effectiveStatus(");
  });

  it("send lands the patient on that timeline instead of navigating away", () => {
    // Before INT-137 the send handler did router.replace() to the visit
    // detail, so 02 §5.4's after-send surface — timeline, then CSAT — was
    // never shown at all. The screen still pushes for edit and resume, so the
    // property is about the send handler and about replace(), not about the
    // router being absent.
    expect(REVIEW_CODE).toContain('updateNote(visitId, { type: "send" })');
    expect(REVIEW_CODE).not.toContain("router.replace");
    const ladderAt = REVIEW_CODE.indexOf("<StatusLadder");
    const ctaAt = REVIEW_CODE.indexOf('t("review.send")');
    expect(ladderAt).toBeGreaterThan(0);
    expect(ctaAt).toBeGreaterThan(ladderAt);
  });
});

/* ------------------------------------------------------------------ */
/* §5 — one-tap CSAT with reason chips (KVKK-5)                        */
/* ------------------------------------------------------------------ */

describe("§5 CSAT — the reason set is the landed csat.v1 enum, not a new one", () => {
  it("mirrors packages/clinical-schemas CsatReason exactly", () => {
    const models = read(REPO, "packages", "clinical-schemas", "src", "generated", "models.ts");
    const declared = /export type CsatReason = ([^;]+);/.exec(models);
    expect(declared, "CsatReason is not declared the way this test reads it").not.toBeNull();
    const ids = [...declared![1].matchAll(/"([a-z_]+)"/g)].map((m) => m[1]);
    expect(ids.length).toBe(5);
    expect(CSAT_REASONS.map((r) => r.id)).toEqual(ids);
  });

  it("every reason chip and score is a real tr/en catalogue string", () => {
    for (const entry of [...CSAT_REASONS, ...CSAT_SCORES]) {
      expect(t(entry.labelKey).length, entry.labelKey).toBeGreaterThan(0);
      expect(en[entry.labelKey].length, entry.labelKey).toBeGreaterThan(0);
    }
  });

  it("the scale is 1–5, as csat.v1 constrains it", () => {
    expect(CSAT_SCORES.map((s) => s.score)).toEqual([1, 2, 3, 4, 5]);
  });

  it("one tap records the score; the reason is a second, optional tap", () => {
    let state = emptyCsat();
    expect(state).toEqual({ score: null, reason: null });
    state = csatReducer(state, { type: "score", score: 4 });
    expect(state.score).toBe(4);
    state = csatReducer(state, { type: "reason", reason: "helpful" });
    expect(state.reason).toBe("helpful");
  });

  it("a score alone is not a submittable csat.v1 — the schema requires a reason", () => {
    // Finding, recorded rather than papered over: 02 §5.4 calls this
    // "one-tap", and INT-240's landed csat.v1 makes `reason` required. The
    // one tap is honoured in the UI; the event is not formed until both
    // parts exist, because inventing a reason would be inventing data.
    const scored = csatReducer(emptyCsat(), { type: "score", score: 5 });
    expect(csatResponse(scored)).toBeNull();
    const full = csatReducer(scored, { type: "reason", reason: "felt_heard" });
    expect(csatResponse(full)).toEqual({ score: 5, reason: "felt_heard" });
  });
});

describe("§5 CSAT — consent (files/06 §2 `satisfaction`) gates collection, closed", () => {
  const withSatisfactionText = (): LedgerState =>
    applyTexts(freshLedger(), {
      satisfaction: {
        status: "loaded",
        text: { version: "v1", textHash: "a".repeat(64), body: "Deneme metni — yalnızca test." },
      },
    });

  it("collects nothing while the purpose is not granted", () => {
    expect(csatCollectable(freshLedger())).toBe(false);
    expect(csatCollectable(withSatisfactionText())).toBe(false);
  });

  it("collects once the patient grants it against a loaded text", () => {
    const granted = grant(withSatisfactionText(), "satisfaction", "2026-08-31T09:00:00Z").state;
    expect(csatCollectable(granted)).toBe(true);
  });

  it("no other purpose opens it — satisfaction is not bundled with anything", () => {
    let ledger = applyTexts(freshLedger(), {
      voice: {
        status: "loaded",
        text: { version: "v1", textHash: "b".repeat(64), body: "Deneme metni — yalnızca test." },
      },
    });
    ledger = grant(ledger, "voice", "2026-08-31T09:00:00Z").state;
    expect(csatCollectable(ledger)).toBe(false);
  });

  it("the prompt itself asks the ledger, so an ungated render is impossible", () => {
    expect(CSAT_PROMPT).toContain("csatCollectable(");
    expect(CSAT_PROMPT).toContain("useConsentLedger()");
  });

  it("the prompt is the 02 §5.4 question and the five reason chips", () => {
    expect(CSAT_PROMPT).toContain('t("csat.title")');
    expect(CSAT_PROMPT).toContain("CSAT_REASONS");
    expect(CSAT_PROMPT).toContain("CSAT_SCORES");
  });

  it("no CSAT figure is rendered anywhere (invariant 20)", () => {
    // The score is collected; it is never shown back as a number, a rate or
    // an average in patient copy.
    for (const key of Object.keys(tr) as MessageKey[]) {
      if (key.startsWith("csat.")) {
        expect(tr[key], key).not.toMatch(/%|ortalama|puan ortalaması/i);
      }
    }
  });
});

/* ------------------------------------------------------------------ */
/* §6 — "never blocks send" is a SAFETY property                       */
/* ------------------------------------------------------------------ */

describe("§6 never blocks send — a newly added gate must not be able to break it", () => {
  it("every scope refused, and the note still sends", () => {
    let state = answeredDraft();
    for (const id of ["chief_complaint", "hpi", "medications", "allergies", "device_health"]) {
      state = noteReducer(state, { type: "scope", sectionId: id, shared: false });
    }
    expect(noteReducer(state, { type: "send" }).status).toBe("sent");
  });

  it("CSAT refused, skipped or half-answered, and the note still sends", () => {
    // Every CSAT state a patient can be in — untouched, score only, reason
    // only, both — and the note reducer's send is the same call in each.
    // The note layer has no CSAT input to take, which is the point: there is
    // no argument through which a future gate could be threaded.
    const states = [
      emptyCsat(),
      csatReducer(emptyCsat(), { type: "score", score: 1 }),
      csatReducer(emptyCsat(), { type: "reason", reason: "too_long" }),
      csatReducer(csatReducer(emptyCsat(), { type: "score", score: 1 }), {
        type: "reason",
        reason: "too_long",
      }),
    ];
    expect(states.filter((s) => csatResponse(s) === null)).toHaveLength(3);
    for (const _ of states) {
      expect(noteReducer(answeredDraft(), { type: "send" }).status).toBe("sent");
    }
    const noteSource = read(MOBILE, "src", "lib", "intake", "note.ts");
    expect(noteSource).not.toMatch(/csat|Csat|satisfaction/);
  });

  it("satisfaction consent refused, and the note still sends", () => {
    expect(csatCollectable(freshLedger())).toBe(false);
    expect(noteReducer(answeredDraft(), { type: "send" }).status).toBe("sent");
  });

  it("a partial or empty note still sends — sending is the patient's call", () => {
    expect(noteReducer(emptyNoteState(), { type: "send" }).status).toBe("sent");
    const checkpointed = noteReducer(answeredDraft(), { type: "checkpoint" });
    expect(noteReducer(checkpointed, { type: "send" }).status).toBe("sent");
  });

  it("the reducer's send case takes no condition at all", () => {
    // The place a future gate would most naturally be added, pinned at the
    // shape rather than at the behaviour — a guard inserted here fails this
    // before it can fail a patient.
    const noteSource = read(MOBILE, "src", "lib", "intake", "note.ts");
    expect(noteSource).toMatch(/case "send":\s*\n\s*return \{ \.\.\.state, status: "sent" \};/);
  });

  it("the send handler does exactly one thing", () => {
    // The other place: inside onPress. One updateNote call, one visitId
    // guard, no early return, no await, no branch on anything optional.
    const cta = /<PrimaryButton[\s\S]*?\/>/.exec(REVIEW_CODE);
    expect(cta, "the send CTA is not shaped the way this test reads it").not.toBeNull();
    const body = cta![0];
    expect(body.match(/updateNote\(/g)).toHaveLength(1);
    expect(body.match(/\bif\s*\(/g)).toHaveLength(1);
    expect(body).toContain("if (visitId)");
    expect(body).not.toMatch(/\breturn\b|\bthrow\b|&&|\|\||await|Alert/);
  });

  it("the send CTA is never disabled and never conditioned", () => {
    const cta = /<PrimaryButton\s+label=\{t\("review\.send"\)\}[\s\S]*?\/>/.exec(REVIEW);
    expect(cta, "the send CTA is not shaped the way this test reads it").not.toBeNull();
    expect(cta![0]).not.toContain("disabled");
    expect(cta![0]).not.toMatch(/csat|consent|Csat|Consent/);
  });

  it("send reaches no network, so an offline patient can always send", () => {
    // The one honest way to prove "an erroring optional surface cannot block
    // the send" in a lane with no renderer: the send path has no await, no
    // fetch and no promise to reject.
    expect(REVIEW_CODE).not.toMatch(/authedFetch|fetch\(|await |async /);
    expect(CSAT_PROMPT_CODE).not.toMatch(/authedFetch|fetch\(|await |async /);
  });

  it("the CSAT surface is rendered only after the note is already sent", () => {
    const at = REVIEW_CODE.indexOf("<CsatPrompt");
    expect(at).toBeGreaterThan(0);
    // It sits inside the `sent` branch: the send has happened before the
    // patient can refuse, skip or mis-answer anything in it.
    expect(REVIEW_CODE.slice(0, at)).toContain('const sent = note.status === "sent"');
    // And it cannot reach back: nothing in it touches the note layer at all.
    expect(CSAT_PROMPT_CODE).not.toMatch(/intake\/note|updateNote|noteReducer|sentSections/);
  });
});

/* ------------------------------------------------------------------ */
/* §7 — Doctor Link QR: the decision, as a negative control            */
/* ------------------------------------------------------------------ */

describe("§7 Doctor Link QR — not built, and the reason is enforced", () => {
  it("no share URL, token or QR payload is constructed on the device", () => {
    // INT-150 ("Doctor Link: 128-bit token + OTP + expiry + view limit +
    // revoke + watermark + access log") is `status: todo` and no /share
    // route exists in services/api. A QR needs an opaque, short-lived
    // reference the clinician redeems against the API under their own auth,
    // with the consent scope checked AT REDEMPTION. Nothing in files/
    // specifies that redemption flow, so no link format is invented here —
    // and this control is what stops one being added quietly.
    for (const source of [REVIEW_CODE, CSAT_PROMPT_CODE]) {
      expect(source).not.toMatch(/https?:\/\/|intake:\/\/|qrcode|QRCode|\btoken\b/i);
    }
  });

  it("the note's own content never leaves the device through this screen", () => {
    expect(REVIEW_CODE).not.toMatch(/encodeURIComponent|JSON\.stringify|base64|btoa/);
  });
});

/* ------------------------------------------------------------------ */
/* §8 — invariant 4: the UI is not the only thing enforcing scope      */
/* ------------------------------------------------------------------ */

describe("§8 the scope the UI shows is the scope the ledger enforces", () => {
  it("the device preview and the server share ledger key on the same ids", () => {
    // INT-197's SectionId is the share-scope vocabulary; buildNote's ids are
    // the device preview's. A section the ledger cannot express is a finding
    // reported in docs/evidence/INT-137.md, never a schema widened from here.
    const schemas = read(REPO, "services", "api", "src", "intake_api", "schemas.py");
    const declared = /SectionId = Literal\[([^\]]+)\]/.exec(schemas);
    expect(declared, "SectionId is not declared the way this test reads it").not.toBeNull();
    const ledgerIds = new Set([...declared![1].matchAll(/"([a-z_]+)"/g)].map((m) => m[1]));
    const previewIds = buildNote(answeredDraft().answers, ayse).map((s) => s.id);
    expect(previewIds.filter((id) => ledgerIds.has(id)).length).toBeGreaterThan(0);
    // Recorded, not asserted away: the preview builds sections the ledger has
    // no literal for. They are listed in the evidence as a spec question.
    const unexpressible = previewIds.filter((id) => !ledgerIds.has(id));
    expect(unexpressible).toEqual(["allergies"]);
  });
});
