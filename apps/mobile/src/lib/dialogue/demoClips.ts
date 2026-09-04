/**
 * The exact set of scripted strings the spoken previsit says, enumerated once
 * so the offline ElevenLabs clip generator and the runtime prebaked-clip
 * resolver read from ONE list (INT-demo dev clip lane).
 *
 * What is in it, and why exactly this: `useDialogueSession` pre-warms and
 * speaks two kinds of scripted clip — the question clip for every spoken
 * question (`questionSpeechTr`) and, for a `text` question, the generic
 * confirm line (`confirmSpeechTr(q, [])`, which names no patient words). Both
 * are composed here from the SAME functions the session uses, so a generated
 * clip is byte-for-byte the string the app will look up (invariant 10). The
 * union is taken over `spokenPack(allQuestions)` — every question that can be
 * spoken in any department pack plus the universal history and base-layer
 * blocks — so whichever department the demo visit runs, its questions have a
 * bundled clip and the previsit speaks offline end to end.
 *
 * What is NOT in it: the OPTION confirm clips (`confirm` clips keyed on the
 * patient's chosen option ids). Those depend on the answer, are combinatorial,
 * and are synthesised on demand by the live dev TTS lane; a demo with no live
 * lane simply plays them silently-degraded exactly as it does today. The demo
 * openers (`dialogue.entryBody` / `dialogue.openInvite`) are DISPLAYED on the
 * entry gate, never voiced as a clip, so they are not synthesised either.
 *
 * Invariant 22 mirror: every string is run through `assertSpeakableTr` here, so
 * a numeral can never reach the manifest and therefore never reach ElevenLabs —
 * the enumerator refuses before the generator ever dials the vendor.
 */
import { allQuestions, spokenPack } from "../intake/questions";
import { clipTextHash } from "./clipHash";
import { confirmSpeechTr, questionSpeechTr } from "./speech";
import { assertSpeakableTr, clipName } from "./tts";

export interface DemoClipScript {
  /** Session cache key the store looks up — `q_<id>.wav` / `c_<id>.wav`. */
  readonly name: string;
  /** The verbatim Turkish spoken for this clip. */
  readonly text: string;
  /** sha256(text) — the prebaked cache key and the clip's filename stem. */
  readonly hash: string;
  readonly kind: "question" | "confirm";
  readonly questionId: string;
}

/**
 * Every scripted clip the spoken previsit can play, deduplicated by cache
 * name (a question id is unique across packs, so its clip is authored once).
 * Deterministic and pure: the generator and the drift guard both call it.
 */
export function demoClipScripts(): readonly DemoClipScript[] {
  const rows: DemoClipScript[] = [];
  const seen = new Set<string>();
  const add = (kind: "question" | "confirm", questionId: string, name: string, text: string) => {
    if (seen.has(name)) {
      return;
    }
    seen.add(name);
    assertSpeakableTr(text); // invariant 22 — no numeral ever enters the manifest
    rows.push({ name, text, hash: clipTextHash(text), kind, questionId });
  };
  for (const question of spokenPack(allQuestions)) {
    add("question", question.id, clipName("question", question.id), questionSpeechTr(question));
    if (question.kind === "text") {
      add("confirm", question.id, clipName("confirm", question.id), confirmSpeechTr(question, []));
    }
  }
  return rows;
}

/**
 * The manifest the offline generator consumes: the voice/model it must synth
 * with, and every `{ name, text, hash }` row. Voice and model are surfaced
 * here as data so the generator and this catalogue cannot disagree about which
 * voice the bundled clips are keyed for.
 */
export interface DemoClipManifest {
  readonly voiceId: string;
  readonly modelId: string;
  readonly count: number;
  readonly totalChars: number;
  readonly rows: readonly DemoClipScript[];
}

export function demoClipManifest(voiceId: string, modelId: string): DemoClipManifest {
  const rows = demoClipScripts();
  return {
    voiceId,
    modelId,
    count: rows.length,
    totalChars: rows.reduce((n, r) => n + r.text.length, 0),
    rows,
  };
}
