/**
 * ADR-038 A3 (INT-473): no presented sheet anywhere, and RED covers an open
 * sheet.
 *
 * A sheet with detents is a React view rendered inside the screen that opens
 * it, and so inside the navigator container. It is never a React Native
 * `Modal`, an expo-router `formSheet` or `modal` presentation, or a portal into
 * another window. The RED root layer (ADR-033 §5, INT-446) mounts after the
 * navigator container, so it paints above any open sheet, and nothing a sheet
 * does can sit over it.
 *
 * The numbers and the per-reason motion are proved in
 * src/lib/motion/sheet.test.ts. This spec holds the wiring.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

const MOBILE = join(__dirname, "..");

/** Code only: comments explain what a file avoids, and a guard reads what it does. */
const code = (text: string): string =>
  text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

/** App code only; tests may name what the app must not. */
const TREE = walk(join(MOBILE, "src"))
  .filter((path) => /\.tsx?$/.test(path) && !/\.test\.ts$/.test(path))
  .map((path) => ({
    name: relative(MOBILE, path).split(sep).join("/"),
    source: code(readFileSync(path, "utf8")),
  }));

const source = (name: string): string => {
  const found = TREE.find((f) => f.name === name);
  expect(found, name).toBeDefined();
  return found!.source;
};

const SHEET = "src/components/DetentSheet.tsx";
const PANEL = "src/components/SectionPanel.tsx";
const DIALOGUE = "src/components/DialogueIntake.tsx";
const SHEET_NATIVE = "src/lib/motion/native/sheetMotion.ts";

/** What presents a view in a window of its own. */
const PRESENTED =
  /<Modal\b|\bpresentation:\s*["'](?:modal|formSheet|transparentModal|containedModal|fullScreenModal)["']|\bsheetAllowedDetents\b|\bcreatePortal\b|<Portal\b|@gorhom\/bottom-sheet/;

describe("no presented sheet anywhere (ADR-038 A3)", () => {
  it("nothing in src presents a view in its own window", () => {
    expect(TREE.length).toBeGreaterThan(100);
    const presented = TREE.filter((f) => PRESENTED.test(f.source)).map((f) => f.name);
    expect(presented).toEqual([]);
  });

  it("near misses: each way of presenting a sheet is caught", () => {
    for (const sample of [
      "<Modal visible transparent>",
      '<Stack.Screen options={{ presentation: "formSheet" }} />',
      "options={{ sheetAllowedDetents: [0.5, 1] }}",
      "createPortal(children, host)",
      'import BottomSheet from "@gorhom/bottom-sheet";',
    ]) {
      expect(PRESENTED.test(sample), sample).toBe(true);
    }
    expect(PRESENTED.test("<DetentSheet visible={open} />")).toBe(false);
  });
});

describe("the section sheet is in-tree", () => {
  it("SectionSheet is a DetentSheet, rendered by the dialogue inside its own tree", () => {
    expect(source(PANEL)).toMatch(/<DetentSheet\b/);
    expect(source(DIALOGUE)).toMatch(/<SectionSheet\b/);
  });

  it("only screens' own components render a DetentSheet", () => {
    const renderers = TREE.filter((f) => /<DetentSheet\b/.test(f.source)).map((f) => f.name);
    expect(renderers).toEqual([PANEL]);
  });
});

describe("DetentSheet", () => {
  it("takes focus with it, closes on the VoiceOver escape and on Android back", () => {
    const sheet = source(SHEET);
    expect(sheet).toMatch(/accessibilityViewIsModal/);
    expect(sheet).toMatch(/onAccessibilityEscape=\{\(\) => close\(\)\}/);
    expect(sheet).toMatch(/BackHandler\.addEventListener\("hardwareBackPress"/);
  });

  it("its detents, settle and motion come from the pure rules", () => {
    const sheet = source(SHEET);
    expect(sheet).toMatch(/detentOffsets\(/);
    expect(sheet).toMatch(/settleTarget\(/);
    expect(sheet).toMatch(/sheetPresent\(/);
    expect(sheet).toMatch(/sheetSettle\(/);
    expect(sheet).toMatch(/sheetClose\(/);
  });

  it("a drag follows the finger: the grabber drives the sheet's position directly", () => {
    const sheet = source(SHEET);
    expect(sheet).toMatch(/PanResponder\.create\(/);
    expect(sheet).toMatch(/onPanResponderMove/);
    expect(sheet).toMatch(/onPanResponderRelease/);
  });

  it("the spring lives in the one allowed native module, with A3's numbers", () => {
    const native = source(SHEET_NATIVE);
    expect(native).toMatch(/import \{[^}]*\bSHEET_SPRING\b[^}]*\} from "\.\.\/sheet"/);
    expect(native).not.toMatch(/stiffness:\s*\d|damping:\s*\d/);
    expect(source(SHEET)).not.toMatch(/withSpring/);
  });

  // INT-551 (the RED-UI review of #842, item 1): Reanimated reads `exiting`
  // when a view mounts or updates, never when it unmounts. The commit that
  // closes the sheet keeps it mounted and hidden, registering the close's own
  // exit (none, for an instant close), and the next commit unmounts it. The
  // two-commit rule itself is proved in src/lib/motion/sheet.test.ts.
  it("an instant close keeps the sheet one commit, hidden and with no exit, then unmounts it", () => {
    const sheet = source(SHEET);
    // What the last commit drew feeds the pure rule; a layout effect stores it.
    expect(sheet).toMatch(/const \[drawn, setDrawn\] = useState<SheetMount>\("closed"\);/);
    expect(sheet).toMatch(
      /const mount = sheetMount\(drawn, \{\s*visible: visible && height !== null,\s*close: sheetClose\(closeReason, \{ reduce \}\),?\s*\}\);/,
    );
    expect(sheet).toMatch(
      /useLayoutEffect\(\(\) => \{\s*if \(mount !== drawn\) \{\s*setDrawn\(mount\);\s*\}\s*\}, \[mount, drawn\]\);/,
    );
    // Only a closed mount unmounts the sheet; the commit that closes never does.
    expect(sheet).toMatch(/if \(height === null \|\| mount === "closed"\) \{\s*return \(/);
    expect(sheet).not.toMatch(/if \(height === null \|\| !visible\)/);
    // The parked commit is hidden from sight, touch and assistive technology,
    // and it registers the close's exit, which for an instant close is none.
    expect(sheet).toMatch(/const parked = mount === "parked";/);
    expect(sheet).toMatch(/parked: \{ display: "none" \}/);
    expect(sheet).toMatch(
      /<Animated\.View\s+style=\{\[StyleSheet\.absoluteFill, parked \? styles\.parked : null\]\}/,
    );
    expect(sheet).toMatch(/pointerEvents=\{parked \? "none" : "auto"\}/);
    expect(sheet).toMatch(/\{parked \? null : \(\s*<Pressable\b/);
    expect(sheet).toMatch(
      /exiting=\{sheetExiting\(sheetClose\(closeReason, \{ reduce \}\), height\)\}/,
    );
  });

  it("the sheet takes the side and bottom insets itself", () => {
    expect(source(SHEET)).toMatch(/paddingLeft: insets\.left/);
    expect(source(SHEET)).toMatch(/paddingRight: insets\.right/);
    expect(source(SHEET)).toMatch(/paddingBottom: insets\.bottom/);
  });
});

describe("RED covers an open sheet", () => {
  it("the root layout presents nothing, so a root layer after the navigator paints above every sheet", () => {
    const root = source("src/app/_layout.tsx");
    expect(PRESENTED.test(root)).toBe(false);
    expect(root).toMatch(/<Stack\b/);
  });
});
