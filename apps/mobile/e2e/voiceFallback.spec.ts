/**
 * INT-246 acceptance — properties of the REPOSITORY, not of one function.
 *
 * The behaviour lives in src/lib/dev/hosts.test.ts (what the probe reports)
 * and src/lib/dev/voiceDiagnostic.test.ts (what the banner decides). What
 * only a source scan can prove is the wiring: that the banner's `__DEV__`
 * gate is the real `__DEV__` and not a literal someone flipped while
 * debugging; that the patient path still falls through quietly; that nothing
 * here retries a dead host; and that no dev string leaked into a
 * patient-facing screen.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const MOBILE = join(__dirname, "..");
const REPO = join(MOBILE, "..", "..");

const read = (...segments: string[]) => readFileSync(join(...segments), "utf8");
const stripComments = (source: string) =>
  source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");

const GATE = read(MOBILE, "src", "components", "DialogueGate.tsx");
const BANNER = read(MOBILE, "src", "components", "DevVoiceBanner.tsx");
const INTAKE = read(MOBILE, "src", "app", "(tabs)", "visits", "[visitId]", "intake.tsx");
const DIAGNOSTIC = read(MOBILE, "src", "lib", "dev", "voiceDiagnostic.ts");

describe("the banner is unreachable in production", () => {
  it("passes the real __DEV__ into the gate, never a literal", () => {
    const code = stripComments(BANNER);
    expect(code).toContain("voiceDiagnostic(report, __DEV__)");
    expect(code).not.toMatch(/voiceDiagnostic\([^)]*,\s*(true|false)\s*\)/);
  });

  it("renders nothing at all when the diagnostic declines", () => {
    expect(stripComments(BANNER)).toMatch(/=== null[\s\S]{0,80}return null/);
  });

  it("is mounted from the intake screen only", () => {
    expect(INTAKE).toContain("<DevVoiceBanner");
    // one mount point: a second would be a second thing to keep dev-only
    expect(INTAKE.match(/<DevVoiceBanner/g)).toHaveLength(1);
  });

  it("keeps its decision in a pure module — no react-native import to smuggle it", () => {
    expect(DIAGNOSTIC).not.toContain('from "react-native"');
    expect(DIAGNOSTIC).not.toContain('from "react"');
  });
});

describe("the patient path is unchanged", () => {
  it("an unreachable lane still dispatches voice_unavailable, as before", () => {
    expect(stripComments(GATE)).toContain('{ type: "voice_unavailable" }');
    expect(stripComments(GATE)).toContain('{ type: "voice_ready" }');
  });

  it("the gate still shows only the probe beat and the typed door", () => {
    // No banner rendered from the gate: it unmounts the instant the fallback
    // fires, and a notice that flashes for one frame helps nobody. (Its
    // docstring may NAME the banner — that is how the reasoning stays here.)
    expect(stripComments(GATE)).not.toContain("<DevVoiceBanner");
    expect(GATE).toContain('t("voiceFirst.typeInstead")');
  });

  it("the gate's docstring still states why the patient sees no notice", () => {
    // wrapped across lines in the source, so match across the leading " * "
    expect(GATE).toMatch(/without a[\s*]+failure notice/);
  });
});

describe("nothing hammers a dead host", () => {
  it("the gate has no timer, interval or retry of its own", () => {
    const code = stripComments(GATE);
    expect(code).not.toMatch(/setInterval|setTimeout|retry|attempt\s*\+\+/);
  });

  it("the banner never probes — it renders a report someone else took", () => {
    const code = stripComments(BANNER);
    expect(code).not.toMatch(/probeAsrReachability|reachableAsrBaseUrl|fetch\(/);
  });
});

describe("invariant 5 — dev strings are catalogued and stay in the dev lane", () => {
  it("no devVoice key is used by a patient-facing screen", () => {
    const patientFacing = [
      ["src", "app", "(tabs)", "visits", "[visitId]", "intake.tsx"],
      ["src", "components", "DialogueGate.tsx"],
      ["src", "components", "DialogueIntake.tsx"],
    ];
    for (const segments of patientFacing) {
      expect(read(MOBILE, ...segments), segments.join("/")).not.toContain('t("devVoice.');
    }
  });
});

describe("the host-side answer to 'is voice up?'", () => {
  it("make voice-doctor exists as a target", () => {
    const makefile = read(REPO, "Makefile");
    expect(makefile).toMatch(/^voice-doctor:/m);
    expect(makefile).toMatch(/^\.PHONY:.*\bvoice-doctor\b/m);
  });

  it("the banner names that command rather than describing a procedure", () => {
    expect(read(MOBILE, "src", "lib", "i18n", "tr.ts")).toContain("make voice-doctor");
  });
});
