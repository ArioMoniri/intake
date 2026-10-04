/**
 * INT-492: the feature flags behind the question progress and
 * micro-interaction redesign (GitHub #839).
 *
 * The owner asked for the redesign behind a flag that is off by default, so
 * a build nobody configured shows exactly the screen it shows today. One part
 * of it, the rolling number, is beyond what ADR-033, ADR-037, ADR-038 and
 * ADR-039 allow: it is listed for the owner as "approval needed" and is
 * honoured in a development build only, so no patient build can carry it
 * before the owner says yes.
 */
import { describe, expect, it } from "vitest";

import {
  APPROVAL_NEEDED,
  FEATURE_FLAGS,
  FLAGS_OFF,
  parseFlagList,
  resolveFlags,
  type FeatureFlag,
} from "./flags";

const DEV = { dev: true } as const;
const RELEASE = { dev: false } as const;

describe("every flag is off unless a build asks for it", () => {
  it("knows exactly the two INT-492 flags", () => {
    expect([...FEATURE_FLAGS]).toEqual(["progressMicro", "progressNumberRoll"]);
  });

  it("the default is every flag off, frozen", () => {
    for (const name of FEATURE_FLAGS) {
      expect(FLAGS_OFF[name], name).toBe(false);
    }
    expect(Object.isFrozen(FLAGS_OFF)).toBe(true);
  });

  it("an unset or empty value is every flag off, in a dev and a release build", () => {
    for (const raw of [undefined, null, "", "   ", ","]) {
      expect(resolveFlags(raw, DEV), String(raw)).toEqual(FLAGS_OFF);
      expect(resolveFlags(raw, RELEASE), String(raw)).toEqual(FLAGS_OFF);
    }
  });

  it("a value that is not a string is every flag off, never a guess", () => {
    for (const raw of [1, true, ["progressMicro"], { progressMicro: true }]) {
      expect(resolveFlags(raw, DEV)).toEqual(FLAGS_OFF);
    }
  });
});

describe("a build turns a flag on by its exact name", () => {
  it("progressMicro turns the within-bounds redesign on in any build", () => {
    expect(resolveFlags("progressMicro", DEV).progressMicro).toBe(true);
    expect(resolveFlags("progressMicro", RELEASE).progressMicro).toBe(true);
    expect(resolveFlags(" progressMicro , ", RELEASE).progressMicro).toBe(true);
  });

  it("near misses stay off: another spelling, a prefix, a negation", () => {
    for (const raw of ["progressmicro", "progress_micro", "progressMicr", "!progressMicro"]) {
      expect(resolveFlags(raw, DEV), raw).toEqual(FLAGS_OFF);
    }
  });

  it("an unknown name is ignored and does not switch a known one", () => {
    expect(parseFlagList("orbV2,progressMicro,nope")).toEqual(["progressMicro"]);
    expect(resolveFlags("orbV2", DEV)).toEqual(FLAGS_OFF);
  });
});

describe("approval-needed flags never reach a patient build", () => {
  it("only the number roll is beyond the ratified ADRs", () => {
    const needed = FEATURE_FLAGS.filter((name) => APPROVAL_NEEDED[name]);
    expect(needed).toEqual<FeatureFlag[]>(["progressNumberRoll"]);
  });

  it("the roll is honoured in a development build, on top of the redesign", () => {
    const flags = resolveFlags("progressMicro,progressNumberRoll", DEV);
    expect(flags).toEqual({ progressMicro: true, progressNumberRoll: true });
  });

  it("near miss: the same value in a release build drops the roll and keeps the rest", () => {
    const flags = resolveFlags("progressMicro,progressNumberRoll", RELEASE);
    expect(flags).toEqual({ progressMicro: true, progressNumberRoll: false });
  });

  it("the roll refines the capsule, so it is off without progressMicro", () => {
    expect(resolveFlags("progressNumberRoll", DEV)).toEqual(FLAGS_OFF);
  });
});
