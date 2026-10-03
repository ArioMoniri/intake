/**
 * INT-421 · a release build labels no account as synthetic.
 *
 * Owner directive: "in production don't include deneme hastası". The Me
 * screen's account row carried `me.syntheticBadge` ("Sentetik deneme hesabı")
 * under EVERY signed-in account, including a real phone-verified one in a
 * store build. The label belongs to the synthetic dev session alone (INT-130
 * fixture, signed in through the INT-197 `__DEV__` card), and the session says
 * which is which by `kind`, never by the display name, which INT-318 may
 * replace from the hospital feed.
 *
 * The vitest lane has no renderer, so the decision lives in a pure module and
 * the screens are pinned to it by source, the way records/screen.test.ts pins
 * Kayıtlarım.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { maskPhone } from "../auth/phone";
import { testAccounts } from "../dev/accounts";
import { tr } from "../i18n/tr";
import { accountBadgeKey, isSyntheticSession } from "./badge";

const APP = join(__dirname, "..", "..", "app");
const ME = readFileSync(join(APP, "(tabs)", "me", "index.tsx"), "utf8");
const RECORDS = readFileSync(join(APP, "(tabs)", "records.tsx"), "utf8");

/** A signed-in account as the session holds it: its kind and display name. */
function account(kind: "dev" | "otp", name: string): { kind: "dev" | "otp"; name: string } {
  return { kind, name };
}

const dev = account("dev", testAccounts[0].name);
// signInOtp names a real account by its masked phone (INT-131)
const otp = account("otp", maskPhone("+905321114455"));

describe("the synthetic label follows the session kind", () => {
  it("the synthetic dev session shows the badge", () => {
    expect(isSyntheticSession(dev)).toBe(true);
    expect(accountBadgeKey(dev)).toBe("me.syntheticBadge");
  });

  it("a phone-verified account shows none", () => {
    expect(isSyntheticSession(otp)).toBe(false);
    expect(accountBadgeKey(otp)).toBeNull();
  });

  it("no session shows none", () => {
    expect(isSyntheticSession(null)).toBe(false);
    expect(accountBadgeKey(null)).toBeNull();
  });

  it.each([testAccounts[0].name, tr["me.syntheticBadge"], "Deneme Hastası"])(
    "near miss: an OTP account whose name looks synthetic (%s) still gets none",
    (name) => {
      expect(accountBadgeKey(account("otp", name))).toBeNull();
      expect(isSyntheticSession(account("otp", name))).toBe(false);
    },
  );

  it("near miss: an unknown kind fails closed to no badge", () => {
    const unknown = { kind: "demo" } as unknown as { kind: "dev" | "otp" };
    expect(accountBadgeKey(unknown)).toBeNull();
  });

  it("the key it returns is the catalogue's synthetic label", () => {
    expect(tr["me.syntheticBadge"].trim().length).toBeGreaterThan(0);
  });
});

describe("the screens take the decision from the helper", () => {
  it("the Me account row renders the badge only through accountBadgeKey", () => {
    expect(ME).toContain('from "@/lib/profile/badge"');
    expect(ME).toContain("accountBadgeKey(account)");
    // the unconditional label is gone
    expect(ME).not.toContain('t("me.syntheticBadge")');
    expect(ME).not.toContain("me.syntheticBadge");
  });

  it("Kayıtlarım shows the synthetic sample only for the synthetic session", () => {
    expect(RECORDS).toContain('from "@/lib/profile/badge"');
    // the dev branch is the helper's true arm, and the only place DevRecords mounts
    expect(RECORDS).toMatch(/isSyntheticSession\(account\) \?\s*\([^<]*<DevRecords /);
    expect(RECORDS.split("<DevRecords ").length - 1).toBe(1);
    // the old fail-open form: anything not proven OTP got the synthetic list
    expect(RECORDS).not.toContain('account?.kind === "otp"');
  });
});
