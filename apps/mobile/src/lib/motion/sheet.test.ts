/**
 * ADR-038 A3: the in-tree detent sheet (INT-473).
 *
 * Two detents, medium (half the frame) and large (just under the screen's
 * own bar, because an in-tree sheet lives below the native header). A drag
 * follows the finger; a release settles to the detent the throw points at,
 * or dismisses past the threshold. Presenting and settling use A1's
 * critically damped spring, so nothing overshoots.
 *
 * - A patient's dismissal settles with the same spring.
 * - A privacy close and a RED close are instant, at every setting: RED never
 *   waits for a sheet.
 * - Reduce Motion: the sheet appears with the 120 ms fade, closes at once,
 *   and a release snaps to its detent without a spring.
 */
import { describe, expect, it } from "vitest";

import { BUBBLE_SPRING } from "./bubbles";
import {
  SHEET_LARGE_GAP,
  SHEET_SPRING,
  detentOffsets,
  isTap,
  nextDetent,
  settleTarget,
  sheetClose,
  sheetMount,
  sheetPresent,
  sheetSettle,
  type SheetCloseReason,
  type SheetMount,
} from "./sheet";

const FRAME = { height: 800, top: 100 } as const;

describe("detents", () => {
  it("medium is half the frame; large sits just under the screen's own bar", () => {
    const offsets = detentOffsets(FRAME);
    expect(offsets.medium).toBe(400);
    expect(offsets.large).toBe(FRAME.top + SHEET_LARGE_GAP);
    expect(offsets.large).toBeLessThan(offsets.medium);
  });

  it("large never sits below medium, however tall the bar", () => {
    const offsets = detentOffsets({ height: 300, top: 260 });
    expect(offsets.large).toBeLessThanOrEqual(offsets.medium);
  });
});

describe("settleTarget: where a release goes", () => {
  const offsets = detentOffsets(FRAME);

  it("a still release goes to the nearer detent", () => {
    expect(settleTarget({ offsets, height: FRAME.height, y: 380, velocity: 0 })).toBe("medium");
    expect(settleTarget({ offsets, height: FRAME.height, y: 150, velocity: 0 })).toBe("large");
  });

  it("a throw is followed: upward from medium reaches large, downward from large reaches medium", () => {
    expect(settleTarget({ offsets, height: FRAME.height, y: 390, velocity: -2 })).toBe("large");
    expect(settleTarget({ offsets, height: FRAME.height, y: 130, velocity: 2 })).toBe("medium");
  });

  it("past the dismiss threshold the sheet closes", () => {
    expect(settleTarget({ offsets, height: FRAME.height, y: 650, velocity: 0 })).toBe("closed");
    expect(settleTarget({ offsets, height: FRAME.height, y: 500, velocity: 3 })).toBe("closed");
  });

  it("near miss: a small pull below medium snaps back rather than closing", () => {
    expect(settleTarget({ offsets, height: FRAME.height, y: 450, velocity: 0 })).toBe("medium");
  });
});

describe("motion (ADR-038 A3)", () => {
  it("the spring is A1's critically damped spring, which cannot overshoot", () => {
    expect(SHEET_SPRING).toEqual(BUBBLE_SPRING);
    expect(SHEET_SPRING.overshootClamping).toBe(true);
    const zeta = SHEET_SPRING.damping / (2 * Math.sqrt(SHEET_SPRING.stiffness * SHEET_SPRING.mass));
    expect(zeta).toBeGreaterThanOrEqual(1);
  });

  it("presents on the spring, or with the 120 ms fade under Reduce Motion", () => {
    expect(sheetPresent({ reduce: false })).toEqual({ kind: "spring", spring: SHEET_SPRING });
    const reduced = sheetPresent({ reduce: true });
    expect(reduced.kind).toBe("fade");
    expect(reduced.kind === "fade" ? reduced.fade.durationMs : -1).toBe(120);
  });

  it("settles on the spring, or snaps under Reduce Motion", () => {
    expect(sheetSettle({ reduce: false })).toBe("spring");
    expect(sheetSettle({ reduce: true })).toBe("snap");
  });

  it("a patient's dismissal settles with the spring; under Reduce Motion it is instant", () => {
    expect(sheetClose("patient", { reduce: false })).toBe("spring");
    expect(sheetClose("patient", { reduce: true })).toBe("instant");
  });

  it("a privacy close and a RED close are instant at every setting", () => {
    for (const reduce of [false, true]) {
      expect(sheetClose("privacy", { reduce })).toBe("instant");
      expect(sheetClose("red", { reduce })).toBe("instant");
    }
  });
});

/*
 * INT-551 (the RED-UI review of #842, item 1). Reanimated reads a view's exit
 * animation when the view mounts or updates (AnimatedComponent's
 * componentDidMount and componentDidUpdate), never when it unmounts, so an
 * unmount plays the exit the commit before it registered. The open sheet
 * registers the patient's spring, and a RED arrives in the same render that
 * hides the sheet: unmounting there played the spring under the RED.
 */
type Close = "spring" | "instant";
type MountRule = (drawn: SheetMount, input: { visible: boolean; close: Close }) => SheetMount;

interface SheetProps {
  readonly visible: boolean;
  readonly reason: SheetCloseReason;
  readonly reduce?: boolean;
}

/**
 * The commits DetentSheet makes for a sequence of prop changes, and the exit
 * each unmount plays. Every mounted commit registers its close's exit
 * (`sheetExiting(sheetClose(closeReason, …))`). A layout effect stores what
 * each commit drew, and a change renders the sheet once more.
 */
function commits(props: readonly SheetProps[], rule: MountRule = sheetMount) {
  let drawn: SheetMount = "closed";
  let registered: Close | null = null;
  const trace: SheetMount[] = [];
  const played: Close[] = [];
  for (const { visible, reason, reduce = false } of props) {
    const close = sheetClose(reason, { reduce });
    for (;;) {
      const mount = rule(drawn, { visible, close });
      if (mount === "closed" && registered !== null) {
        played.push(registered);
      }
      registered = mount === "closed" ? null : close;
      if (mount === drawn) {
        break;
      }
      trace.push(mount);
      drawn = mount;
    }
  }
  return { trace, played };
}

/** The rule before INT-551: the commit that closes the sheet unmounts it. */
const unmountAtOnce: MountRule = (_drawn, { visible }) => (visible ? "open" : "closed");

const OPEN: SheetProps = { visible: true, reason: "patient" };

describe("an instant close leaves no exit to play (INT-551)", () => {
  it("defect, as the review found it: unmounting in the closing commit plays the patient's spring under a RED", () => {
    const red = commits([OPEN, { visible: false, reason: "red" }], unmountAtOnce);
    expect(red.played).toEqual(["spring"]);
  });

  it("a RED or privacy close keeps the sheet one commit, with no exit, then unmounts it", () => {
    for (const reason of ["red", "privacy"] as const) {
      for (const reduce of [false, true]) {
        const run = commits([
          { ...OPEN, reduce },
          { visible: false, reason, reduce },
        ]);
        expect(run.trace, `${reason} ${reduce}`).toEqual(["open", "parked", "closed"]);
        expect(run.played, `${reason} ${reduce}`).toEqual(["instant"]);
      }
    }
  });

  it("near miss: the patient's own close unmounts at once and falls away on the spring", () => {
    const run = commits([OPEN, { visible: false, reason: "patient" }]);
    expect(run.trace).toEqual(["open", "closed"]);
    expect(run.played).toEqual(["spring"]);
  });

  it("under Reduce Motion the patient's close is instant too, and plays nothing", () => {
    const run = commits([
      { ...OPEN, reduce: true },
      { visible: false, reason: "patient", reduce: true },
    ]);
    expect(run.played).toEqual(["instant"]);
  });

  it("parks only a sheet that was open, and a sheet shown again while parked is open", () => {
    expect(sheetMount("closed", { visible: false, close: "instant" })).toBe("closed");
    expect(sheetMount("parked", { visible: false, close: "instant" })).toBe("closed");
    expect(sheetMount("open", { visible: false, close: "instant" })).toBe("parked");
    expect(sheetMount("open", { visible: false, close: "spring" })).toBe("closed");
    for (const drawn of ["closed", "parked", "open"] as const) {
      for (const close of ["spring", "instant"] as const) {
        expect(sheetMount(drawn, { visible: true, close })).toBe("open");
      }
    }
  });
});

describe("the single-pointer alternative to the drag (SC 2.5.7)", () => {
  it("a tap on the grabber moves to the other detent", () => {
    expect(nextDetent("medium")).toBe("large");
    expect(nextDetent("large")).toBe("medium");
  });

  it("a release that barely moved is a tap; a drag is not", () => {
    expect(isTap({ dx: 1, dy: 2 })).toBe(true);
    expect(isTap({ dx: 0, dy: 12 })).toBe(false);
    expect(isTap({ dx: 12, dy: 0 })).toBe(false);
  });
});
