/**
 * INT-450 — the chart primitives and the figure reader they stand on.
 *
 * Properties, each with its near-miss: a mark is drawn only for a figure the
 * page prints (an unknown or malformed one draws nothing — invariant 17 and
 * 22); a stale reading is hatched and named; the chart is one named image; no
 * `style` attribute reaches the markup (the CSP has no `unsafe-inline`).
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { BarList, Gauge, toneOf, type BarRow } from "./charts";
import { figureOf, percentOf, ratioOf, sharesOf } from "./figure";

const NB = " ";
const c = { unknown: "Unknown", stale: "stale" };

function bars(rows: BarRow[], id = "lane-requests"): string {
  return renderToStaticMarkup(<BarList id={id} title="Requests" rows={rows} c={c} />);
}

describe("figureOf reads back the printed figure", () => {
  it("parses a number and its no-break-space unit", () => {
    expect(figureOf(`2311${NB}ms`)).toEqual({ value: 2311, unit: "ms" });
    expect(figureOf(`93${NB}%`)).toEqual({ value: 93, unit: "%" });
    expect(figureOf("21.5")).toEqual({ value: 21.5, unit: null });
    expect(figureOf(`-12.0${NB}%`)).toEqual({ value: -12, unit: "%" });
  });

  it("refuses anything that is not one plain figure (near-miss: grouping, plain space)", () => {
    expect(figureOf(null)).toBeNull();
    expect(figureOf("Unknown")).toBeNull();
    expect(figureOf("1,234")).toBeNull();
    expect(figureOf(`1${NB}234`)).toBeNull();
    expect(figureOf("12 ms")).toBeNull();
    expect(figureOf(`50.0${NB}GiB / 140.4${NB}GiB`)).toBeNull();
  });

  it("derives shares only when both sides agree on the unit", () => {
    expect(ratioOf(`50.0${NB}GiB`, `140.4${NB}GiB`)).toBeCloseTo(50 / 140.4, 6);
    expect(ratioOf(`50.0${NB}GiB`, `140.4${NB}MiB`)).toBeNull();
    expect(ratioOf("3", "0")).toBeNull();
    expect(ratioOf("11", "12")).toBeCloseTo(11 / 12, 6);
    expect(percentOf(`93${NB}%`)).toBeCloseTo(0.93, 6);
    expect(percentOf(`140${NB}%`)).toBe(1);
    expect(percentOf(`-5${NB}%`)).toBe(0);
    expect(percentOf(`93${NB}ms`)).toBeNull();
  });

  it("scales a set against its largest member and keeps unknowns unknown", () => {
    expect(sharesOf(["412", "17", null, "1207"])).toEqual([412 / 1207, 17 / 1207, null, 1]);
    expect(sharesOf(["0", "0"])).toEqual([0, 0]);
    expect(sharesOf([null])).toEqual([null]);
  });
});

describe("BarList", () => {
  const rows: BarRow[] = [
    { key: "extract_slots", text: "412", share: 412 / 1207, tone: "data" },
    { key: "freya-tts", text: "1207", share: 1, tone: "data" },
    { key: "asr", text: null, share: null, tone: "data" },
  ];

  it("is one named image whose name reads every printed figure", () => {
    const html = bars(rows);
    expect(html).toContain('role="img"');
    expect(html).toContain('aria-label="Requests: extract_slots 412, freya-tts 1207, asr Unknown"');
    expect(html).toContain('aria-hidden="true"');
  });

  it("draws one bar per known figure and none for an unknown one", () => {
    const html = bars(rows);
    expect(html.match(/<rect class="bar"/g)).toHaveLength(2);
    expect(html).toContain('width="240"');
    expect(html).toContain('<span class="bar-value cell-unknown">Unknown</span>');
  });

  it("draws nothing for a zero share but still prints the figure (near-miss: 0 is not unknown)", () => {
    const html = bars([{ key: "idle", text: "0", share: 0, tone: "data" }]);
    expect(html).not.toContain('class="bar"');
    expect(html).toContain('<span class="bar-value">0</span>');
  });

  it("keeps a tiny non-zero share visible", () => {
    const html = bars([{ key: "rare", text: "1", share: 0.0001, tone: "data" }]);
    expect(html).toContain('width="2"');
  });

  it("hatches a stale reading and names it stale", () => {
    const html = bars([{ key: "redis", text: `2.1${NB}ms`, share: 1, tone: "bad", stale: true }]);
    expect(html).toContain('fill="url(#chart-lane-requests-hatch)"');
    expect(html).toContain('data-stale="true"');
    expect(html).toContain(`aria-label="Requests: redis 2.1${NB}ms (stale)"`);
    expect(html).not.toContain('id="chart-lane-requests-bad"');
  });

  it("fills a fresh reading from its tone's gradient, defined once per chart", () => {
    const html = bars(rows);
    expect(html.match(/id="chart-lane-requests-data"/g)).toHaveLength(1);
    expect(html).toContain('fill="url(#chart-lane-requests-data)"');
  });

  it("derives element ids that are safe and distinct per chart", () => {
    const html = bars(rows, "slo:api.availability");
    expect(html).toContain('id="chart-slo-api-availability-data"');
  });

  it("renders nothing for no rows, and never a style attribute", () => {
    expect(bars([])).toBe("");
    expect(bars(rows)).not.toContain("style=");
  });
});

describe("Gauge", () => {
  function gauge(text: string | null, share: number | null): string {
    return renderToStaticMarkup(
      <Gauge id="clip" label="Hit ratio" text={text} share={share} tone="data" c={c} />,
    );
  }

  it("sweeps the arc to the share and prints the figure beside it", () => {
    const html = gauge(`93${NB}%`, 0.93);
    expect(html).toContain('stroke-dashoffset="7"');
    expect(html).toContain('pathLength="100"');
    expect(html).toContain(`aria-label="Hit ratio: 93${NB}%"`);
    expect(html).not.toContain("style=");
  });

  it("draws no arc for an unknown share and says unknown (near-miss: 0 % draws none either)", () => {
    const unknown = gauge(null, null);
    expect(unknown).not.toContain("gauge-arc");
    expect(unknown).toContain('data-tone="unknown"');
    expect(unknown).toContain('aria-label="Hit ratio: Unknown"');
    const zero = gauge(`0${NB}%`, 0);
    expect(zero).not.toContain("gauge-arc");
    expect(zero).toContain('data-tone="data"');
  });
});

describe("toneOf", () => {
  it("folds the console's state words onto chart tones", () => {
    expect(toneOf("healthy")).toBe("ok");
    expect(toneOf("success")).toBe("ok");
    expect(toneOf("failure")).toBe("bad");
    expect(toneOf("unhealthy")).toBe("bad");
    expect(toneOf("cancelled")).toBe("warn");
    expect(toneOf("no_result")).toBe("unknown");
    expect(toneOf(null)).toBe("unknown");
  });
});
