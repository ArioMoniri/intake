/**
 * INT-354 on the INT-328 rule: a release build walks no dev LAN lane.
 *
 * INT-328 gave the API base one resolver and kept the LAN walk behind
 * `__DEV__`. The voice lanes did not go through that resolver: the ASR probe
 * (DialogueGate → voice.ts, port 8802), the extract bridge (8804) and the TTS
 * ladder (8805/8803) each read `configuredServiceCandidates` /
 * `configuredTtsLaneCandidates` directly, so a TestFlight build still probed
 * the Metro host and `extra.asrHosts` (127.0.0.1 and a hotspot address) over
 * plain http the moment a patient opened an intake. That is the audit's F01
 * fix left half-done ("in !__DEV__, ignore hostUri and asrHosts") and it is
 * what raises the iOS local-network prompt F17 removed the purpose string for.
 *
 * The gate sits at the one module that reads those hosts, so every lane is
 * covered by a single branch:
 *
 *  - `devLanCandidates` is the pure rule: outside a dev build it returns no
 *    candidate and never runs the walk.
 *  - `expoHosts.ts` routes BOTH exports through it with `__DEV__`, never a
 *    literal (checked on the source, the same way apiBase.test.ts checks
 *    expoApiBase.ts, because a node test cannot import expo-constants).
 *  - nothing else in src reads the Metro hostUri, so there is no second walk
 *    to forget.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it, vi } from "vitest";

import { devLanCandidates } from "./hosts";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, "..", "..");

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      out.push(...sourceFiles(path));
    } else if (/\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name)) {
      out.push(path);
    }
  }
  return out;
}

describe("devLanCandidates · the dev LAN walk exists only in a dev build", () => {
  it("a release build gets no candidate and the walk never runs", () => {
    const walk = vi.fn(() => ["http://127.0.0.1:8802", "http://172.20.10.3:8802"]);
    expect(devLanCandidates(false, walk)).toEqual([]);
    expect(walk).not.toHaveBeenCalled();
  });

  it("a dev build walks exactly as before (control)", () => {
    const walk = vi.fn(() => ["http://127.0.0.1:8802", "http://172.20.10.3:8802"]);
    expect(devLanCandidates(true, walk)).toEqual([
      "http://127.0.0.1:8802",
      "http://172.20.10.3:8802",
    ]);
    expect(walk).toHaveBeenCalledTimes(1);
  });
});

describe("expoHosts.ts gates every lane on __DEV__", () => {
  const source = readFileSync(join(HERE, "expoHosts.ts"), "utf8");

  it.each(["configuredServiceCandidates", "configuredTtsLaneCandidates"])(
    "%s returns through devLanCandidates(__DEV__, …)",
    (name) => {
      const start = source.indexOf(`export function ${name}(`);
      expect(start).toBeGreaterThanOrEqual(0);
      const next = source.indexOf("export function", start + 1);
      const body = source.slice(start, next === -1 ? undefined : next);
      expect(body).toMatch(/return devLanCandidates\(__DEV__,/);
    },
  );

  it("no other module in src reads the Metro hostUri", () => {
    const readers = sourceFiles(SRC)
      .filter((file) => /expoConfig\??\.hostUri/.test(readFileSync(file, "utf8")))
      .map((file) => relative(SRC, file).split(sep).join("/"));
    expect(readers).toEqual(["lib/dev/expoHosts.ts"]);
  });
});
