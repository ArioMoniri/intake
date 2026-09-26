/**
 * The demo clip catalogue is the contract between three things that must never
 * drift: what the session SPEAKS (`questionSpeechTr`/`confirmSpeechTr`), what
 * the offline generator SYNTHESISED (the committed manifest + the bundled
 * `<hash>.wav` files), and what the runtime LOOKS UP (`clipTextHash`). This
 * test pins all three.
 *
 * It is also the manifest emitter: run with `WRITE_DEMO_CLIP_MANIFEST=1` it
 * (re)writes `assets/dialogue-clips/manifest.json` for the generator, and the
 * coverage check still runs, reporting the strings whose wavs do not exist yet;
 * run normally it asserts the committed manifest and the bundled wavs match
 * the catalogue, so a changed question string fails here until the clips are
 * regenerated.
 */
import { existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { allQuestions, spokenPack } from "../intake/questions";
import { clipTextHash } from "./clipHash";
import { demoClipManifest, demoClipScripts } from "./demoClips";
import { DEMO_CLIP_MODEL_ID, DEMO_CLIP_VOICE_ID } from "./demoVoice";
import { confirmSpeechTr, questionSpeechTr } from "./speech";

const writing = process.env.WRITE_DEMO_CLIP_MANIFEST === "1";

const manifestPath = fileURLToPath(
  new URL("../../../assets/dialogue-clips/manifest.json", import.meta.url),
);
const clipsDir = fileURLToPath(new URL("../../../assets/dialogue-clips/", import.meta.url));

describe("demoClipScripts", () => {
  const rows = demoClipScripts();

  it("enumerates at least the shared core questions", () => {
    expect(rows.length).toBeGreaterThan(50);
    expect(rows.some((r) => r.name === "q_complaint.wav")).toBe(true);
  });

  it("carries no numeral — nothing that could reach the vendor unspoken (invariant 22)", () => {
    for (const row of rows) {
      // an independent control: a fresh Unicode-digit scan, not the enumerator's
      // own guard, so a weakened guard cannot make this pass.
      expect(/\p{N}/u.test(row.text), `${row.name}: ${row.text}`).toBe(false);
    }
  });

  it("every clip's text is the session's own composition, verbatim (invariant 10)", () => {
    const byId = new Map(spokenPack(allQuestions).map((q) => [q.id, q]));
    for (const row of rows) {
      const question = byId.get(row.questionId);
      expect(question, row.name).toBeDefined();
      const expected =
        row.kind === "question" ? questionSpeechTr(question!) : confirmSpeechTr(question!, []);
      expect(row.text, row.name).toBe(expected);
    }
  });

  it("names are unique and hashes are the content hash of the text", () => {
    const names = new Set<string>();
    for (const row of rows) {
      expect(names.has(row.name), row.name).toBe(false);
      names.add(row.name);
      expect(row.hash).toBe(clipTextHash(row.text));
    }
  });
});

describe("demo clip manifest (generator input, committed)", () => {
  const manifest = demoClipManifest(DEMO_CLIP_VOICE_ID, DEMO_CLIP_MODEL_ID);

  it(
    writing ? "writes the manifest the generator consumes" : "matches the committed manifest",
    () => {
      if (writing) {
        writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf-8");
        expect(existsSync(manifestPath)).toBe(true);
        return;
      }
      expect(existsSync(manifestPath), `${manifestPath} missing — regenerate the manifest`).toBe(
        true,
      );
      const committed = JSON.parse(readFileSync(manifestPath, "utf-8"));
      expect(committed).toEqual(manifest);
    },
  );
});

// Never skipped (invariant 17; tests/ci/test_security_gates.py). In a
// WRITE_DEMO_CLIP_MANIFEST=1 run this fails for any new string, which is the
// truth at that moment: the manifest is written, the wavs are not yet.
describe("bundled clips cover the catalogue", () => {
  it("every scripted string has a bundled <hash>.wav (coverage; regenerate if this fails)", () => {
    const present = new Set(readdirSync(clipsDir).filter((f) => f.endsWith(".wav")));
    const missing = demoClipScripts()
      .filter((row) => !present.has(`${row.hash}.wav`))
      .map((row) => row.name);
    expect(missing, `missing bundled clips: ${missing.join(", ")}`).toEqual([]);
  });
});
