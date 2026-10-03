/**
 * INT-446 — a red-flag answer reaches the RED screen, end to end, on both
 * lanes; a near miss does not (CLAUDE.md invariants 1, 10, 21).
 *
 * The chain under test is the app's own, module for module: the dialogue
 * reducer (spoken utterance or typed composer) or the typed StepFlow commit →
 * the session note's `answer` action (the one place every bound answer lands)
 * → the rules-engine hop → the decoder → the RED store → the RED screen
 * model RedLayer renders. The engine's side is the recorded exchange file
 * tests/fixtures/triage_hop/exchanges.json, which tests/api/test_triage_hop.py
 * pins to the real `/v1/triage/evaluate` route over the signed SENTETİK set —
 * so what the device is tested against is what the engine really answers,
 * and the device holds no rule of its own.
 *
 * What a node test cannot show — the layer's pixels — is the simulator
 * screenshot recorded in docs/evidence/INT-446.md.
 */
import { readFileSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { isDeepStrictEqual } from "node:util";
import { describe, expect, it } from "vitest";

import {
  dialogueStreamReducer,
  initialDialogueStreamState,
  type DialogueStreamAction,
  type DialogueStreamState,
} from "../src/lib/dialogue/stream";
import { emptyNoteState, noteReducer, type NoteState } from "../src/lib/intake/note";
import type { IntakeQuestion } from "../src/lib/intake/questions";
import { CATALOG_PATH, type HopTransport } from "../src/lib/red/hop";
import { deriveRedLocation } from "../src/lib/red/location";
import { createRedHop, createRedStore, redScreen, type RedStore } from "../src/lib/red/store";
import { code } from "./motionSource";
import { specifiers } from "./redSurface";

const MOBILE = join(__dirname, "..");
const FIXTURES = join(MOBILE, "..", "..", "tests", "fixtures", "triage_hop");
const CATALOG_BYTES = new Uint8Array(readFileSync(join(FIXTURES, "red_catalog.json")));
const EXCHANGES = (
  JSON.parse(readFileSync(join(FIXTURES, "exchanges.json"), "utf8")) as {
    exchanges: { name: string; request: unknown; response: unknown }[];
  }
).exchanges;

/** The recorded engine: a request it has a recording for gets that answer. */
function recordedEngine(calls: string[]): HopTransport {
  return async (path, body) => {
    if (path === CATALOG_PATH) {
      calls.push("catalog");
      return { status: 200, bytes: CATALOG_BYTES };
    }
    const request: unknown = JSON.parse(body ?? "null");
    const hit = EXCHANGES.find((e) => isDeepStrictEqual(e.request, request));
    calls.push(hit?.name ?? "unrecorded");
    if (hit === undefined) {
      return { status: 404, bytes: new Uint8Array() };
    }
    return { status: 200, bytes: new TextEncoder().encode(JSON.stringify(hit.response)) };
  };
}

// The SENTETİK set's two slots, asked as open questions — exactly the shape a
// compiled pack's slot takes in the dialogue and the StepFlow.
const PACK: IntakeQuestion[] = [
  { id: "ziyaret.basvuru_nedeni", kind: "text", titleKey: "intake.q.extra" },
  { id: "sure_dakika", kind: "text", titleKey: "intake.q.extra" },
];
const REFERENCE = new Date("2026-08-29T07:00:00.000Z");
const TODAY = "2026-08-29";

interface Lane {
  note: NoteState;
  dialogue: DialogueStreamState;
}

function dispatch(lane: Lane, action: DialogueStreamAction): void {
  lane.dialogue = dialogueStreamReducer(PACK, lane.dialogue, action);
}

/**
 * What DialogueIntake does when the patient confirms: the note gets the
 * candidate's values, then the reducer is told. Whichever surface holds the
 * suggestion — the live confirm card or a panel row — the values are the same.
 */
function confirm(lane: Lane, questionId: string): void {
  if (lane.dialogue.turn.phase === "speaking" && lane.dialogue.turn.intent === "confirm") {
    dispatch(lane, { type: "speech_done" }); // the confirm line is read back first
  }
  const { turn } = lane.dialogue;
  if (turn.phase === "confirming" && PACK[turn.step]?.id === questionId) {
    const values = [...turn.candidate.values];
    lane.note = noteReducer(lane.note, { type: "answer", questionId, values });
    dispatch(lane, { type: "confirm", values });
    return;
  }
  const pending = lane.dialogue.pending[questionId];
  expect(pending, `a suggestion for ${questionId}`).toBeDefined();
  lane.note = noteReducer(lane.note, { type: "answer", questionId, values: [...pending.values] });
  dispatch(lane, { type: "confirm_pending", questionId });
}

/** One spoken answer: the mic closes, ASR returns, the extract settles. */
function speak(lane: Lane, workId: number, questionId: string, transcript: string): void {
  if (lane.dialogue.turn.phase === "speaking") {
    dispatch(lane, { type: "speech_done" });
  }
  expect(lane.dialogue.turn.phase).toBe("listening");
  dispatch(lane, { type: "utterance", workId });
  dispatch(lane, { type: "transcript_ready", workId, text: transcript });
  // A text step's answer is the transcript verbatim (useDialogueSession runExtract).
  dispatch(lane, {
    type: "extract_settled",
    workId,
    candidates: { [questionId]: { values: [transcript], quote: transcript } },
  });
  confirm(lane, questionId);
}

/** One typed composer message: the same conversation minus the ASR hop. */
function type(lane: Lane, workId: number, questionId: string, text: string): void {
  dispatch(lane, { type: "typed", workId, text });
  dispatch(lane, {
    type: "extract_settled",
    workId,
    candidates: { [questionId]: { values: [text], quote: text } },
  });
  confirm(lane, questionId);
}

function fresh(mode: "hizli" | "detayli"): Lane {
  const note = noteReducer(emptyNoteState(), { type: "mode", mode });
  return { note, dialogue: initialDialogueStreamState(PACK) };
}

function harness() {
  const calls: string[] = [];
  const store = createRedStore();
  let clock = 0;
  const hop = createRedHop({
    transport: recordedEngine(calls),
    store,
    now: () => clock,
    clock: () => REFERENCE,
  });
  return {
    calls,
    store,
    tick: (ms: number) => {
      clock += ms;
    },
    /** What RedLayer's effect does on every note change. */
    commit: async (lane: Lane, visitDate: string) => {
      const location = deriveRedLocation({
        mode: lane.note.mode,
        visitDate,
        today: TODAY,
        kiosk: false,
      });
      return hop.onAnswers("visit-e2e", lane.note.answers, location);
    },
  };
}

const LATER = "2026-09-02"; // Hızlı + a later visit → REMOTE

function screenOf(store: RedStore) {
  return redScreen(store.getSnapshot());
}

describe("INT-446 — a red-flag answer reaches the RED screen on the voice lane", () => {
  it("spoken answers → note → engine → RED root layer, verbatim, with 112 under REMOTE", async () => {
    const h = harness();
    const lane = fresh("hizli");
    speak(lane, 1, "ziyaret.basvuru_nedeni", "sentetik_yasamsal");
    // One bound answer, undated: the engine's near miss — no RED yet.
    expect(await h.commit(lane, LATER)).toEqual({ kind: "level", level: "GREEN" });
    expect(screenOf(h.store)).toEqual({ kind: "none" });
    speak(lane, 2, "sure_dakika", "2026-08-29");
    const started = performance.now();
    expect((await h.commit(lane, LATER)).kind).toBe("red");
    const answerToRedMs = performance.now() - started;
    const screen = screenOf(h.store);
    expect(screen).toMatchObject({
      kind: "act",
      mode: "rootLayer",
      register: "ALERT",
      location: "REMOTE",
      actionTr: "Hemen yardım isteyin.",
      doNotsTr: ["Yalnız kalmayın."],
      whyTr: "Bu bir sentetik test metnidir.",
      call112: true,
    });
    // The catalog was on the device before the first verdict, once.
    expect(h.calls).toEqual(["catalog", "near_miss_undated", "red_remote"]);
    expect(answerToRedMs).toBeLessThan(300);
    console.info(
      `INT-446 voice lane: answer bound → RED screen model ${answerToRedMs.toFixed(2)} ms`,
    );
  });

  it("near miss: one differing value goes through the engine and shows nothing", async () => {
    const h = harness();
    const lane = fresh("hizli");
    speak(lane, 1, "ziyaret.basvuru_nedeni", "sentetik_yasamsal_degil");
    speak(lane, 2, "sure_dakika", "2026-08-29");
    expect(await h.commit(lane, LATER)).toEqual({ kind: "level", level: "GREEN" });
    expect(h.calls).toEqual(["catalog", "near_miss_value"]);
    expect(h.store.getSnapshot()).toBeNull();
  });
});

describe("INT-446 — a red-flag answer reaches the RED screen on the typed lane", () => {
  it("typed composer: Detaylı → UNKNOWN → the one question, then ON_SITE with no 112", async () => {
    const h = harness();
    const lane = fresh("detayli");
    dispatch(lane, { type: "speech_done" });
    type(lane, 1, "ziyaret.basvuru_nedeni", "sentetik_yasamsal");
    await h.commit(lane, LATER);
    if (lane.dialogue.turn.phase === "speaking") {
      dispatch(lane, { type: "speech_done" });
    }
    type(lane, 2, "sure_dakika", "2026-08-29");
    expect((await h.commit(lane, LATER)).kind).toBe("red");
    expect(screenOf(h.store)).toMatchObject({
      kind: "ask",
      mode: "rootLayer",
      askTr: "Şu anda hastanede misiniz?",
    });
    h.store.answerLocation("inHospital");
    const screen = screenOf(h.store);
    expect(screen).toMatchObject({
      kind: "act",
      location: "ON_SITE",
      actionTr: "Görevlilere haber verin.",
      call112: false, // ON_SITE: absent
    });
  });

  it("typed StepFlow: each tapped/typed commit is one note answer, and RED follows the second", async () => {
    const h = harness();
    let lane = fresh("hizli");
    const commit = (questionId: string, value: string) => {
      lane = {
        ...lane,
        note: noteReducer(lane.note, { type: "answer", questionId, values: [value], words: value }),
      };
    };
    commit("ziyaret.basvuru_nedeni", "sentetik_yasamsal");
    expect((await h.commit(lane, LATER)).kind).toBe("level");
    commit("sure_dakika", "2026-08-29");
    h.tick(0);
    expect((await h.commit(lane, LATER)).kind).toBe("red");
    expect(h.store.getSnapshot()?.elapsedMs).not.toBeNull();
    expect(screenOf(h.store)).toMatchObject({ kind: "act", location: "REMOTE", call112: true });
  });

  it("near miss on the typed lane: the undated answer alone never fires", async () => {
    const h = harness();
    const lane = fresh("hizli");
    lane.note = noteReducer(lane.note, {
      type: "answer",
      questionId: "ziyaret.basvuru_nedeni",
      values: ["sentetik_yasamsal"],
    });
    expect(await h.commit(lane, LATER)).toEqual({ kind: "level", level: "GREEN" });
    // Unchanged answers are not re-sent: one hop per bound-answer change.
    expect(await h.commit(lane, LATER)).toEqual({ kind: "unevaluated" });
    expect(h.calls).toEqual(["catalog", "near_miss_undated"]);
    expect(h.store.getSnapshot()).toBeNull();
  });

  it("no catalog, no verdict: the answers are not sent before the words are on the device", async () => {
    const store = createRedStore();
    const sent: string[] = [];
    const hop = createRedHop({
      transport: async (path) => {
        sent.push(path);
        return { status: 503, bytes: new Uint8Array() };
      },
      store,
      now: () => 0,
      clock: () => REFERENCE,
    });
    const lane = fresh("hizli");
    lane.note = noteReducer(lane.note, {
      type: "answer",
      questionId: "sure_dakika",
      values: ["x"],
    });
    expect(await hop.onAnswers("v", lane.note.answers, "REMOTE")).toEqual({ kind: "unevaluated" });
    expect(sent).toEqual([CATALOG_PATH]);
    expect(store.getSnapshot()).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// The RED path touches no media transport, and the layer is mounted at root.
// ---------------------------------------------------------------------------

const SRC = join(MOBILE, "src");

function resolveLocal(from: string, spec: string): string | null {
  const base = spec.startsWith("@/")
    ? join(SRC, spec.slice(2))
    : spec.startsWith(".")
      ? resolve(dirname(from), spec)
      : null;
  if (base === null) {
    return null;
  }
  for (const candidate of [`${base}.ts`, `${base}.tsx`, join(base, "index.ts")]) {
    if (existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
}

/** Every package a file reaches through local imports, transitively. */
function reachedPackages(entry: string): Set<string> {
  const seen = new Set<string>();
  const packages = new Set<string>();
  const queue = [entry];
  while (queue.length > 0) {
    const current = queue.pop() as string;
    if (seen.has(current)) {
      continue;
    }
    seen.add(current);
    for (const spec of specifiers(readFileSync(current, "utf8"))) {
      const local = resolveLocal(current, spec);
      if (local !== null) {
        queue.push(local);
      } else if (!spec.startsWith(".") && !spec.startsWith("@/")) {
        packages.add(spec);
      }
    }
  }
  return packages;
}

const MEDIA = /expo-audio|expo-av|livekit|webrtc|expo-haptics|expo-speech/;

describe("INT-453 — a RED with a missing script shows the generic RED on the device", () => {
  /** The recorded engine, with a pre-positioned catalog that lacks one script (pack drift). */
  function driftedEngine(missing: string, calls: string[]): HopTransport {
    const engine = recordedEngine(calls);
    return async (path, body) => {
      if (path !== CATALOG_PATH) {
        return engine(path, body);
      }
      calls.push("catalog");
      const raw = JSON.parse(new TextDecoder().decode(CATALOG_BYTES)) as {
        scripts: Record<string, unknown>;
        questions: Record<string, unknown>;
      };
      delete raw.scripts[missing];
      delete raw.questions[missing];
      return { status: 200, bytes: new TextEncoder().encode(JSON.stringify(raw)) };
    };
  }

  it.each([
    ["REMOTE", "hizli", "2026-09-02"],
    ["UNKNOWN", "detayli", "2026-09-02"],
  ] as const)(
    "answer → engine RED (%s) → script missing → the pre-positioned generic RED, ALERT root layer",
    async (location, mode, visitDate) => {
      const calls: string[] = [];
      const store = createRedStore();
      const hop = createRedHop({
        transport: driftedEngine(`rf.sentetik_yasamsal.${location.toLowerCase()}`, calls),
        store,
        now: () => 0,
        clock: () => REFERENCE,
      });
      let lane = fresh(mode);
      lane = {
        ...lane,
        note: noteReducer(
          noteReducer(lane.note, {
            type: "answer",
            questionId: "ziyaret.basvuru_nedeni",
            values: ["sentetik_yasamsal"],
          }),
          { type: "answer", questionId: "sure_dakika", values: ["2026-08-29"] },
        ),
      };
      const derived = deriveRedLocation({
        mode: lane.note.mode,
        visitDate,
        today: TODAY,
        kiosk: false,
      });
      expect(derived).toBe(location);
      expect((await hop.onAnswers("visit-drift", lane.note.answers, derived)).kind).toBe("red");
      // The served catalog carries the generic RED (the INT-453 serve
      // precondition), so its own words show: verbatim, never invented.
      if (location === "UNKNOWN") {
        expect(redScreen(store.getSnapshot())).toMatchObject({
          kind: "ask",
          mode: "rootLayer",
          register: "ALERT",
          askTr: "Şu anda hastanede misiniz?",
        });
        store.answerLocation("notInHospital");
      }
      expect(redScreen(store.getSnapshot())).toMatchObject({
        kind: "act",
        mode: "rootLayer",
        register: "ALERT",
        location: "REMOTE",
        // INT-465: the active CD-24 copy, as the route serves it (rendered).
        actionTr: "Hemen 112 Acil Çağrı Merkezi'ni arayın.",
        call112: true,
      });
      // Near miss: with the script present the rule's own words show, not the generic.
      const own = createRedStore();
      await createRedHop({
        transport: recordedEngine([]),
        store: own,
        now: () => 0,
        clock: () => REFERENCE,
      }).onAnswers("visit-own", lane.note.answers, derived);
      expect(redScreen(own.getSnapshot()).kind).toBe(location === "UNKNOWN" ? "ask" : "act");
      expect(JSON.stringify(redScreen(own.getSnapshot()))).not.toContain('"actionTr":""');
    },
  );

  it("RedLayer renders the RED's words always, and the 112 control only where allowed", () => {
    const layer = code(readFileSync(join(SRC, "components/RedLayer.tsx"), "utf8"));
    // INT-465: never wordless (CD-24); no branch hides an empty action line.
    expect(layer).not.toMatch(/actionTr\.length/);
    expect(layer).toMatch(/\{screen\.call112 \?/);
  });

  it("an unanswered location question starts the no-answer clock (CD-24), owned by no component", () => {
    const layer = code(readFileSync(join(SRC, "components/RedLayer.tsx"), "utf8"));
    expect(layer).toMatch(
      /useEffect\(\(\)\s*=>\s*\(asking \? startNoAnswerClock\(redStore\) : undefined\),\s*\[asking\]\)/,
    );
    expect(layer).not.toMatch(/setTimeout|setInterval/);
  });

  it("CD-24 generic_red_stops_intake: the dialogue shows nothing that arrives after the RED", () => {
    const dialogue = code(readFileSync(join(SRC, "components/DialogueIntake.tsx"), "utf8"));
    expect(dialogue).toMatch(/dialogueShown\(state\.stream,\s*frozenAt\)\.map\(renderEntry\)/);
    expect(dialogue).not.toMatch(/\{state\.stream\.map\(renderEntry\)\}/);
    for (const phase of ["listening", "settling", "confirming"]) {
      expect(dialogue).not.toMatch(new RegExp(`\\{turn\\.phase === "${phase}" \\?`));
    }
  });
});

describe("INT-446 — the RED path", () => {
  it("decode → store → screen reaches no media, audio or haptic module", () => {
    for (const entry of ["lib/red/store.ts", "lib/red/hop.ts", "lib/red/location.ts"]) {
      const reached = [...reachedPackages(join(SRC, entry))];
      expect(
        reached.filter((p) => MEDIA.test(p)),
        entry,
      ).toEqual([]);
    }
    // Non-vacuity: the detector does see a media module where one is.
    const dialogue = reachedPackages(join(SRC, "lib/dialogue/useDialogueSession.ts"));
    expect([...dialogue].some((p) => MEDIA.test(p))).toBe(true);
  });

  it("the layer imports no media, audio, animation or haptic module, and opens no Modal", () => {
    const layer = readFileSync(join(SRC, "components/RedLayer.tsx"), "utf8");
    expect(specifiers(layer).filter((s) => MEDIA.test(s) || /reanimated/.test(s))).toEqual([]);
    expect(code(layer)).not.toMatch(/\bModal\b|\bAnimated\b|\bLayoutAnimation\b|\bHaptics\b/);
  });

  it("the root layout mounts RedLayer after the navigator container, never inside it", () => {
    const layout = code(readFileSync(join(SRC, "app/_layout.tsx"), "utf8"));
    const navigator = layout.indexOf("</KioskGate>");
    const layer = layout.indexOf("<RedLayer />");
    expect(navigator).toBeGreaterThan(-1);
    expect(layer).toBeGreaterThan(navigator);
    expect(layout.slice(layer).indexOf("</SessionProvider>")).toBeGreaterThan(0);
  });

  it("the dialogue stops for a RED the patient sees, and SILENT renders in the flow of both lanes", () => {
    const dialogue = code(readFileSync(join(SRC, "components/DialogueIntake.tsx"), "utf8"));
    expect(dialogue).toMatch(/redStopsDialogue\(red\)/);
    expect(dialogue).toMatch(/session\.leave\(\)/);
    expect(dialogue).toMatch(/<RedInFlow \/>/);
    const typed = code(readFileSync(join(SRC, "app/(tabs)/visits/[visitId]/intake.tsx"), "utf8"));
    expect(typed).toMatch(/<RedInFlow \/>/);
  });
});
