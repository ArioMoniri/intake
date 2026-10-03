/**
 * INT-472: review and send as iOS Settings grouped inset lists (GitHub #802;
 * docs/design/library-patterns.md §5.2 "Review and summary").
 *
 * The rows each section shows, and the summary's metadata rows, are proved in
 * src/lib/intake/reviewRows.test.ts. This spec holds the wiring the source
 * alone can show:
 *
 * - every note section is a ListGroup under its section title, drawn from
 *   `reviewSectionRows`; the old cards and tonal chips are gone;
 * - the share control is the app's SwitchRow: one element with the switch
 *   role, named with its section, its state also in words, read-only once
 *   sent;
 * - edits are navigation rows with a chevron, named with their section;
 * - the share summary is a metadata group of `shareSummaryRows`; after send
 *   the ladder has its own group and CSAT stays in the sent branch;
 * - the bottom bar is never see-through: where iOS draws no glass (INT-131's
 *   capture protection on this screen), its floor is the fallback wash;
 * - no motion is added.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { en } from "../src/lib/i18n/en";
import { tr } from "../src/lib/i18n/tr";

const MOBILE = join(__dirname, "..");

/** Code only: comments explain what a file avoids, and a guard reads what it does. */
const code = (text: string): string =>
  text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

const source = (name: string): string => code(readFileSync(join(MOBILE, name), "utf8"));

const REVIEW = "src/app/(tabs)/visits/[visitId]/review.tsx";
const SWITCH_ROW = "src/components/SwitchRow.tsx";
const LIST_ROW = "src/components/ListRow.tsx";
const GLASS_BAR = "src/components/GlassBar.tsx";

/** Every `<Tag ...>` opening in `text`, props and all. */
function openings(text: string, tag: string): string[] {
  const found: string[] = [];
  const pattern = new RegExp(`<${tag}\\b`, "g");
  for (let m = pattern.exec(text); m !== null; m = pattern.exec(text)) {
    let depth = 0;
    let end = m.index;
    for (let i = m.index; i < text.length; i += 1) {
      const ch = text[i];
      if (ch === "{") depth += 1;
      if (ch === "}") depth -= 1;
      if (ch === ">" && depth === 0) {
        end = i;
        break;
      }
    }
    found.push(text.slice(m.index, end + 1));
  }
  return found;
}

describe("each note section is a grouped inset list", () => {
  it("draws its rows from reviewSectionRows, under the section title, in a ListGroup", () => {
    const review = source(REVIEW);
    expect(review).toMatch(/reviewSectionRows\(section, \{ shared, sent \}\)/);
    expect(review).toMatch(/<Kicker label=\{t\(section\.titleKey\)\} inset \/>\s*<ListGroup\b/);
  });

  it("the old cards and tonal chips are gone", () => {
    const review = source(REVIEW);
    expect(review).not.toMatch(/<Card\b/);
    expect(review).not.toMatch(/scopeChip/);
  });

  it("each line is a row; the facts block keeps its INT-256 kind", () => {
    const review = source(REVIEW);
    expect(review).toMatch(/row\.kind === "line"[\s\S]*?<ListRow\b[^>]*label=\{row\.text\}/);
    expect(review).toMatch(
      /<CarriedFactReview\b[\s\S]*?fact\.kind === row\.factKind[\s\S]*?disabled=\{sent\}/,
    );
  });

  it("the section's note is the group's footer", () => {
    expect(source(REVIEW)).toMatch(/footer=\{footerKey === null \? undefined : t\(footerKey\)\}/);
  });
});

describe("the share control is a switch row", () => {
  it("one SwitchRow per section: named with the section, the state in words, read-only once sent", () => {
    const [row] = openings(source(REVIEW), "SwitchRow");
    expect(row).toBeDefined();
    expect(row).toContain('label={t("review.shareSwitch")}');
    expect(row).toMatch(
      /sublabel=\{row\.shared \? t\("review\.shared"\) : t\("review\.notShared"\)\}/,
    );
    expect(row).toContain("checked={row.shared}");
    expect(row).toContain("labelContext={t(section.titleKey)}");
    expect(row).toContain("disabled={row.readOnly}");
    expect(row).toContain('hint={t("a11y.shareHint")}');
  });

  it("flipping it is the same scope dispatch as before", () => {
    expect(source(REVIEW)).toMatch(
      /updateNote\(visitId, \{\s*type: "scope",\s*sectionId: section\.id,\s*shared: next,?\s*\}\)/,
    );
  });

  it("SwitchRow names itself with its context and honours disabled", () => {
    const row = source(SWITCH_ROW);
    expect(row).toContain("accessibilityLabel={withContext(label, labelContext)}");
    expect(row).toMatch(/accessibilityState=\{\{ checked, disabled \}\}/);
    expect(row).toContain("disabled={disabled}");
  });

  it("the new label is Turkish-first, mirrored, siz-safe and no imperative", () => {
    expect(tr["review.shareSwitch"]).toBe("Hekimle paylaşılsın");
    expect(en["review.shareSwitch"]).toBeTruthy();
    expect(tr["review.shareSwitch"]).not.toMatch(/\bsen\b|\bsana\b|\d/);
  });
});

describe("edits are navigation rows", () => {
  it("each edit row has a chevron and is named with its section", () => {
    const review = source(REVIEW);
    const edits = openings(review, "ListRow").filter((row) => row.includes("row.labelKey"));
    expect(edits).toHaveLength(1);
    expect(edits[0]).toContain("chevron");
    expect(edits[0]).toContain("labelContext={t(section.titleKey)}");
    expect(review).toMatch(/\/intake\?q=\$\{row\.target\}/);
  });
});

describe("the partial note and the summary", () => {
  it("a checkpointed note lists what is missing as rows, and resume as a navigation row", () => {
    const review = source(REVIEW);
    expect(review).toMatch(
      /<Kicker label=\{t\("review\.eksik\.title"\)\} inset \/>\s*<ListGroup\b/,
    );
    expect(review).toMatch(/<ListRow\b[^>]*label=\{t\(q\.titleKey\)\}/);
    expect(review).toMatch(/<ListRow\b[^>]*label=\{t\("review\.resume"\)\}[^>]*chevron/);
  });

  it("the share summary is a metadata group of shareSummaryRows", () => {
    const review = source(REVIEW);
    expect(review).toMatch(
      /<Kicker label=\{t\("review\.consent\.title"\)\} inset \/>\s*<ListGroup\b/,
    );
    expect(review).toMatch(/shareSummaryRows\(summary\)\.map\(/);
    expect(review).toMatch(/<MetadataRow\b[^>]*label=\{row\.label\}[^>]*values=\{row\.values\}/);
    expect(source(LIST_ROW)).toMatch(/export function MetadataRow\b/);
  });

  it("after send the ladder has its own group", () => {
    expect(source(REVIEW)).toMatch(
      /<Kicker label=\{t\("visits\.detail\.noteStatus"\)\} inset \/>\s*<ListGroup\b[\s\S]*?<StatusLadder\b/,
    );
  });
});

describe("the bottom bar is never see-through", () => {
  /** True when the liquid branch draws blur, then the wash, then the glass. */
  function floored(bar: string): boolean {
    const liquid = bar.slice(
      bar.indexOf('if (mode === "liquid")'),
      bar.indexOf('if (mode === "solid")'),
    );
    const blurAt = liquid.indexOf("<BlurView");
    const washAt = liquid.indexOf("backgroundColor: fallback.backgroundColor");
    const glassAt = liquid.indexOf("<GlassView");
    return blurAt > -1 && washAt > blurAt && glassAt > washAt;
  }

  it("its Liquid Glass sits over the system blur and the fallback wash", () => {
    // Where iOS draws no glass (captured on this screen), the bar is still a
    // frosted bar, so the note never shows through under the CTA.
    expect(floored(source(GLASS_BAR))).toBe(true);
  });

  it("near miss: a bare GlassView bar, with nothing under it, would be caught", () => {
    const bare = [
      'if (mode === "liquid") {',
      '  return <GlassView glassEffectStyle="regular" style={barStyle}>{inner}</GlassView>;',
      "}",
      'if (mode === "solid") {',
    ].join("\n");
    expect(floored(bare)).toBe(false);
  });
});

describe("no motion is added", () => {
  it("the review screen imports no animation", () => {
    expect(source(REVIEW)).not.toMatch(/react-native-reanimated|withSpring|withTiming|Animated\./);
  });
});
