/**
 * INT-263 — the behavioural half: can the patient still REACH the content at
 * the top of the INT-260 ladder?
 *
 * `src/app/scroll-containers.test.ts` is the static sweep. It walks the route
 * tree, and for each FILE it asks whether the tokens of a scroll container
 * appear in it and whether the catalogue copy that file declares models taller
 * than a phone. That is the right shape for a gate on a new screen, and it is
 * deliberately not what this file does. Four things the sweep cannot ask, and
 * they are the four the acceptance is actually about:
 *
 *  1. **Which screen.** A route is not one screen. `otp.tsx` renders one thing
 *     while the pending phone is null and another once it is not; `intake.tsx`
 *     hands its body to one of three components by phase; `review.tsx` has an
 *     empty state and a full one. A file-level token match passes as soon as
 *     ONE branch holds the container. This file resolves every `return` in the
 *     file into a screen state of its own and asks the question per state, so
 *     a branch that renders a bare frame is convicted even when its neighbour
 *     scrolls.
 *  2. **Where the content sits, not how much of it there is.** The sweep sums
 *     heights. Reachability is about POSITIONS: the welcome defect was not
 *     that the copy was tall, it was that a non-scrolling box with
 *     `justifyContent: "center"` clips an overflow at BOTH ends, which is why
 *     the title went under the status bar and `welcome.body` went with it.
 *     This file lays the state's elements out — text, fields, buttons and card
 *     padding, at the shipped tokens — and asks of each one whether any scroll
 *     offset brings it into the viewport.
 *  3. **The keyboard.** The sweep asserts that the string
 *     `automaticallyAdjustKeyboardInsets` occurs in `Themed.tsx` and that the
 *     free-text ROUTES declare `keyboardShouldPersistTaps`. Neither says
 *     anything about the state the field is actually in: a scroll region whose
 *     frame runs under the keyboard can only be scrolled until the content's
 *     bottom meets the frame's bottom, so the last keyboard-height of content
 *     is unreachable while typing however tall the content is. That is the
 *     covered-field defect, and it is asserted here as a position.
 *  4. **The counterfactual.** The sweep proves a container is present. This
 *     file proves the container is doing work: for every state it also lays
 *     the same content out with the container taken away — the tree as it
 *     stood before INT-263 — and NAMES the catalogue keys that fall out of
 *     reach. At 2.0 that set is non-empty on real screens; at 1.0 it is empty
 *     on the same screens, which is the acceptance's own argument (a check
 *     that only ran at the default would have passed on welcome the day the
 *     defect shipped) carried out per screen instead of once.
 *
 * WHAT THIS FILE IS NOT, stated plainly because the difference matters:
 *
 * - **Nothing here is rendered.** The vitest lane in this app runs in `node`
 *   with no renderer — no `react-test-renderer`, no testing-library, and
 *   `react-native` itself ships Flow source that this lane cannot even
 *   import. `e2e/` in this repo is a vitest folder, not a device harness
 *   (`flows.spec.ts` reads screens with `readFileSync`), and this file keeps
 *   that idiom rather than inventing a second one. "Renders" below always
 *   means "the screen state resolved from the source, laid out by the model in
 *   §2". No screenshot exists and none is claimed.
 * - **The layout is a model**, and it is a FLOOR. It counts catalogue copy,
 *   text fields, buttons and card padding; it does not count images, list
 *   fixtures, server strings, rows built by `.map` over data, or the extra
 *   lines a card's narrower measure forces. Every one of those omissions makes
 *   a screen model SHORTER than it renders, so the counterfactual convicts
 *   fewer screens than reality would — a named loss here is a loss; silence is
 *   not a clean bill of health, which is why the sweep's rule 1 applies to
 *   every route regardless.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { basename, join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

import { MIN_TAP } from "../src/lib/a11y/target";
import { tr, type MessageKey } from "../src/lib/i18n/tr";
import { APP_STEPS, isLargeText } from "../src/lib/prefs/appearance";
import { lineHeight, scaledSize, spacing, type TypeRole } from "../src/lib/theme";

const MOBILE = join(__dirname, "..");
const APP = join(MOBILE, "src", "app");
const COMPONENTS = join(MOBILE, "src", "components");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

const named = (path: string): string => relative(MOBILE, path).split(sep).join("/");

/* ------------------------------------------------------------------ */
/* §1 — screen states, one per branch a patient can land on            */
/* ------------------------------------------------------------------ */

/** Containers that scroll. A state rooted in one can reach its own overflow. */
const SCROLLERS = ["ScrollScreen", "ScrollView", "FlatList", "SectionList", "FlashList"];

/**
 * Roots that occupy the whole screen. `Screen` and `SafeAreaView` are frames
 * that do NOT scroll — they are legal only when they host a scroll region
 * inside them (the intake and review flows do, beside a fixed glass bar) —
 * and `KeyboardAvoidingView` is a frame that resizes with the keyboard, which
 * is the other way a field is kept reachable.
 */
const FRAMES = [...SCROLLERS, "Screen", "SafeAreaView", "KeyboardAvoidingView", "Redirect"];

/**
 * The expression of every `return` in a file, in source order.
 *
 * Read to the `;` that closes the statement, with brackets counted and
 * strings and comments skipped, so a parenthesised block, a one-line
 * `return <Redirect … />;` and a ternary between two of them are all read the
 * same way. `return null` yields an empty state — a screen that renders
 * nothing, and therefore has nothing to lose.
 */
function returnedJsx(source: string): string[] {
  const out: string[] = [];
  for (const match of source.matchAll(/\breturn\b/g)) {
    const at = match.index + match[0].length;
    let depth = 0;
    let quote: string | null = null;
    let line = false;
    let block = false;
    let index = at;
    for (; index < source.length; index += 1) {
      const char = source[index];
      const next = source[index + 1];
      if (line) {
        if (char === "\n") line = false;
        continue;
      }
      if (block) {
        if (char === "*" && next === "/") {
          block = false;
          index += 1;
        }
        continue;
      }
      if (quote !== null) {
        if (char === "\\") index += 1;
        else if (char === quote) quote = null;
        continue;
      }
      if (char === "/" && next === "/") {
        line = true;
        index += 1;
        continue;
      }
      if (char === "/" && next === "*") {
        block = true;
        index += 1;
        continue;
      }
      if (char === '"' || char === "'" || char === "`") {
        quote = char;
        continue;
      }
      if (char === "(" || char === "[" || char === "{") depth += 1;
      if (char === ")" || char === "]" || char === "}") depth -= 1;
      if (depth < 0) break;
      if (char === ";" && depth === 0) break;
    }
    out.push(source.slice(at, index));
  }
  return out;
}

function rootTag(jsx: string): string | null {
  const match = /<([A-Za-z][\w.]*)/.exec(jsx);
  return match === null ? null : match[1];
}

/** The open tag of the first `<Tag` in `jsx`, attributes included. */
function openTag(jsx: string, tag: string): string {
  const start = jsx.indexOf(`<${tag}`);
  if (start === -1) {
    return "";
  }
  const end = jsx.indexOf(">", start);
  return jsx.slice(start, end === -1 ? jsx.length : end + 1);
}

/** The style block a `styles.<name>` reference resolves to, as source text. */
function styleBlock(source: string, name: string): string {
  const match = new RegExp(`\\b${name}:\\s*\\{([^{}]*)\\}`).exec(source);
  return match === null ? "" : match[1];
}

interface Surface {
  /** `src/app/(auth)/welcome.tsx#0` — the file and which branch of it. */
  readonly id: string;
  readonly file: string;
  readonly root: string;
  /** The state's own root scrolls. */
  readonly scrolls: boolean;
  /** Content laid inside a scroll region (the whole state, when it scrolls). */
  readonly scrollJsx: string;
  /** Content pinned outside every scroll region — chrome that cannot move. */
  readonly fixedJsx: string;
  /**
   * Everything the state renders, region or not. The counterfactual reads
   * this rather than the scroll region, so "take the container away" measures
   * the same copy on a tree that has one and on a tree that does not.
   */
  readonly contentJsx: string;
  /** The scroll region makes room for the keyboard, one way or the other. */
  readonly keyboardHandled: boolean;
  /** The content box centres itself, so an overflow is clipped at both ends. */
  readonly centred: boolean;
  /** A free-text field lives in the scroll region. */
  readonly typing: boolean;
  /** The body is handed to a component that renders a screen of its own. */
  readonly delegates: boolean;
}

/**
 * Split a frame-rooted state into the part that scrolls and the part that
 * cannot. Nested scroll regions are not a thing in this app (the sweep forbids
 * the virtualized case and no screen nests a plain one), so each region runs
 * from its open tag to its own closing tag.
 */
function split(jsx: string): { scrollJsx: string; fixedJsx: string; regions: string[] } {
  const regions: string[] = [];
  let fixed = "";
  let rest = jsx;
  for (;;) {
    const found = SCROLLERS.map((tag) => ({ tag, at: rest.indexOf(`<${tag}`) })).filter(
      (candidate) => candidate.at !== -1,
    );
    if (found.length === 0) {
      fixed += rest;
      break;
    }
    const first = found.reduce((a, b) => (a.at <= b.at ? a : b));
    const close = rest.indexOf(`</${first.tag}>`, first.at);
    const selfClosed = rest.slice(first.at, close === -1 ? rest.length : close);
    const end = close === -1 ? rest.length : close + `</${first.tag}>`.length;
    fixed += rest.slice(0, first.at);
    regions.push(selfClosed);
    rest = rest.slice(end);
  }
  return { scrollJsx: regions.join("\n"), fixedJsx: fixed, regions };
}

/**
 * A component that renders `{children}` is a container primitive — `Screen`,
 * `ScrollScreen`, the glass bar, the biometric gate's pass-through — not a
 * screen a patient lands on. Its own copy is whatever its caller puts in it,
 * which is checked at the caller.
 */
function passesThrough(jsx: string): boolean {
  return /\{\s*children\s*\}/.test(jsx);
}

function frameRooted(jsx: string): boolean {
  const root = rootTag(jsx);
  return root !== null && FRAMES.includes(root) && !passesThrough(jsx);
}

/**
 * Components declared in the same file that render a whole screen — the
 * intake route hands its body to `StepFlow`, which is where that screen's
 * scroll region actually lives. A small local piece (a pill, a row) is not one
 * of these: the test is whether the declaration's own returns are frame-rooted.
 */
function screenLocals(source: string): Set<string> {
  const declarations = [...source.matchAll(/^(?:export default )?function ([A-Z]\w*)\s*\(/gm)];
  const names = new Set<string>();
  declarations.forEach((declaration, index) => {
    const next = declarations[index + 1];
    const body = source.slice(declaration.index, next === undefined ? source.length : next.index);
    if (returnedJsx(body).some(frameRooted)) {
      names.add(declaration[1]);
    }
  });
  return names;
}

function surfaces(path: string): Surface[] {
  const file = named(path);
  const source = readFileSync(path, "utf8");
  const locals = screenLocals(source);
  const out: Surface[] = [];
  returnedJsx(source).forEach((jsx, index) => {
    const root = rootTag(jsx);
    if (root === null) {
      // A screen that renders nothing: no copy, so nothing to put out of
      // reach. Any other non-JSX return (a cleanup function, a value) is not
      // a screen state at all.
      if (jsx.trim() === "null") {
        out.push({
          id: `${file}#${index}`,
          file,
          root: "null",
          scrolls: false,
          scrollJsx: "",
          fixedJsx: "",
          contentJsx: "",
          keyboardHandled: true,
          centred: false,
          typing: false,
          delegates: false,
        });
      }
      return;
    }
    // A fragment root is transparent: the frame inside it is the state.
    const effective = FRAMES.includes(root) ? root : (rootTag(jsx.replace(`<${root}`, "")) ?? root);
    if (!FRAMES.includes(effective) || passesThrough(jsx)) {
      return;
    }
    const scrolls = SCROLLERS.includes(effective);
    const parts = scrolls ? { scrollJsx: jsx, fixedJsx: "", regions: [jsx] } : split(jsx);
    const tags = parts.regions.map((region) => openTag(region, rootTag(region) ?? ""));
    // Where the state's own layout style lives: on the scroll content when
    // there is a scroll region, and on the frame itself when there is not —
    // which is how the welcome screen carried `justifyContent: "center"`
    // before INT-263, and why its overflow was clipped at the top as well.
    const contentStyle =
      /contentContainerStyle=\{\[?styles\.(\w+)/.exec(parts.scrollJsx) ??
      /\bstyle=\{\[?styles\.(\w+)/.exec(openTag(jsx, effective));
    out.push({
      id: `${file}#${index}`,
      file,
      root: effective,
      scrolls,
      scrollJsx: parts.scrollJsx,
      fixedJsx: parts.fixedJsx,
      contentJsx: `${parts.scrollJsx}\n${parts.fixedJsx}`,
      keyboardHandled:
        effective === "KeyboardAvoidingView" ||
        tags.some((tag) => tag.includes("automaticallyAdjustKeyboardInsets")) ||
        // ScrollScreen sets it for every caller; the prop is on the shared
        // container rather than repeated at each site.
        tags.some((tag) => tag.startsWith("<ScrollScreen")),
      centred:
        contentStyle !== null &&
        /justifyContent:\s*"center"/.test(styleBlock(source, contentStyle[1])),
      typing: /<TextInput\b/.test(parts.scrollJsx),
      delegates: [...jsx.matchAll(/<([A-Z]\w*)/g)].some(
        (tag) => SCREEN_COMPONENTS.has(tag[1]) || locals.has(tag[1]),
      ),
    });
  });
  return out;
}

const ROUTE_FILES = walk(APP).filter((path) => {
  const file = basename(path);
  return (
    file.endsWith(".tsx") &&
    !file.includes(".test.") &&
    !file.startsWith("_") &&
    !file.startsWith("+")
  );
});

/**
 * Components that render a whole screen rather than a piece of one — the
 * intake gate, the dialogue, the biometric lock. A route that delegates its
 * body to one of these has its content there, not in the route file, so the
 * surfaces have to be collected from both or the delegating branch is checked
 * against an empty screen.
 */
const COMPONENT_FILES = walk(COMPONENTS).filter(
  (path) => path.endsWith(".tsx") && returnedJsx(readFileSync(path, "utf8")).some(frameRooted),
);

const SCREEN_COMPONENTS = new Set(COMPONENT_FILES.map((path) => basename(path, ".tsx")));

const SURFACES: readonly Surface[] = [...ROUTE_FILES, ...COMPONENT_FILES]
  .flatMap(surfaces)
  .sort((a, b) => a.id.localeCompare(b.id));

describe("§1 — the harness resolves screen states, not files", () => {
  it("finds a state for every route, and more states than there are routes", () => {
    const routeSurfaces = SURFACES.filter((s) => s.file.startsWith("src/app/"));
    const covered = new Set(routeSurfaces.map((s) => s.file));
    expect(covered.size).toBe(ROUTE_FILES.length);
    // The point of the split: branches outnumber files. A file-level reader
    // cannot see the difference between these two numbers.
    expect(routeSurfaces.length).toBeGreaterThan(ROUTE_FILES.length);
  });

  it("resolves the branchy screens branch by branch", () => {
    const otp = SURFACES.filter((s) => s.file.endsWith("(auth)/otp.tsx"));
    // The pending-phone-is-null state and the six-box form are two screens.
    expect(otp.length).toBe(2);
    const review = SURFACES.filter((s) => s.file.endsWith("review.tsx"));
    expect(review.length).toBeGreaterThanOrEqual(2);
    const intake = SURFACES.filter((s) => s.file.endsWith("intake.tsx"));
    expect(intake.length).toBeGreaterThanOrEqual(3);
  });

  it("follows the routes that delegate their whole body to a component", () => {
    const files = new Set(SURFACES.map((s) => s.file));
    expect(files).toContain("src/components/DialogueGate.tsx");
    expect(files).toContain("src/components/DialogueIntake.tsx");
    expect(files).toContain("src/components/BiometricGate.tsx");
  });

  it("reads the shipped container's own properties rather than assuming them", () => {
    const welcome = SURFACES.find((s) => s.file.endsWith("welcome.tsx"))!;
    expect(welcome.scrolls).toBe(true);
    // Read from styles.content in the route itself — this is the property that
    // made the original defect clip the TITLE and not only the footer.
    expect(welcome.centred).toBe(true);
    const phone = SURFACES.find((s) => s.file.endsWith("phone.tsx"))!;
    expect(phone.typing).toBe(true);
    expect(phone.centred).toBe(false);
  });
});

/* ------------------------------------------------------------------ */
/* §2 — the layout model                                               */
/* ------------------------------------------------------------------ */

/**
 * The reference phone, in the same coordinates as the static sweep and
 * INT-260's rail measurements: iPhone 16 Pro logical points, 402 × 874, safe
 * insets 62 top and 34 bottom. `Screen` and `ScrollScreen` are padding-free
 * frames since INT-263, so the frame IS the safe area and the screen padding
 * rides on the scroll content.
 */
const VIEWPORT = { width: 402, height: 874, insetTop: 62, insetBottom: 34 } as const;
const WINDOW = VIEWPORT.height - VIEWPORT.insetTop - VIEWPORT.insetBottom;
const PAD = spacing.screen;
const MEASURE = VIEWPORT.width - 2 * PAD;

/**
 * The software keyboard, portrait, with its accessory bar — the height of the
 * region a focused field's scroll view runs underneath. A model value: no
 * keyboard was measured in this container. It is used only to ask whether a
 * field can be scrolled clear of it, and the answer below does not turn on the
 * exact number (a scroll region without keyboard insets loses its bottom
 * keyboard-height of content whatever that height is).
 */
const KEYBOARD = 291;

/** The tightest rhythm any screen uses between blocks — the model's floor. */
const GAP = spacing.md;

/** Average glyph advance as a fraction of the size, Inter set in Turkish. */
const GLYPH_ADVANCE = 0.5;

interface Block {
  /** The catalogue key this block renders, when it renders one. */
  readonly key: MessageKey | null;
  readonly kind: "text" | "control" | "field" | "cardPadding";
  readonly height: number;
}

const TOKEN =
  /<(AppText|PrimaryButton|SecondaryButton|TextInput|Card|GlassCard)\b|role="(display|hero|title|body|label|caption|micro)"|\bt\("([^"]+)"/g;

/**
 * Strip what a patient does not read: accessibility labels and hints (spoken,
 * never laid out), and the navigation header's own options (chrome the frame
 * owns, outside the content box).
 */
function readable(jsx: string): string {
  return jsx
    .replace(/<Stack\.Screen[\s\S]*?\/>/g, "")
    .replace(/accessibility\w*=\{[^{}]*\}/g, "")
    .replace(/\bhint=\{[^{}]*\}/g, "");
}

function textHeight(text: string, role: TypeRole, scale: number): number {
  const perLine = Math.max(1, Math.floor(MEASURE / (scaledSize(role, scale) * GLYPH_ADVANCE)));
  return Math.max(1, Math.ceil(text.length / perLine)) * lineHeight(role, scale);
}

/**
 * The blocks a piece of JSX lays out, in source order.
 *
 * Controls are laid out at the geometry they ship with — a CTA is the 56 pt
 * pill or its label plus `spacing.md` top and bottom, whichever is taller; a
 * field is never shorter than `MIN_TAP`; a card contributes its own padding,
 * and the padding it contributes is the one `isLargeText` picks, so the model
 * changes form at 1.6 exactly where the app does.
 */
function blocks(jsx: string, scale: number): Block[] {
  const out: Block[] = [];
  let role: TypeRole = "body";
  let pending: "text" | "control" | "field" = "text";
  const cardPadding = 2 * (isLargeText(scale) ? spacing.md : spacing.lg);
  const controlHeight = Math.max(56, lineHeight("body", scale) + 2 * spacing.md);
  const fieldHeight = Math.max(MIN_TAP, scaledSize("body", scale) + 2 * spacing.md);
  for (const match of readable(jsx).matchAll(TOKEN)) {
    if (match[1] !== undefined) {
      if (match[1] === "AppText") {
        pending = "text";
        role = "body";
      } else if (match[1] === "TextInput") {
        pending = "field";
        out.push({ key: null, kind: "field", height: fieldHeight });
      } else if (match[1] === "Card" || match[1] === "GlassCard") {
        out.push({ key: null, kind: "cardPadding", height: cardPadding });
      } else {
        pending = "control";
        out.push({ key: null, kind: "control", height: controlHeight });
      }
      continue;
    }
    if (match[2] !== undefined) {
      role = match[2] as TypeRole;
      continue;
    }
    const key = match[3] as MessageKey;
    const text = tr[key];
    if (typeof text !== "string") {
      continue;
    }
    if (pending === "text") {
      out.push({ key, kind: "text", height: textHeight(text, role, scale) });
      continue;
    }
    // The key belongs to the control or field just pushed — a CTA's label is
    // not a line of copy under the button, it is the button.
    const last = out[out.length - 1];
    if (last !== undefined && last.key === null) {
      out[out.length - 1] = { ...last, key };
    }
    pending = "text";
  }
  return out;
}

interface Laid {
  readonly block: Block;
  readonly top: number;
  readonly bottom: number;
}

interface Conditions {
  /** The state's scroll region exists (false models the pre-INT-263 tree). */
  readonly scrolls: boolean;
  readonly centred: boolean;
  readonly keyboardUp: boolean;
  readonly keyboardHandled: boolean;
}

/**
 * Lay the blocks out and return the ones NO scroll offset can bring into the
 * viewport — the content the app did not show.
 *
 * A scroll region reaches `content - WINDOW`, and no further: the frame runs
 * under the keyboard, so unless the region takes a keyboard-sized bottom inset
 * (`automaticallyAdjustKeyboardInsets`, or a frame that resizes) the last
 * KEYBOARD points of content stay under it however far the patient drags. A
 * box that does not scroll reaches nothing, and when it centres its children
 * an overflow is clipped at the TOP as well — which is the shape of the
 * original welcome defect, where the app's own name went under the status bar.
 */
function unreachable(source: Block[], conditions: Conditions): Laid[] {
  if (source.length === 0) {
    return [];
  }
  const content =
    2 * PAD + source.reduce((total, block) => total + block.height, 0) + GAP * (source.length - 1);
  const inset = conditions.keyboardUp && conditions.keyboardHandled ? KEYBOARD : 0;
  const visible = WINDOW - (conditions.keyboardUp ? KEYBOARD : 0);
  const maxScroll = conditions.scrolls ? Math.max(0, content + inset - WINDOW) : 0;
  const shift = !conditions.scrolls && conditions.centred ? (WINDOW - content) / 2 : 0;
  const laid: Laid[] = [];
  let y = PAD + shift;
  for (const block of source) {
    laid.push({ block, top: y, bottom: y + block.height });
    y += block.height + GAP;
  }
  return laid.filter((item) => item.top < 0 || item.bottom > visible + maxScroll);
}

/** The catalogue keys a state loses under `conditions`, named. */
function lostKeys(jsx: string, scale: number, conditions: Conditions): MessageKey[] {
  return unreachable(blocks(jsx, scale), conditions)
    .map((item) => item.block.key)
    .filter((key): key is MessageKey => key !== null);
}

const shipped = (surface: Surface, over: Partial<Conditions> = {}): Conditions => ({
  scrolls: surface.scrolls || surface.scrollJsx.length > 0,
  centred: surface.centred,
  keyboardUp: false,
  keyboardHandled: surface.keyboardHandled,
  ...over,
});

const TOP = APP_STEPS[APP_STEPS.length - 1];

describe("§2 — the model measures positions, and it is not vacuous", () => {
  it("2.0 is the rung the patient can choose, and the one measured here", () => {
    expect(TOP).toBe(2.0);
  });

  it("lays out controls and card padding, not only lines of copy", () => {
    const phone = SURFACES.find((s) => s.file.endsWith("phone.tsx"))!;
    const kinds = new Set(blocks(phone.contentJsx, TOP).map((b) => b.kind));
    expect(kinds).toContain("text");
    expect(kinds).toContain("field");
    expect(kinds).toContain("control");
    expect(kinds).toContain("cardPadding");
  });

  it("a CTA's label is the button, counted once", () => {
    const welcome = SURFACES.find((s) => s.file.endsWith("welcome.tsx"))!;
    const laid = blocks(welcome.contentJsx, TOP);
    const cta = laid.filter((b) => b.key === "welcome.phoneCta");
    expect(cta).toHaveLength(1);
    expect(cta[0].kind).toBe("control");
  });

  it("the model changes form where the app does, at LARGE_TEXT_SCALE", () => {
    const jsx = SURFACES.find((s) => s.file.endsWith("phone.tsx"))!.contentJsx;
    const padding = (scale: number) =>
      blocks(jsx, scale).find((b) => b.kind === "cardPadding")!.height;
    expect(padding(1.0)).toBeGreaterThan(padding(TOP));
    expect(padding(1.3)).toBe(padding(1.0));
    expect(padding(1.6)).toBe(padding(TOP));
  });
});

/* ------------------------------------------------------------------ */
/* §3 — every state a patient lands on keeps its content reachable     */
/* ------------------------------------------------------------------ */

describe("§3 — at 2.0, every screen state renders inside a reachable container", () => {
  it.each(SURFACES.map((s) => [s.id, s] as const))("%s", (id, surface) => {
    if (surface.root === "Redirect" || surface.root === "null") {
      // Renders no content of its own — §5 checks the exemption separately.
      expect(blocks(surface.contentJsx, TOP)).toHaveLength(0);
      return;
    }
    expect(
      surface.scrolls || surface.scrollJsx.length > 0 || surface.delegates,
      `${id} is a whole screen with neither a scroll region nor a screen component to host one`,
    ).toBe(true);
    // The closing half, and it is the model's theorem rather than a second
    // observation: a region that scrolls reaches its own content, so this line
    // is what makes the line above load-bearing — the same call convicts the
    // moment `scrolls` goes false, which is precisely what §4 does on purpose.
    expect(lostKeys(surface.scrollJsx, TOP, shipped(surface)), id).toEqual([]);
  });

  it("chrome pinned outside the scroll region still fits the phone at 2.0", () => {
    // The two flow screens host a fixed bar beside their scroll region. What
    // is pinned cannot be scrolled to, so it has to fit — and this is the one
    // place where "it does not fit" would have to be answered by changing the
    // screen's FORM rather than by adding a container.
    for (const surface of SURFACES) {
      const fixed = blocks(surface.fixedJsx, TOP);
      const height = fixed.reduce((total, block) => total + block.height, 0);
      expect(
        height,
        `${surface.id} pins ${height} pt of chrome outside its scroll region`,
      ).toBeLessThanOrEqual(WINDOW);
    }
  });
});

/* ------------------------------------------------------------------ */
/* §4 — the counterfactual: what the container is worth, at 2.0        */
/* ------------------------------------------------------------------ */

describe("§4 — take the container away and name what the patient loses", () => {
  const welcome = () => SURFACES.find((s) => s.file.endsWith("(auth)/welcome.tsx"))!;

  it("welcome loses its own title at 2.0 and loses nothing at 1.0", () => {
    // The defect as it was reported: at the top rung the hero sat under the
    // status bar. A centred box clips both ends, so the FIRST block goes as
    // well as the last — which is why the sweep's total-height reading cannot
    // express this case and this one can.
    const surface = welcome();
    const bare = shipped(surface, { scrolls: false });
    expect(lostKeys(surface.contentJsx, TOP, bare)).toContain("app.name");
    expect(lostKeys(surface.contentJsx, 1.0, bare)).toEqual([]);
  });

  it("the loss is a function of the scale, and it only grows with it", () => {
    const surface = welcome();
    const bare = shipped(surface, { scrolls: false });
    const counts = APP_STEPS.map((scale) => lostKeys(surface.contentJsx, scale, bare).length);
    expect(counts[0]).toBe(0);
    expect(counts[counts.length - 1]).toBeGreaterThan(0);
    for (let index = 1; index < counts.length; index += 1) {
      expect(
        counts[index],
        `${APP_STEPS[index]} loses less than ${APP_STEPS[index - 1]}`,
      ).toBeGreaterThanOrEqual(counts[index - 1]);
    }
  });

  it("more screens lose content at 2.0 than at 1.0, and they are a superset", () => {
    const losing = (scale: number) =>
      new Set(
        SURFACES.filter(
          (s) => lostKeys(s.contentJsx, scale, shipped(s, { scrolls: false })).length > 0,
        ).map((s) => s.id),
      );
    const atDefault = losing(1.0);
    const atTop = losing(TOP);
    expect(atTop.size).toBeGreaterThan(atDefault.size);
    for (const id of atDefault) {
      expect(atTop, `${id} loses content at 1.0 but not at 2.0`).toContain(id);
    }
  });

  it("the model can convict, and does, on real screens rather than one", () => {
    const convicted = SURFACES.filter(
      (s) => lostKeys(s.contentJsx, TOP, shipped(s, { scrolls: false })).length > 0,
    );
    expect(convicted.length).toBeGreaterThanOrEqual(5);
    // Every named loss is a real catalogue string, so the failure message a
    // future regression prints is the copy the patient would not have seen.
    for (const surface of convicted) {
      for (const key of lostKeys(surface.contentJsx, TOP, shipped(surface, { scrolls: false }))) {
        expect(typeof tr[key], `${surface.id} names ${key}`).toBe("string");
      }
    }
  });
});

/* ------------------------------------------------------------------ */
/* §5 — the exemption is not a hole                                    */
/* ------------------------------------------------------------------ */

describe("§5 — the route that does not scroll still delivers its content", () => {
  const index = join(APP, "index.tsx");
  const source = readFileSync(index, "utf8");

  it("renders nothing of its own at any rung of the ladder", () => {
    for (const scale of APP_STEPS) {
      for (const surface of surfaces(index)) {
        expect(blocks(surface.contentJsx, scale), `${surface.id} at ${scale}`).toHaveLength(0);
      }
    }
  });

  it("every destination it hands the patient to is a real route", () => {
    const targets = [...source.matchAll(/<Redirect href="([^"]+)"/g)].map((m) => m[1]);
    expect(targets.length).toBeGreaterThanOrEqual(2);
    const routes = new Set(
      ROUTE_FILES.map((path) =>
        named(path)
          .replace(/^src\/app/, "")
          .replace(/\.tsx$/, "")
          .replace(/\/index$/, ""),
      ),
    );
    for (const target of targets) {
      expect(routes, `index.tsx redirects to ${target}, which is not a route`).toContain(target);
    }
  });

  it("and each destination scrolls, so the content arrives reachable", () => {
    const targets = [...source.matchAll(/<Redirect href="([^"]+)"/g)].map((m) => m[1]);
    for (const target of targets) {
      const landing = SURFACES.filter(
        (s) =>
          s.file
            .replace(/^src\/app/, "")
            .replace(/\.tsx$/, "")
            .replace(/\/index$/, "") === target,
      );
      expect(landing.length, `nothing renders ${target}`).toBeGreaterThan(0);
      for (const surface of landing) {
        expect(lostKeys(surface.scrollJsx, TOP, shipped(surface)), surface.id).toEqual([]);
      }
    }
  });
});

/* ------------------------------------------------------------------ */
/* §6 — the keyboard, at 2.0, where the field actually is              */
/* ------------------------------------------------------------------ */

describe("§6 — a field stays reachable with the keyboard up at 2.0", () => {
  const typing = SURFACES.filter((s) => s.typing);

  it("finds every state that asks the patient to type", () => {
    const files = new Set(typing.map((s) => s.file));
    expect(files).toContain("src/app/(auth)/phone.tsx");
    expect(files).toContain("src/app/(auth)/otp.tsx");
    expect(files).toContain("src/app/(tabs)/visits/new.tsx");
    expect(files).toContain("src/app/(tabs)/visits/[visitId]/intake.tsx");
  });

  it.each(typing.map((s) => [s.id, s] as const))("%s keeps its field on screen", (id, surface) => {
    // The mechanism, asserted where the field is rather than in Themed.tsx:
    // a scroll region whose frame runs under the keyboard cannot be dragged
    // past its own content, so the bottom keyboard-height is unreachable —
    // the covered-field defect, reintroduced by the container that fixed the
    // overflow. Either the region takes a keyboard inset or the frame resizes.
    expect(surface.keyboardHandled, `${id} hosts a field with no room for the keyboard`).toBe(true);
    expect(lostKeys(surface.scrollJsx, TOP, shipped(surface, { keyboardUp: true })), id).toEqual(
      [],
    );
  });

  it.each(typing.map((s) => [s.id, s] as const))(
    "%s loses content the moment that room is taken away",
    (id, surface) => {
      // The negative control, so the assertion above cannot be passing on a
      // model that has no way to fail: the same state, at the same scale,
      // with the keyboard inset taken away — which is what every one of these
      // screens looked like before the inset was declared on the region.
      const lost = unreachable(
        blocks(surface.scrollJsx, TOP),
        shipped(surface, { keyboardUp: true, keyboardHandled: false }),
      );
      expect(lost.length, `${id} would lose nothing — the inset is doing no work`).toBeGreaterThan(
        0,
      );
    },
  );

  it("on the phone screen it is the sign-in CTA that goes under the keyboard", () => {
    // Named rather than counted: without the inset the patient reaches the
    // field, types their number, and cannot reach the button that sends it.
    const phone = SURFACES.find((s) => s.file.endsWith("(auth)/phone.tsx"))!;
    expect(
      lostKeys(phone.scrollJsx, TOP, shipped(phone, { keyboardUp: true, keyboardHandled: false })),
    ).toContain("auth.phone.cta");
  });

  it("on the intake step the field itself goes under it", () => {
    // The tall case: the content already exceeds the viewport, so there is
    // plenty to scroll — and the field is still unreachable, because a region
    // that runs under the keyboard cannot be dragged past its own content.
    const step = SURFACES.find((s) => s.file.endsWith("visits/[visitId]/intake.tsx") && s.typing)!;
    const lost = unreachable(
      blocks(step.scrollJsx, TOP),
      shipped(step, { keyboardUp: true, keyboardHandled: false }),
    );
    expect(lost.some((item) => item.block.kind === "field")).toBe(true);
  });
});
