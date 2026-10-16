/**
 * INT-465: the pre-positioned RED catalog is refused unless it carries CD-24's
 * generic RED with words, so a generic RED is never wordless (CD-24
 * `generic_red_silent_is_never_wordless`).
 *
 * The hop sends no answer until a catalog is on the device. A catalog that
 * cannot say the generic RED therefore means no RED can arrive that the device
 * would have to show without words. The near miss is the recorded catalog the
 * real route serves, which decodes.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { GENERIC_RED_SCRIPT_IDS } from "../livekit/red";
import { decodeRedCatalog, type HopTransport } from "./hop";
import { createRedHop, createRedStore } from "./store";

const FIXTURES = join(__dirname, "..", "..", "..", "..", "..", "tests", "fixtures", "triage_hop");
const RAW = JSON.parse(readFileSync(join(FIXTURES, "red_catalog.json"), "utf8")) as {
  scripts: Record<string, Record<string, unknown>>;
  questions: Record<string, Record<string, unknown>>;
};

const bytes = (body: unknown) => new TextEncoder().encode(JSON.stringify(body));

function without(edit: (raw: typeof RAW) => void): Uint8Array {
  const copy = JSON.parse(JSON.stringify(RAW)) as typeof RAW;
  edit(copy);
  return bytes(copy);
}

describe("CD-24 generic_red_silent_is_never_wordless — the catalog", () => {
  it("decodes the catalog the real route serves (near miss)", () => {
    expect(decodeRedCatalog(bytes(RAW))).not.toBeNull();
  });

  it.each([
    ["no generic REMOTE", (r: typeof RAW) => delete r.scripts[GENERIC_RED_SCRIPT_IDS.REMOTE]],
    ["no generic ON_SITE", (r: typeof RAW) => delete r.scripts[GENERIC_RED_SCRIPT_IDS.ON_SITE]],
    ["no generic question", (r: typeof RAW) => delete r.questions[GENERIC_RED_SCRIPT_IDS.UNKNOWN]],
    [
      "a wordless generic REMOTE",
      (r: typeof RAW) => (r.scripts[GENERIC_RED_SCRIPT_IDS.REMOTE].actionTr = ""),
    ],
    [
      "a blank generic ON_SITE",
      (r: typeof RAW) => (r.scripts[GENERIC_RED_SCRIPT_IDS.ON_SITE].actionTr = "   "),
    ],
  ])("refuses a catalog with %s", (_name, edit) => {
    expect(decodeRedCatalog(without(edit))).toBeNull();
  });

  it("refuses the whole catalog when any question sends no answer ON_SITE (near miss: REMOTE decodes)", () => {
    for (const id of Object.keys(RAW.questions)) {
      expect(
        decodeRedCatalog(without((r) => (r.questions[id].onNoAnswer = "ON_SITE"))),
        id,
      ).toBeNull();
    }
    expect(
      decodeRedCatalog(
        without((r) => (r.questions[GENERIC_RED_SCRIPT_IDS.UNKNOWN].onNoAnswer = "REMOTE")),
      ),
    ).not.toBeNull();
  });

  // Round 5: yes is in the hospital, no is not — the DSL and the catalog say so.
  it("refuses the whole catalog when any question swaps yes and no (near miss: ON_SITE/REMOTE decodes)", () => {
    for (const id of Object.keys(RAW.questions)) {
      expect(
        decodeRedCatalog(without((r) => (r.questions[id].onYes = "REMOTE"))),
        `${id} onYes`,
      ).toBeNull();
      expect(
        decodeRedCatalog(without((r) => (r.questions[id].onNo = "ON_SITE"))),
        `${id} onNo`,
      ).toBeNull();
    }
    expect(
      decodeRedCatalog(
        without((r) => {
          const q = r.questions[GENERIC_RED_SCRIPT_IDS.UNKNOWN];
          q.onYes = "ON_SITE";
          q.onNo = "REMOTE";
        }),
      ),
    ).not.toBeNull();
  });

  it("a hop given such a catalog sends no answer, so no RED can arrive wordless", async () => {
    const paths: string[] = [];
    const transport: HopTransport = async (path) => {
      paths.push(path);
      return {
        status: 200,
        bytes: without((r) => delete r.scripts[GENERIC_RED_SCRIPT_IDS.ON_SITE]),
      };
    };
    const store = createRedStore();
    const hop = createRedHop({
      transport,
      store,
      now: () => 0,
      clock: () => new Date("2026-10-03T07:00:00.000Z"),
    });
    const outcome = await hop.onAnswers(
      "visit",
      [{ questionId: "extra", values: ["x"] }],
      "REMOTE",
    );
    expect(outcome.kind).toBe("unevaluated");
    expect(paths.every((path) => !path.endsWith("/evaluate"))).toBe(true);
    expect(store.getSnapshot()).toBeNull();
  });
});
