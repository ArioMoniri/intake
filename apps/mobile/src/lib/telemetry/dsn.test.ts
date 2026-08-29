/** GlitchTip DSN parsing (INT-145). No DSN means inert — never a default. */
import { describe, expect, it } from "vitest";

import { parseDsn } from "./dsn";

describe("parseDsn", () => {
  it("derives the envelope endpoint from the DSN and nothing else", () => {
    const dsn = parseDsn("http://f00dcafe@127.0.0.1:8010/7");
    expect(dsn).toEqual({
      publicKey: "f00dcafe",
      projectId: "7",
      envelopeUrl: "http://127.0.0.1:8010/api/7/envelope/",
    });
  });

  it("keeps https and a default port out of the endpoint", () => {
    expect(parseDsn("https://abc123@glitchtip.intake.local/42")?.envelopeUrl).toBe(
      "https://glitchtip.intake.local/api/42/envelope/",
    );
  });

  it("returns null when unset — there is no default endpoint to fall back to", () => {
    for (const unset of [undefined, null, "", "   "]) {
      expect(parseDsn(unset)).toBeNull();
    }
  });

  it("returns null for a malformed DSN rather than guessing a host", () => {
    for (const bad of [
      "not-a-url",
      "http://127.0.0.1:8010/7", // no public key
      "http://f00d@127.0.0.1:8010/", // no project id
      "http://f00d@127.0.0.1:8010/abc", // project id is not numeric
      "ftp://f00d@127.0.0.1:8010/7", // not an http scheme
      "http://f00d:secret@127.0.0.1:8010/7", // a secret half we never accept
    ]) {
      expect(parseDsn(bad), bad).toBeNull();
    }
  });

  it("carries no query or fragment from the DSN into the endpoint", () => {
    const dsn = parseDsn("http://f00d@127.0.0.1:8010/7?token=abc#frag");
    expect(dsn?.envelopeUrl).toBe("http://127.0.0.1:8010/api/7/envelope/");
  });
});
