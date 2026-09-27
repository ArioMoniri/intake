/**
 * INT-409 · no build pins "today".
 *
 * Acceptance (verbatim): "a test fails if any source under `apps/mobile/src`
 * (outside tests and fixtures) pins a calendar date constant used as 'now',
 * with a near-miss control".
 *
 * Found by INT-179's close-out: Vizitlerim read "today" from a module constant
 * in every build, release included, so the upcoming/past split, the calendar's
 * today marker and its opening month were wrong for every real patient.
 *
 * The rule is read off the TypeScript syntax tree, not off text, so a date in a
 * comment or a visit's own `date:` field is never mistaken for a pinned now.
 * A *pinned date* is a literal: an ISO day string, `new Date(…)`, `Date.UTC(…)`
 * or `Date.parse(…)` over constants only, or an arrow returning one, or a
 * const bound to one. It is *used as now* when it lands in a slot named for the
 * current moment (a word `today`, `now` or `clock` in a variable, property,
 * JSX attribute, parameter default or assignment target), or is passed to a
 * function in the tree at a parameter so named (`splitVisits(visits, todayIso)`
 * and the calendar helpers). Test files are out of scope: a test injects a
 * fixed clock by design. The synthetic seed needs no exclusion, because its
 * dates are visit and record dates, never "now".
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import ts from "typescript";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..", "src");

const NOW_WORDS = new Set(["today", "now", "clock"]);
const ISO_DAY = /^\d{4}-\d{2}-\d{2}/;

/** `TODAY_FIXTURE` → today, fixture; `nowIso` → now, iso; `unknown` → unknown. */
function words(name: string): string[] {
  return name.split(/_|(?<=[a-z0-9])(?=[A-Z])/).map((word) => word.toLowerCase());
}

function isNowName(name: string): boolean {
  return words(name).some((word) => NOW_WORDS.has(word));
}

function unwrap(node: ts.Expression): ts.Expression {
  let current = node;
  while (
    ts.isParenthesizedExpression(current) ||
    ts.isAsExpression(current) ||
    ts.isSatisfiesExpression(current) ||
    ts.isNonNullExpression(current) ||
    ts.isTypeAssertionExpression(current)
  ) {
    current = current.expression;
  }
  return current;
}

function isDateMember(node: ts.Expression, member: string): boolean {
  return (
    ts.isPropertyAccessExpression(node) &&
    ts.isIdentifier(node.expression) &&
    node.expression.text === "Date" &&
    node.name.text === member
  );
}

/** A value fixed when the source is written: a literal, or a date built only from literals. */
function isConstant(node: ts.Expression): boolean {
  const value = unwrap(node);
  if (ts.isStringLiteral(value) || ts.isNoSubstitutionTemplateLiteral(value)) {
    return true;
  }
  if (ts.isNumericLiteral(value)) {
    return true;
  }
  if (ts.isPrefixUnaryExpression(value) && ts.isNumericLiteral(value.operand)) {
    return true;
  }
  return isDateLiteral(value);
}

/** A calendar date written into the source. */
function isDateLiteral(node: ts.Expression): boolean {
  const value = unwrap(node);
  if (ts.isStringLiteral(value) || ts.isNoSubstitutionTemplateLiteral(value)) {
    return ISO_DAY.test(value.text);
  }
  if (ts.isNewExpression(value) && ts.isIdentifier(value.expression)) {
    const args = value.arguments ?? [];
    return value.expression.text === "Date" && args.length > 0 && args.every(isConstant);
  }
  if (
    ts.isCallExpression(value) &&
    (isDateMember(value.expression, "UTC") || isDateMember(value.expression, "parse"))
  ) {
    return value.arguments.length > 0 && value.arguments.every(isConstant);
  }
  return false;
}

const LOGICAL = new Set<ts.SyntaxKind>([
  ts.SyntaxKind.AmpersandAmpersandToken,
  ts.SyntaxKind.BarBarToken,
  ts.SyntaxKind.QuestionQuestionToken,
]);

/**
 * Whether evaluating `node` can hand back a date written into the source:
 * the literal itself, a const bound to one, either branch of `?:`, `&&`,
 * `||` or `??`, or the body of an arrow (a clock that always answers it).
 */
function yieldsPinnedDate(
  node: ts.Expression | undefined,
  dateConstants: ReadonlySet<string>,
): boolean {
  if (node === undefined) {
    return false;
  }
  const value = unwrap(node);
  if (isDateLiteral(value)) {
    return true;
  }
  if (ts.isIdentifier(value)) {
    return dateConstants.has(value.text);
  }
  if (ts.isConditionalExpression(value)) {
    return (
      yieldsPinnedDate(value.whenTrue, dateConstants) ||
      yieldsPinnedDate(value.whenFalse, dateConstants)
    );
  }
  if (ts.isBinaryExpression(value) && LOGICAL.has(value.operatorToken.kind)) {
    return (
      yieldsPinnedDate(value.left, dateConstants) || yieldsPinnedDate(value.right, dateConstants)
    );
  }
  if (ts.isArrowFunction(value) && !ts.isBlock(value.body)) {
    return yieldsPinnedDate(value.body, dateConstants);
  }
  return false;
}

/** For every function declared in the tree: the indices of its now-named parameters. */
type NowParameters = ReadonlyMap<string, readonly number[]>;

function parse(path: string, text: string): ts.SourceFile {
  const kind = path.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  return ts.createSourceFile(path, text, ts.ScriptTarget.Latest, true, kind);
}

function visit(node: ts.Node, each: (node: ts.Node) => void): void {
  each(node);
  ts.forEachChild(node, (child) => visit(child, each));
}

function nowParameterIndices(parameters: ts.NodeArray<ts.ParameterDeclaration>): number[] {
  return parameters.flatMap((parameter, index) =>
    ts.isIdentifier(parameter.name) && isNowName(parameter.name.text) ? [index] : [],
  );
}

function collectNowParameters(files: readonly ts.SourceFile[]): NowParameters {
  const found = new Map<string, number[]>();
  for (const file of files) {
    visit(file, (node) => {
      if (ts.isFunctionDeclaration(node) && node.name !== undefined) {
        const indices = nowParameterIndices(node.parameters);
        if (indices.length > 0) {
          found.set(node.name.text, indices);
        }
      }
      if (
        ts.isVariableDeclaration(node) &&
        ts.isIdentifier(node.name) &&
        node.initializer !== undefined &&
        (ts.isArrowFunction(node.initializer) || ts.isFunctionExpression(node.initializer))
      ) {
        const indices = nowParameterIndices(node.initializer.parameters);
        if (indices.length > 0) {
          found.set(node.name.text, indices);
        }
      }
    });
  }
  return found;
}

function slotName(name: ts.Node): string | null {
  if (ts.isIdentifier(name) || ts.isStringLiteral(name) || ts.isPrivateIdentifier(name)) {
    return name.text;
  }
  return null;
}

function calleeName(callee: ts.Expression): string | null {
  if (ts.isIdentifier(callee)) {
    return callee.text;
  }
  if (ts.isPropertyAccessExpression(callee)) {
    return callee.name.text;
  }
  return null;
}

/** Every place in one file where a date written into the source is used as "now". */
function pinnedNow(file: ts.SourceFile, nowParameters: NowParameters): string[] {
  // in source order, so `const A = "…"; const B = A;` makes both constants
  const dateConstants = new Set<string>();
  visit(file, (node) => {
    if (
      ts.isVariableDeclaration(node) &&
      ts.isIdentifier(node.name) &&
      yieldsPinnedDate(node.initializer, dateConstants)
    ) {
      dateConstants.add(node.name.text);
    }
  });

  const pinned = (value: ts.Expression | undefined): boolean =>
    yieldsPinnedDate(value, dateConstants);

  const findings: string[] = [];
  const report = (node: ts.Node): void => {
    const { line } = file.getLineAndCharacterOfPosition(node.getStart(file));
    findings.push(`${file.fileName}:${line + 1} ${node.getText(file).split("\n")[0]}`);
  };
  const slot = (name: ts.Node, value: ts.Expression | undefined, node: ts.Node): void => {
    const text = slotName(name);
    if (text !== null && isNowName(text) && pinned(value)) {
      report(node);
    }
  };

  visit(file, (node) => {
    if (ts.isVariableDeclaration(node) || ts.isBindingElement(node) || ts.isParameter(node)) {
      slot(node.name, node.initializer, node);
    } else if (ts.isPropertyAssignment(node)) {
      slot(node.name, node.initializer, node);
    } else if (ts.isPropertyDeclaration(node)) {
      slot(node.name, node.initializer, node);
    } else if (ts.isJsxAttribute(node) && node.initializer !== undefined) {
      const value = ts.isJsxExpression(node.initializer)
        ? node.initializer.expression
        : node.initializer;
      slot(node.name, value, node);
    } else if (
      ts.isBinaryExpression(node) &&
      node.operatorToken.kind === ts.SyntaxKind.EqualsToken
    ) {
      const target = ts.isPropertyAccessExpression(node.left) ? node.left.name : node.left;
      slot(target, node.right, node);
    } else if (ts.isCallExpression(node)) {
      const name = calleeName(node.expression);
      const indices = name === null ? undefined : nowParameters.get(name);
      if (indices !== undefined && indices.some((index) => pinned(node.arguments[index]))) {
        report(node);
      }
    }
  });
  return findings;
}

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

/** Every shipped source file: .ts/.tsx under src, tests excluded. */
const shipped = walk(SRC)
  .filter((path) => /\.tsx?$/.test(path) && !/\.test\.tsx?$/.test(path))
  .map((path) => parse(relative(SRC, path), readFileSync(path, "utf8")));

const treeNowParameters = collectNowParameters(shipped);

/** Runs one synthetic module through the same rule, against the tree's own functions. */
function scan(source: string, path = "app/(tabs)/planted.tsx"): string[] {
  return pinnedNow(parse(path, source), treeNowParameters);
}

describe("no source under src pins a calendar date used as now (INT-409)", () => {
  it("the shipped tree has none", () => {
    expect(shipped.flatMap((file) => pinnedNow(file, treeNowParameters))).toEqual([]);
  });

  it("the scan reaches the screens and the helpers it must judge", () => {
    const names = shipped.map((file) => file.fileName);
    expect(names).toContain(join("app", "(tabs)", "visits", "index.tsx"));
    expect(names).toContain(join("app", "(tabs)", "records.tsx"));
    expect(names.some((name) => name.endsWith(".test.ts"))).toBe(false);
    // derived, not listed: an empty map would let every call through
    for (const helper of [
      "splitVisits",
      "pastVisitsRecentFirst",
      "initialMonth",
      "initialSelectedDay",
      "buildCalendarGrid",
      "pickUploadVisit",
      "todayIso",
    ]) {
      expect(treeNowParameters.has(helper), helper).toBe(true);
    }
  });
});

describe("controls: each way to pin today fails", () => {
  it("a module constant named for today (the INT-179 finding's shape)", () => {
    expect(scan('const TODAY_FIXTURE = "2026-08-27";')).toHaveLength(1);
  });

  it("an innocently named constant handed to a today parameter", () => {
    const source = 'const OPENING = "2026-08-27";\nsplitVisits(visits, OPENING);';
    expect(scan(source)).toEqual(["app/(tabs)/planted.tsx:2 splitVisits(visits, OPENING)"]);
  });

  it("a literal handed straight to a calendar helper", () => {
    expect(scan('initialMonth(visits, "2026-08-27");')).toHaveLength(1);
  });

  it("a JSX today attribute", () => {
    expect(scan('const view = <VisitCalendar todayIso={"2026-08-27"} />;')).toHaveLength(1);
    expect(scan('const view = <VisitCalendar todayIso="2026-08-27" />;')).toHaveLength(1);
  });

  it("a clock that always answers the same instant", () => {
    expect(scan('const clock = () => new Date("2026-08-27T09:00:00Z");')).toHaveLength(1);
    expect(scan("const now = new Date(2026, 7, 27);")).toHaveLength(1);
    expect(scan("const now = new Date(Date.UTC(2026, 7, 27));")).toHaveLength(1);
  });

  it("a pinned date behind a fallback, a condition or a short-circuit", () => {
    expect(scan('const today = override ?? "2026-08-27";')).toHaveLength(1);
    expect(scan('const today = __DEV__ ? "2026-08-27" : todayIso(clock);')).toHaveLength(1);
    expect(scan('const today = todayIso(clock) && "2026-08-27";')).toHaveLength(1);
  });

  it("a pinned default for an injected clock or a today field", () => {
    expect(scan('function Screen({ clock = () => new Date("2026-08-27") }) {}')).toHaveLength(1);
    expect(scan('const state = { todayIso: "2026-08-27" };')).toHaveLength(1);
    expect(scan('model.today = "2026-08-27";')).toHaveLength(1);
  });
});

describe("near misses: dates that are not now pass", () => {
  it("today read from the injected clock", () => {
    expect(scan("const today = todayIso(clock);\nsplitVisits(visits, today);")).toEqual([]);
  });

  it("a today computed at run time, even from Date.UTC or behind a fallback", () => {
    expect(scan("const today = new Date(Date.UTC(year, month, day));")).toEqual([]);
    expect(scan("const today = visit.date ?? todayIso(clock);")).toEqual([]);
  });

  it("a fixed anchor that is not now (the weekday-header Monday)", () => {
    expect(scan("const WEEK_ANCHOR = Date.UTC(2024, 0, 1);\nheaders(WEEK_ANCHOR);")).toEqual([]);
  });

  it("a bound on another date, handed to a function with no today parameter", () => {
    expect(scan('const EARLIEST = "1900-01-01";\nvalidate(birthDate, EARLIEST);')).toEqual([]);
  });

  it("a visit's own date and a date in a comment", () => {
    expect(scan('const visit = { id: "v-1", date: "2026-09-03" };')).toEqual([]);
    expect(scan('// today was pinned to "2026-08-27" here\nconst x = 1;')).toEqual([]);
  });

  it("a name that only contains the letters of now", () => {
    expect(scan('const unknownDate = "2026-08-27";\nconst known = "2026-08-27";')).toEqual([]);
  });
});

describe("Vizitlerim and the records screen read today from the clock", () => {
  const read = (...segments: string[]) => readFileSync(join(SRC, ...segments), "utf8");

  it("the visits screen takes an injectable clock that defaults to the device", () => {
    const screen = read("app", "(tabs)", "visits", "index.tsx");
    expect(screen).toMatch(/export default function Visits\(\{ clock = deviceClock \}/);
    expect(screen).toContain("const today = todayIso(clock);");
    for (const call of [
      "initialMonth(visits, today)",
      "initialSelectedDay(visits, today)",
      "splitVisits(visits, today)",
      "pastVisitsRecentFirst(visits, today)",
      "todayIso={today}",
    ]) {
      expect(screen, call).toContain(call);
    }
  });

  it("the records screen picks its upload visit on the same day", () => {
    const records = read("app", "(tabs)", "records.tsx");
    expect(records).toContain("pickUploadVisit(visits, todayIso(deviceClock))");
    expect(records).not.toContain("toISOString().slice(0, 10)");
  });
});
