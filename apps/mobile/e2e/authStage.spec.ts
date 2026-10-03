/**
 * INT-464: welcome and sign-in in the stage's visual language (ADR-039 S7,
 * GitHub #793; docs/design/liquid-glass-research.md).
 *
 * The pure parts are proved in lib/stage/{field,nav,orb,palette}.test.ts.
 * This spec holds the wiring the source alone can show:
 *
 * - welcome, phone entry and OTP entry draw on the stage's still backdrop,
 *   from the stage palette resolved with Reduce Transparency and Increase
 *   Contrast;
 * - nothing on them moves: no Reanimated, and every stage button is inert
 *   glass (`interactive={false}`). The OTP step is a gate (ADR-033 §4);
 * - the welcome mark is the stage orb drawn still; the title is the static
 *   large title, a heading;
 * - phone and OTP keep a solid native bar with only the back chevron, and the
 *   step title is a heading in the content; their fields are filled stage
 *   fields with no card around them;
 * - the dev accounts are a grouped inset list, development builds only;
 * - the consent screen, which renders hash-bound legal text, is untouched.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const MOBILE = join(__dirname, "..");

/** Code only: comments explain what a file avoids, and a guard reads what it does. */
const code = (text: string): string =>
  text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

const source = (name: string): string => code(readFileSync(join(MOBILE, name), "utf8"));

const WELCOME = "src/app/(auth)/welcome.tsx";
const PHONE = "src/app/(auth)/phone.tsx";
const OTP = "src/app/(auth)/otp.tsx";
const CONSENT = "src/app/(auth)/consent.tsx";
const CONTROLS = "src/components/stage/StageControls.tsx";
const HOOK = "src/components/stage/useStagePalette.ts";
const SCREENS = [WELCOME, PHONE, OTP] as const;

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

describe("the stage palette, resolved once for every stage screen", () => {
  it("useStagePalette follows Reduce Transparency and Increase Contrast", () => {
    const hook = source(HOOK);
    expect(hook).toMatch(
      /stagePalette\(scheme, \{\s*reduceTransparency: mode !== "liquid",\s*increasedContrast,?\s*\}\)/,
    );
    expect(hook).toContain("useIncreasedContrast()");
    expect(hook).toContain("useGlassMode()");
    expect(hook).toContain("useScheme()");
  });
});

describe.each(SCREENS)("%s draws on the still stage", (name) => {
  it("paints the stage backdrop from the stage palette, over the palette's base", () => {
    const screen = source(name);
    expect(screen).toMatch(/const palette = useStagePalette\(\);/);
    expect(screen).toMatch(/<AmbientBackdrop palette=\{palette\} \/>/);
    expect(screen).toMatch(/<Screen\b[^>]*backgroundColor: palette\.base/);
  });

  it("adds no motion: no Reanimated, and every stage button is inert glass", () => {
    const screen = source(name);
    expect(screen).not.toMatch(/react-native-reanimated|withSpring|withTiming|\bAnimated\./);
    const buttons = openings(screen, "StageButton");
    expect(buttons.length).toBeGreaterThan(0);
    for (const button of buttons) {
      expect(button, button).toContain("interactive={false}");
    }
  });

  it("keeps no old chrome: no PrimaryButton, SecondaryButton or Card", () => {
    const screen = source(name);
    expect(screen).not.toMatch(/<(?:PrimaryButton|SecondaryButton|Card)\b/);
  });
});

describe("welcome: the iOS setup layout", () => {
  it("the mark is the stage orb, drawn still", () => {
    const welcome = source(WELCOME);
    const [orb] = openings(welcome, "VoiceOrb");
    expect(orb).toBeDefined();
    expect(orb).toContain("motion={stillOrb()}");
  });

  it("the title is the static large title, a heading", () => {
    expect(source(WELCOME)).toMatch(
      /<AppText\s+role="hero"\s+heading[^>]*>\s*\{t\("app\.name"\)\}/,
    );
  });

  it("the phone sign-in is the one prominent action", () => {
    const buttons = openings(source(WELCOME), "StageButton");
    const prominent = buttons.filter((b) => /\bprominent\b/.test(b));
    expect(prominent).toHaveLength(1);
    expect(prominent[0]).toContain('label={t("welcome.phoneCta")}');
  });

  it("the dev accounts are a grouped inset list on the stage card, development builds only", () => {
    const welcome = source(WELCOME);
    const dev = welcome.slice(
      welcome.indexOf("function DevSignIn"),
      welcome.indexOf("export default"),
    );
    expect(dev).toMatch(/<ListGroup surface=\{palette\.card\}[\s>]/);
    expect(dev).toMatch(/<ListRow\b[^>]*\bchevron\b/);
    expect(welcome).toMatch(/\{__DEV__ \? <DevSignIn palette=\{palette\} \/> : null\}/);
  });
});

describe.each([
  [PHONE, "auth.phone.title"],
  [OTP, "auth.otp.title"],
] as const)("%s: a solid bar, the title in the content, filled fields", (name, title) => {
  it("the native bar is solid and shows only the back chevron", () => {
    const screen = source(name);
    expect(screen).toContain(`options={withSolidStageBar(headerOptions(t("${title}")), palette)}`);
    expect(screen).not.toMatch(/headerTransparent|withStageNav|GlassNavBackground/);
  });

  it("the step title is a static large-title heading in the content", () => {
    expect(source(name)).toMatch(
      new RegExp(
        `<AppText\\s+role="hero"\\s+heading[^>]*>\\s*\\{t\\("${title.replace(".", "\\.")}"\\)\\}`,
      ),
    );
  });

  it("each field is a filled stage field: no resting outline, the ring when focused", () => {
    const screen = source(name);
    const inputs = openings(screen, "TextInput");
    expect(inputs.length).toBeGreaterThan(0);
    for (const input of inputs) {
      expect(input).toMatch(/stageFieldChrome\(palette, \{ focused(?:: [^}]+)? \}\)/);
    }
    expect(screen).not.toMatch(/borderWidth: 1\b/);
  });
});

describe("the stage controls carry the inert variant", () => {
  it("StageButton takes `interactive`, interactive by default, and hands it to the glass", () => {
    const controls = source(CONTROLS);
    expect(controls).toMatch(/interactive = true/);
    expect(controls).toMatch(/isInteractive=\{interactive\}/);
  });

  it("the dialogue's stage buttons keep the system press response (ADR-039 S4)", () => {
    for (const button of openings(source("src/components/DialogueIntake.tsx"), "StageButton")) {
      expect(button).not.toContain("interactive={false}");
    }
  });
});

describe("what stays as it is", () => {
  it("the consent screen renders its legal text in its own look, outside the stage", () => {
    expect(source(CONSENT)).not.toMatch(/components\/stage\/|lib\/stage\//);
  });

  it("no new string: every visible line on the three screens is an existing key", () => {
    for (const name of SCREENS) {
      const screen = source(name);
      // Text children are t() calls or values, never literals.
      expect(screen, name).not.toMatch(/<AppText\b[^>]*>\s*[A-Za-zÇĞİÖŞÜçğıöşü]/);
    }
  });
});
