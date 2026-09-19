/**
 * A minimal, dependency-free parser for the Prometheus text exposition format
 * (INT-181; the body `GET /metrics` serves via `intake_platform.health`).
 *
 * The console never adds a metrics client to the browser bundle: `/metrics` is
 * plain text, so a ~40-line parser is the whole dependency. It reads exactly
 * what `prometheus_client.generate_latest` writes — `# HELP`/`# TYPE` comment
 * lines, then `name{label="value",...} number [timestamp]` samples — and
 * returns a flat list of samples. The projection in `./module` decides which of
 * those samples the page is allowed to paint; this file only turns text into
 * data and makes no judgement about PHI, catalogue membership or shape.
 *
 * The label block is delimited by the FIRST `{` and the LAST `}` on the line:
 * a route-template label value such as `route="/visits/{visit_id}"` carries its
 * own braces, but the value token after the structural `}` never does, so the
 * last `}` is always the structural close. Label pairs are then read with a
 * quote-aware pattern so a comma or an escaped quote inside a value cannot split
 * a pair.
 */

/** One observation off `/metrics`: a series name, its labels, and its value. */
export interface Sample {
  readonly name: string;
  readonly labels: Readonly<Record<string, string>>;
  readonly value: number;
}

/** `key="value"` pairs, quote- and escape-aware so commas inside a value are safe. */
const LABEL_PAIR = /([a-zA-Z_][a-zA-Z0-9_]*)="((?:[^"\\]|\\.)*)"/g;

/** Prometheus renders the non-finite values as these tokens. */
function parseValue(token: string): number {
  switch (token) {
    case "+Inf":
      return Number.POSITIVE_INFINITY;
    case "-Inf":
      return Number.NEGATIVE_INFINITY;
    case "NaN":
      return Number.NaN;
    default:
      return Number.parseFloat(token);
  }
}

function unescape(value: string): string {
  return value.replace(/\\(["\\n])/g, (_match, ch: string) => (ch === "n" ? "\n" : ch));
}

function parseLabels(block: string): Record<string, string> {
  const labels: Record<string, string> = {};
  for (const match of block.matchAll(LABEL_PAIR)) {
    labels[match[1]!] = unescape(match[2]!);
  }
  return labels;
}

/**
 * Parse a Prometheus text exposition into a flat list of samples.
 *
 * Comment lines (`#`), blank lines and lines with no parseable value are
 * skipped. A malformed value yields `NaN`, which the projection treats as a
 * missing reading rather than a zero.
 */
export function parsePrometheusText(text: string): readonly Sample[] {
  const samples: Sample[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (line === "" || line.startsWith("#")) {
      continue;
    }
    const open = line.indexOf("{");
    let name: string;
    let labels: Record<string, string>;
    let rest: string;
    if (open === -1) {
      const space = line.indexOf(" ");
      if (space === -1) {
        continue;
      }
      name = line.slice(0, space);
      labels = {};
      rest = line.slice(space + 1).trim();
    } else {
      const close = line.lastIndexOf("}");
      if (close < open) {
        continue;
      }
      name = line.slice(0, open).trim();
      labels = parseLabels(line.slice(open + 1, close));
      rest = line.slice(close + 1).trim();
    }
    const token = rest.split(/\s+/)[0];
    if (token === undefined || token === "") {
      continue;
    }
    samples.push({ name, labels, value: parseValue(token) });
  }
  return samples;
}
