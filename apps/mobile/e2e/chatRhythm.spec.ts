/**
 * INT-423: the conversation as source facts (docs/design/chat-rhythm.md).
 *
 * - Materials sit on chrome only. The composer and the CTAs ride the glass
 *   bar; bubbles and text sit on solid fills and never on a material.
 * - Turns group. The transcript spaces bubbles with lib/dialogue/rhythm, and
 *   the tail corner belongs to a group's last bubble alone.
 * - The measure is readable, and an accessibility text size never breaks a
 *   question word inside its bubble (checked at React Native's own AX1-AX5
 *   multipliers).
 * - The lead-in is a lighter secondary line above the question.
 *
 * React Native has no DOM, so the tree proves the wiring and arithmetic
 * proves the fit, as in designSystem.spec.ts.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { readFontMetrics } from "./fontMetrics";
import { bubbleMaxWidth } from "@/lib/dialogue/rhythm";
import { en } from "@/lib/i18n/en";
import { tr } from "@/lib/i18n/tr";
import { allQuestions } from "@/lib/intake/questions";
import { scaledSize, spacing } from "@/lib/theme";

const MOBILE = join(__dirname, "..");

/** Code only: comments explain what a file avoids, and a guard reads what it does. */
const code = (source: string): string =>
  source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

const source = (name: string): string => code(readFileSync(join(MOBILE, name), "utf8"));

const DIALOGUE = "src/components/DialogueIntake.tsx";
const LINES = "src/components/ChatLines.tsx";

describe("materials on chrome, content on solid fills (HIG Materials)", () => {
  it("the transcript draws no material; the composer and CTAs ride the glass bar", () => {
    const dialogue = source(DIALOGUE);
    expect(dialogue).not.toMatch(/<GlassView\b|<BlurView\b|\buseGlassMode\b|expo-blur/);
    expect(dialogue).toMatch(/<GlassBar\b[^>]*>[\s\S]*styles\.composerRow[\s\S]*<\/GlassBar>/);
    expect(source(LINES)).not.toMatch(/GlassView|BlurView|useGlassMode/);
  });

  it("every bubble fill is a solid palette token", () => {
    const dialogue = source(DIALOGUE);
    const fills = [...dialogue.matchAll(/backgroundColor:\s*([^,}\n]+)/g)].map((m) => m[1].trim());
    expect(fills.length).toBeGreaterThan(3);
    for (const fill of fills) {
      expect(fill).toMatch(
        // INT-462: a chip takes INT-433's chipChrome, whose two fills are the
        // palette's surface and primarySoft (lib/controlChrome.ts).
        /^(?:theme\.(?:surface|surfaceRaised|primarySoft|primary|ink|cta)|[a-z]+ \? theme\.\w+ : theme\.\w+|look\.backgroundColor)$/,
      );
    }
  });
});

describe("turns group, and the tail is a group's last bubble alone", () => {
  it("the transcript places every bubble through rhythm.ts", () => {
    const dialogue = source(DIALOGUE);
    expect(dialogue).toContain("placeTurns(");
    expect(dialogue).toContain("bubbleMaxWidth(");
    expect(dialogue).toContain("sideOf");
    // Every bubble takes its shape from the placement: the agent's question
    // and confirm turns, the two patient states and the open-mic turn. INT-414
    // moved the "not understood" line into the delivery plan, so it is no
    // longer a stream bubble of its own.
    expect(dialogue.match(/\.\.\.shape\(/g)?.length ?? 0).toBeGreaterThanOrEqual(4);
    // A delivery line (INT-414) sits outside the turn list: the measure, no tail.
    expect(dialogue).toMatch(/renderDeliveryBubble[\s\S]*?\{ maxWidth: measure \}/);
  });

  it("the tail corner lives in the tail styles alone, never on every bubble", () => {
    const dialogue = source(DIALOGUE);
    const block = (name: string) =>
      new RegExp(`\\b${name}: \\{([^}]*)\\}`).exec(dialogue)?.[1] ?? "";
    expect(block("agentBubble")).not.toContain("borderBottomLeftRadius");
    expect(block("patientBubble")).not.toContain("borderBottomRightRadius");
    expect(block("agentTail")).toContain("borderBottomLeftRadius");
    expect(block("patientTail")).toContain("borderBottomRightRadius");
    // The measure comes from rhythm.ts, not a percentage pinned in a style.
    expect(block("bubble")).not.toContain("maxWidth");
  });

  it("the transcript's own gap is the turn gap the grouped margin is taken from", () => {
    expect(source(DIALOGUE)).toMatch(/content: \{ gap: spacing\.md,/);
  });
});

describe("the lead-in is a lighter line above the question", () => {
  it("renders before the question, in the Subheadline role and the secondary ink", () => {
    const lines = source(LINES);
    const lead = lines.indexOf("{leadIn}");
    const question = lines.indexOf("{question}");
    expect(lead).toBeGreaterThan(-1);
    expect(question).toBeGreaterThan(lead);
    expect(lines).toMatch(/<AppText role="label" color="inkSoft">\s*\{leadIn\}/);
    expect(lines).toMatch(/<AppText role="body">\s*\{question\}/);
  });

  it("the agent's question bubble renders through it", () => {
    expect(source(DIALOGUE)).toContain("<AgentQuestionLines");
  });
});

describe("Dynamic Type up to AX5 inside a bubble", () => {
  const MULTIPLIERS = [
    ...readFileSync(
      join(MOBILE, "node_modules/react-native/React/CoreModules/RCTAccessibilityManager.mm"),
      "utf8",
    ).matchAll(/UIContentSizeCategory(\w+)\s*:\s*@([\d.]+)/g),
  ].map((m) => [m[1], Number(m[2])] as const);

  /** Inter Regular: the measured upper bound for SF Pro (docs/evidence/INT-422.md). */
  const face = readFontMetrics(
    join(MOBILE, "node_modules/@expo-google-fonts/inter/400Regular/Inter_400Regular.ttf"),
  );

  const WORDS = [
    ...new Set(
      allQuestions
        .flatMap((q) => [tr[q.titleKey], en[q.titleKey]])
        .flatMap((text) => text.split(/\s+/))
        .flatMap((word) => word.split(/(?<=-)/)),
    ),
  ].filter((word) => word.length > 0);

  /** WCAG 1.4.10's reflow width (an iPhone in Display Zoom), less the margins. */
  const CONTENT = 320 - 2 * spacing.screen;

  it("reads the table and the words it is supposed to", () => {
    expect(MULTIPLIERS.length).toBe(12);
    expect(WORDS.length).toBeGreaterThan(200);
  });

  it.each(MULTIPLIERS)(
    "%s (×%s): every question word fits its bubble at 320 pt",
    (_name, scale) => {
      const inner = bubbleMaxWidth(CONTENT, scale) - 2 * spacing.md;
      const size = scaledSize("body", scale);
      const tooWide = WORDS.filter((word) => face.advance(word, size) > inner);
      expect(tooWide).toEqual([]);
    },
  );

  it("near miss: at 2.0 the old fixed 84 % bubble breaks a question word at 320 pt", () => {
    const inner = Math.round(CONTENT * 0.84) - 2 * spacing.md;
    const size = scaledSize("body", 2.0);
    expect(WORDS.some((word) => face.advance(word, size) > inner)).toBe(true);
  });
});
