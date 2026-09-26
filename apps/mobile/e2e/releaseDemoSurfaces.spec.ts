/**
 * INT-354 · a release build reaches no demo-tier surface.
 *
 * The TestFlight build source is int-demo merged with main, and int-demo
 * carries surfaces that only make sense against the demo API. A release build
 * talks to the production-strict API (INT-328's configured base), so each
 * demo surface is either compiled out behind `__DEV__` or never called:
 *
 *  - `/v1/visits/sync` (INT-318) is the Acıbadem appointments read. On
 *    int-demo it built its connector row from hardcoded dev refs (audit
 *    F06); on main it reads the row from infra/connectors/sources.yaml,
 *    which ships empty, so it answers "unavailable" until a human registers
 *    one. The OTP screen used to call it unconditionally after sign-in,
 *    sending the verified phone for an answer that cannot yet be anything
 *    else. It now runs only in a dev build.
 *  - the synthetic test accounts and the OTP peek stay behind `__DEV__`
 *    (controls: already true, pinned here so a merge cannot undo them).
 *
 * The rules are checked on the source because these are screens: the mobile
 * vitest lane is node-only and cannot render a component.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..", "src");

function source(path: string): string {
  return readFileSync(join(SRC, path), "utf8");
}

/** The text of the `if (__DEV__) { … }` blocks in `text`, braces balanced. */
function devBlocks(text: string): string[] {
  const blocks: string[] = [];
  const opener = /if \(__DEV__\) \{/g;
  for (let match = opener.exec(text); match !== null; match = opener.exec(text)) {
    let depth = 1;
    let index = match.index + match[0].length;
    while (depth > 0 && index < text.length) {
      if (text[index] === "{") {
        depth += 1;
      } else if (text[index] === "}") {
        depth -= 1;
      }
      index += 1;
    }
    blocks.push(text.slice(match.index, index));
  }
  return blocks;
}

describe("the hospital visits sync (INT-318, demo tier) runs only in a dev build", () => {
  const otp = source("app/(auth)/otp.tsx");

  it("every syncVisits call on the OTP screen sits inside if (__DEV__)", () => {
    const calls = otp.split("syncVisits(").length - 1;
    expect(calls).toBeGreaterThan(0);
    const guarded = devBlocks(otp)
      .map((block) => block.split("syncVisits(").length - 1)
      .reduce((sum, n) => sum + n, 0);
    expect(guarded).toBe(calls);
  });

  it("no other screen or module calls it", () => {
    const callers = ["app/(auth)/otp.tsx", "lib/session.tsx", "app/(tabs)/visits/index.tsx"]
      .filter((path) => source(path).includes("syncVisits("))
      .sort();
    expect(callers).toEqual(["app/(auth)/otp.tsx"]);
  });
});

describe("controls: the dev sign-in surfaces stay behind __DEV__", () => {
  it("the OTP peek renders only in a dev build", () => {
    const otp = source("app/(auth)/otp.tsx");
    const peekButton = otp.indexOf("onPress={() => void peek()}");
    expect(peekButton).toBeGreaterThan(0);
    expect(otp.lastIndexOf("{__DEV__ ?", peekButton)).toBeGreaterThan(0);
  });

  it("the synthetic test accounts render only in a dev build", () => {
    const welcome = source("app/(auth)/welcome.tsx");
    const accounts = welcome.indexOf("testAccounts.map(");
    expect(accounts).toBeGreaterThan(0);
    expect(welcome.lastIndexOf("{__DEV__ ?", accounts)).toBeGreaterThan(0);
  });
});
