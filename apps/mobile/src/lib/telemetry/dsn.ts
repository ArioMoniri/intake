/**
 * GlitchTip DSN parsing (INT-145).
 *
 * There is no default here and there must never be one. A crash reporter that
 * falls back to a built-in host sends patient-adjacent diagnostics to an
 * endpoint nobody in this project chose — which is the failure mode, not a
 * convenience. Unset means inert; malformed means inert; only a DSN somebody
 * configured produces an endpoint.
 *
 * The DSN is parsed by pattern rather than by `URL`: React Native's `URL` is a
 * partial implementation, and a parser that behaves differently on device than
 * in the test is worse than no parser.
 *
 * A DSN with a secret half (`key:secret@`) is REFUSED rather than trimmed.
 * Sentry retired the secret in 2016 and GlitchTip never wanted one, so a DSN
 * carrying one is a copy-paste from somewhere else — and quietly accepting it
 * would put a credential in `app.json`.
 */

/** The three things we keep from a DSN. The rest of it is discarded. */
export interface Dsn {
  readonly publicKey: string;
  readonly projectId: string;
  readonly envelopeUrl: string;
}

const DSN_PATTERN = /^(https?):\/\/([0-9A-Za-z]+)@([^/@:?#]+(?::\d{1,5})?)\/(\d{1,12})(?:[?#].*)?$/;

/** Parse a configured DSN; `null` for unset, blank or malformed. */
export function parseDsn(raw: string | null | undefined): Dsn | null {
  if (typeof raw !== "string") {
    return null;
  }
  const match = DSN_PATTERN.exec(raw.trim());
  if (match === null) {
    return null;
  }
  const [, scheme, publicKey, host, projectId] = match;
  // The endpoint is derived, never taken from the DSN's path: a query string
  // or a fragment in the configured value reaches nothing.
  return { publicKey, projectId, envelopeUrl: `${scheme}://${host}/api/${projectId}/envelope/` };
}
