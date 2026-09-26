/**
 * INT-259 — T-3, the negative fixture for the channel brands.
 *
 * This suite's real assertions are the `@ts-expect-error` lines: they fail
 * `pnpm typecheck` if the brands ever become assignable to one another, which
 * is the whole mechanism. The runtime `expect`s only prove the constructors
 * are the identity at runtime, so a branded key still reaches `t()`.
 *
 * The channel *split* — `titleKey: SpokenKey`, `affordanceKey: ScreenKey` on
 * `IntakeQuestion`, and the structurally-narrowed `questionSpeechTr` — is the
 * next issue. What is pinned here is that the two brands are disjoint, which
 * is what makes that split enforceable rather than conventional.
 */
import { describe, expect, it } from "vitest";

import { screenKey, spokenKey, type ScreenKey, type SpokenKey } from "./channel";
import { t } from ".";
import type { MessageKey } from "./tr";

function speak(key: SpokenKey): string {
  return t(key);
}

function show(key: ScreenKey): string {
  return t(key);
}

describe("the two channels are disjoint at the type level", () => {
  it("a screen key cannot be spoken", () => {
    const affordance = screenKey("dialogue.status.silent");
    // @ts-expect-error a ScreenKey is not a SpokenKey — this is the mechanism
    speak(affordance);
    expect(t(affordance)).toBeTypeOf("string");
  });

  it("a spoken key cannot become an affordance line", () => {
    const script = spokenKey("intake.q.complaint");
    // @ts-expect-error a SpokenKey is not a ScreenKey
    show(script);
    expect(t(script)).toBeTypeOf("string");
  });

  it("an unbranded catalogue key belongs to neither channel until it is declared", () => {
    const bare: MessageKey = "dialogue.confirm";
    // @ts-expect-error a bare MessageKey has not declared its channel
    speak(bare);
    // @ts-expect-error a bare MessageKey has not declared its channel
    show(bare);
    expect(t(bare)).toBeTypeOf("string");
  });

  it("both brands are still catalogue keys, so `t` accepts them unchanged", () => {
    expect(t(spokenKey("dialogue.confirm"))).toBe(t("dialogue.confirm"));
    expect(t(screenKey("dialogue.confirm"))).toBe(t("dialogue.confirm"));
  });

  it("the constructors are the identity — a brand costs nothing at runtime", () => {
    expect(spokenKey("dialogue.confirm")).toBe("dialogue.confirm");
    expect(screenKey("dialogue.confirm")).toBe("dialogue.confirm");
  });
});
