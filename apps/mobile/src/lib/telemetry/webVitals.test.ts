/**
 * Web RUM (INT-145). The mobile package is the only web target that exists
 * (`expo start --web`, react-native-web), so Core Web Vitals are read from the
 * platform's own PerformanceObserver — no third-party collector, and inert
 * everywhere the API is absent, which is every native build.
 */
import { describe, expect, it, vi } from "vitest";

import { observeWebVitals, vitalFromEntry } from "./webVitals";

interface FakeObserver {
  observe: (options: { type: string; buffered: boolean }) => void;
  disconnect: () => void;
}

/** A scope that looks like a browser: one PerformanceObserver per `type`. */
function browserScope(): {
  scope: Record<string, unknown>;
  fire: (type: string, entries: unknown[]) => void;
  observed: string[];
  disconnects: number;
} {
  const callbacks = new Map<string, (list: { getEntries: () => unknown[] }) => void>();
  const observed: string[] = [];
  let disconnects = 0;
  class PerformanceObserverStub implements FakeObserver {
    private readonly callback: (list: { getEntries: () => unknown[] }) => void;
    constructor(callback: (list: { getEntries: () => unknown[] }) => void) {
      this.callback = callback;
    }
    observe(options: { type: string; buffered: boolean }): void {
      observed.push(options.type);
      callbacks.set(options.type, this.callback);
    }
    disconnect(): void {
      disconnects += 1;
    }
  }
  return {
    scope: { PerformanceObserver: PerformanceObserverStub },
    fire: (type, entries) => callbacks.get(type)?.({ getEntries: () => entries }),
    observed,
    get disconnects() {
      return disconnects;
    },
  };
}

describe("vitalFromEntry", () => {
  it("maps the four entry types we observe onto catalogued vitals", () => {
    expect(vitalFromEntry({ entryType: "largest-contentful-paint", startTime: 2100 })).toEqual({
      metricId: "web.core_web_vitals",
      value: 2100,
      vital: "LCP",
    });
    expect(vitalFromEntry({ entryType: "layout-shift", value: 0.07 })).toEqual({
      metricId: "web.core_web_vitals",
      value: 0.07,
      vital: "CLS",
    });
    expect(vitalFromEntry({ entryType: "event", duration: 190, interactionId: 3 })).toEqual({
      metricId: "web.core_web_vitals",
      value: 190,
      vital: "INP",
    });
    expect(
      vitalFromEntry({ entryType: "paint", name: "first-contentful-paint", startTime: 640 }),
    ).toEqual({ metricId: "web.core_web_vitals", value: 640, vital: "FCP" });
    expect(vitalFromEntry({ entryType: "navigation", responseStart: 120 })).toEqual({
      metricId: "web.core_web_vitals",
      value: 120,
      vital: "TTFB",
    });
  });

  it("ignores an entry type we do not observe rather than guessing a vital", () => {
    expect(vitalFromEntry({ entryType: "resource", startTime: 5 })).toBeNull();
    expect(vitalFromEntry({ entryType: "paint", name: "first-paint", startTime: 5 })).toBeNull();
    expect(vitalFromEntry({ entryType: "event", duration: 190 })).toBeNull();
    expect(vitalFromEntry(null)).toBeNull();
    expect(vitalFromEntry("not-an-entry")).toBeNull();
  });

  it("never reads a name, a url or any other free-text field off an entry", () => {
    const sample = vitalFromEntry({
      entryType: "largest-contentful-paint",
      startTime: 2100,
      url: "https://example.test/visits?q=gogus-agrisi",
      element: "<img alt='Ayse Yilmaz kan tahlili'>",
      id: "hero",
    });
    expect(Object.keys(sample ?? {}).sort()).toEqual(["metricId", "value", "vital"]);
  });
});

describe("observeWebVitals", () => {
  it("is inert with no PerformanceObserver — every native build", () => {
    const sink = { emit: vi.fn() };
    const stop = observeWebVitals({}, sink);
    expect(stop).toBeNull();
    expect(sink.emit).not.toHaveBeenCalled();
  });

  it("subscribes to the five entry types and emits catalogued samples", () => {
    const sink = { emit: vi.fn() };
    const browser = browserScope();
    const stop = observeWebVitals(browser.scope, sink);
    expect(browser.observed.sort()).toEqual([
      "event",
      "largest-contentful-paint",
      "layout-shift",
      "navigation",
      "paint",
    ]);
    browser.fire("largest-contentful-paint", [
      { entryType: "largest-contentful-paint", startTime: 2100 },
    ]);
    expect(sink.emit).toHaveBeenCalledWith({
      metricId: "web.core_web_vitals",
      value: 2100,
      vital: "LCP",
    });
    stop?.();
    expect(browser.disconnects).toBe(5);
  });

  it("a throwing observer never breaks the page it is measuring", () => {
    const sink = { emit: vi.fn() };
    const scope = {
      PerformanceObserver: class {
        observe(): void {
          throw new Error("unsupported entry type");
        }
        disconnect(): void {}
      },
    };
    expect(() => observeWebVitals(scope, sink)).not.toThrow();
    expect(sink.emit).not.toHaveBeenCalled();
  });
});
