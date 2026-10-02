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

import { testAccounts } from "../dev/accounts";
import { packForVisit, spokenPack } from "../intake/questions";
import {
  bundledClipAddress,
  bundledClipAddressFromFile,
  bundledClipFor,
  bundledClipSet,
  clipTextHash,
} from "./bundledClips";
import { DELIVERY_CONTEXTS } from "./deliveryContext";
import { deliveryTextTr, prewarmContextOf, slotOf, VOICE_DELIVERY_KEYS } from "./deliveryDeck";
import { questionDeliveryContextOf } from "./deliveryPlan";
import { confirmSpeechTr, questionSpeechTr } from "./speech";

const HERE = fileURLToPath(new URL(".", import.meta.url));
const JSON_PATH = join(HERE, "bundledClipSet.json");

/** The departments of the dev test visits — what a simulator run asks. */
const DEPARTMENTS = [
  ...new Set(testAccounts.flatMap((account) => account.visits.map((visit) => visit.department))),
].sort();

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
  const set = bundledClipSet(DEPARTMENTS);
  const pair = (context: string, text: string) => `${context}\u0000${text}`;
  const listed = new Set(set.map((line) => pair(line.context, line.text_tr)));
  // What the app composes, each in the context the driver asks the store for.
  const composed = new Set<string>();
  for (const department of DEPARTMENTS) {
    for (const mode of ["hizli", "detayli"] as const) {
      for (const question of spokenPack(packForVisit(department, { mode }))) {
        const context = questionDeliveryContextOf(question);
        if (context === "instrument" || context === "red") {
          continue;
        }
        composed.add(pair(context, questionSpeechTr(question)));
        composed.add(pair(context, confirmSpeechTr(question, [])));
        if (question.kind === "chips" || question.kind === "single") {
          for (const option of question.options) {
            composed.add(pair(context, confirmSpeechTr(question, [option.id])));
          }
        }
      }
    }
  }
  const deliveryLines = new Set<string>();
  for (const key of VOICE_DELIVERY_KEYS) {
    const context = prewarmContextOf(key);
    if (context === "instrument" || context === "red") {
      continue;
    }
    deliveryLines.add(pair(context, deliveryTextTr(key)));
    if (["repair", "silence"].includes(slotOf(key) ?? "")) {
      deliveryLines.add(pair("sensitive", deliveryTextTr(key)));
    }
  }

  it("covers every question line and its confirm lines, in the question's context", () => {
    for (const entry of composed) {
      expect(listed.has(entry), entry).toBe(true);
    }
  });

  it("covers every spoken INT-414 delivery line in the context its slot speaks it in", () => {
    for (const key of VOICE_DELIVERY_KEYS) {
      const context = prewarmContextOf(key);
      if (context !== "instrument" && context !== "red") {
        expect(listed.has(pair(context, deliveryTextTr(key))), key).toBe(true);
      }
    }
    // the welcome is the opening's content: it must be in the bundle
    expect(set.some((line) => line.context === "welcome")).toBe(true);
    expect(set.some((line) => line.context === "acknowledgement")).toBe(true);
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
    for (const line of set) {
      const entry = pair(line.context, line.text_tr);
      expect(composed.has(entry) || deliveryLines.has(entry), entry).toBe(true);
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
