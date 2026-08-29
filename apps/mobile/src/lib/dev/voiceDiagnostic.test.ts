/**
 * INT-246 — the dev-only fallback banner, as a pure decision.
 *
 * DialogueGate's docstring argues the silence is right FOR PATIENTS: nothing
 * was attempted yet, so there is nothing to apologise for. That argument is
 * about production and it stands. It says nothing about the engineer holding
 * the phone, who in the incident could not tell a dead SSH tunnel from an
 * unbuilt feature.
 *
 * So the banner is a `__DEV__` affordance and the gate lives HERE, in a pure
 * function, where a test can hold it: with `isDev` false the function returns
 * null and there is nothing for a component to render. That is the production
 * silence, pinned.
 */
import { afterEach, describe, expect, it } from "vitest";

import { setLocale } from "@/lib/i18n";
import { en } from "@/lib/i18n/en";
import { tr } from "@/lib/i18n/tr";

import type { ReachabilityReport } from "./hosts";
import { voiceDiagnostic } from "./voiceDiagnostic";

afterEach(() => setLocale("tr"));

const DOWN: ReachabilityReport = {
  base: null,
  probes: [
    { base: "http://127.0.0.1:8802", failure: { kind: "refused" } },
    { base: "http://172.20.10.3:8802", failure: { kind: "timeout", timeoutMs: 1500 } },
    { base: "http://10.0.0.9:8802", failure: { kind: "status", status: 503 } },
  ],
};

const UP: ReachabilityReport = {
  base: "http://127.0.0.1:8802",
  probes: [{ base: "http://127.0.0.1:8802", failure: null }],
};

describe("production silence is preserved", () => {
  it("returns null when __DEV__ is false, however dead the lane is", () => {
    expect(voiceDiagnostic(DOWN, false)).toBeNull();
  });

  it("returns null for every report shape when __DEV__ is false", () => {
    expect(voiceDiagnostic(UP, false)).toBeNull();
    expect(voiceDiagnostic(null, false)).toBeNull();
    expect(voiceDiagnostic({ base: null, probes: [] }, false)).toBeNull();
  });
});

describe("in dev it stays quiet unless there is something to say", () => {
  it("says nothing while the probe is still in flight", () => {
    expect(voiceDiagnostic(null, true)).toBeNull();
  });

  it("says nothing when a lane answered — a working voice needs no banner", () => {
    expect(voiceDiagnostic(UP, true)).toBeNull();
  });
});

describe("in dev, a dead lane names every base it tried", () => {
  it("lists one line per candidate, in probe order", () => {
    const diagnostic = voiceDiagnostic(DOWN, true);
    expect(diagnostic).not.toBeNull();
    expect(diagnostic!.lines).toHaveLength(3);
    expect(diagnostic!.lines[0]).toContain("http://127.0.0.1:8802");
    expect(diagnostic!.lines[1]).toContain("http://172.20.10.3:8802");
    expect(diagnostic!.lines[2]).toContain("http://10.0.0.9:8802");
  });

  it("says HOW each one failed — refused, timed out, or a status", () => {
    const lines = voiceDiagnostic(DOWN, true)!.lines;
    expect(lines[0]).toContain(tr["devVoice.reason.refused"]);
    expect(lines[1]).toContain(tr["devVoice.reason.timeout"]);
    expect(lines[2]).toContain(tr["devVoice.reason.status"]);
    expect(lines[2]).toContain("503");
    // the three reasons are distinguishable, which is the whole point
    expect(new Set(lines.map((l) => l.split(" — ")[1])).size).toBe(3);
  });

  it("points at the one command that answers 'is voice up?'", () => {
    expect(voiceDiagnostic(DOWN, true)!.hint).toContain("make voice-doctor");
  });

  it("says so plainly when no candidate was configured at all", () => {
    const diagnostic = voiceDiagnostic({ base: null, probes: [] }, true);
    expect(diagnostic!.lines).toEqual([tr["devVoice.noCandidates"]]);
  });

  it("never claims voice is ready — it states the fallback", () => {
    const diagnostic = voiceDiagnostic(DOWN, true)!;
    expect(diagnostic.title).toBe(tr["devVoice.title"]);
    expect(diagnostic.body).toBe(tr["devVoice.body"]);
  });
});

describe("invariant 5 — the strings come from the catalogue, tr first", () => {
  it("renders from tr by default and mirrors into en", () => {
    expect(voiceDiagnostic(DOWN, true)!.title).toBe(tr["devVoice.title"]);
    setLocale("en");
    expect(voiceDiagnostic(DOWN, true)!.title).toBe(en["devVoice.title"]);
  });

  it("every dev-banner key exists in both catalogues", () => {
    for (const key of [
      "devVoice.title",
      "devVoice.body",
      "devVoice.hint",
      "devVoice.noCandidates",
      "devVoice.reason.timeout",
      "devVoice.reason.refused",
      "devVoice.reason.status",
    ] as const) {
      expect(tr[key].length, key).toBeGreaterThan(0);
      expect(en[key].length, key).toBeGreaterThan(0);
    }
  });
});
