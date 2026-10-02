/**
 * INT-440 — the bundled ElevenLabs clip set (ADR-028 offline clip-gen).
 *
 * The render script reads bundledClipSet.json and nothing else, so this file
 * is what keeps the vendor from ever being handed a line the app does not say:
 * the committed JSON must equal the app's own composition over the dev test
 * visits' packs. To regenerate after a catalogue change:
 *   INTAKE_WRITE_CLIP_SET=1 pnpm --filter @intake/mobile exec vitest run src/lib/dialogue/bundledClips.test.ts
 */
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { packForVisit, spokenPack } from "../intake/questions";
import {
  bundledClipAddress,
  bundledClipAddressFromFile,
  bundledClipFor,
  bundledClipSet,
  BUNDLED_CLIP_DEPARTMENTS,
  clipTextHash,
} from "./bundledClips";
import { DELIVERY_CONTEXTS } from "./deliveryContext";
import { confirmSpeechTr, questionSpeechTr } from "./speech";

const HERE = fileURLToPath(new URL(".", import.meta.url));
const JSON_PATH = join(HERE, "bundledClipSet.json");

describe("clipTextHash is protocols.dsl clip_text_hash", () => {
  it("is sha256 over the NFC text, lower-case hex", () => {
    const text = "Sizi bugün hekime getiren nedir?";
    expect(clipTextHash(text)).toBe(
      createHash("sha256").update(text.normalize("NFC"), "utf8").digest("hex"),
    );
  });

  it("maps NFD and NFC spellings of the same Turkish to one clip", () => {
    const nfc = "Şikâyetiniz ne zaman başladı?";
    expect(clipTextHash(nfc.normalize("NFD"))).toBe(clipTextHash(nfc));
  });

  it("addresses a clip by its context too — one text, two contexts, two clips", () => {
    const text = "Teşekkür ederim.";
    expect(bundledClipAddress(text, "routine")).toBe(`routine/${clipTextHash(text)}`);
    expect(bundledClipAddress(text, "acknowledgement")).not.toBe(
      bundledClipAddress(text, "routine"),
    );
  });
});

describe("bundledClipSet — exactly the lines the dev dialogue speaks", () => {
  const set = bundledClipSet();
  const composed = new Set<string>();
  for (const department of BUNDLED_CLIP_DEPARTMENTS) {
    for (const mode of ["hizli", "detayli"] as const) {
      for (const question of spokenPack(packForVisit(department, { mode }))) {
        composed.add(questionSpeechTr(question));
        composed.add(confirmSpeechTr(question, []));
        if (question.kind === "chips" || question.kind === "single") {
          for (const option of question.options) {
            composed.add(confirmSpeechTr(question, [option.id]));
          }
        }
      }
    }
  }

  it("covers every question line and its confirm lines, every test department, both modes", () => {
    const routine = new Set(set.filter((l) => l.context === "routine").map((l) => l.text_tr));
    for (const text of composed) {
      expect(routine.has(text), text).toBe(true);
    }
  });

  it("lists each (context, line) once, numeral- and markup-free, in a known context", () => {
    const seen = new Set(set.map((line) => `${line.context}\u0000${line.text_tr}`));
    expect(seen.size).toBe(set.length);
    for (const line of set) {
      expect(/\p{N}/u.test(line.text_tr), line.text_tr).toBe(false);
      expect(/[<>[\]]/u.test(line.text_tr), line.text_tr).toBe(false);
      expect(DELIVERY_CONTEXTS).toContain(line.context);
      expect(["red", "instrument"]).not.toContain(line.context);
    }
  });

  it("lists only lines the app composes — nothing else can reach the renderer", () => {
    for (const line of set.filter((l) => l.context === "routine")) {
      expect(composed.has(line.text_tr), line.text_tr).toBe(true);
    }
  });

  it("the committed bundledClipSet.json IS this set (the renderer's only input)", () => {
    const rendered = `${JSON.stringify(set, null, 2)}\n`;
    if (process.env.INTAKE_WRITE_CLIP_SET === "1") {
      writeFileSync(JSON_PATH, rendered, "utf8");
    }
    expect(readFileSync(JSON_PATH, "utf8")).toBe(rendered);
  });
});

describe("bundled clip lookup", () => {
  const text = "Sizi bugün hekime getiren nedir?";

  it("finds a clip by its line and context and misses everything else", () => {
    const assets = new Map([[bundledClipAddress(text, "routine"), 7]]);
    expect(bundledClipFor(text, "routine", assets)).toBe(7);
    expect(bundledClipFor(text, "welcome", assets)).toBeNull();
    expect(bundledClipFor("Başka bir soru?", "routine", assets)).toBeNull();
  });

  it("reads an address only from a well-formed clip file name", () => {
    const hash = clipTextHash(text);
    expect(bundledClipAddressFromFile(`./routine/${hash}.wav`)).toBe(`routine/${hash}`);
    expect(bundledClipAddressFromFile(`./${hash}.wav`)).toBeNull();
    expect(bundledClipAddressFromFile(`./shouting/${hash}.wav`)).toBeNull();
    expect(bundledClipAddressFromFile(`./routine/${hash}.mp3`)).toBeNull();
  });
});
