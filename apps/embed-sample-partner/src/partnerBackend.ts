/**
 * INT-320 follow-up — the sample partner's server-to-server backend (ADR-029).
 *
 * This is the half of the embed handshake that holds a credential. A partner
 * never puts an Önvizit secret in the browser: the "Start pre-visit" button calls
 * the partner's OWN backend (this module), and only this backend authenticates
 * to Önvizit and mints a launch ticket via the real
 * ``POST /embed/v1/launch-tickets``. The browser receives only the three public
 * launch fields (ticket, launch_url, expires_at) — never the token, never the
 * upstream error body.
 *
 * Dev tier: the partner-backend credential is the Önvizit dev admin bearer
 * (``INTAKE_DEV_TOKEN_ADMIN``). A live partner authenticates with OIDC
 * client-credentials / mTLS instead (awaiting-human, ADR-029); this module's
 * shape does not change when it does — only where ``adminToken`` comes from.
 *
 * Nothing clinical or personal crosses this boundary (invariant 6): the request
 * carries a ``tenant_id`` and the response carries an opaque ticket.
 */

/** The public launch response shape — identical to what ``@intake/embed-sdk``
 * consumes in the browser. */
export interface LaunchResponse {
  ticket: string;
  launch_url: string;
  expires_at: number;
}

export interface MintOptions {
  /** Base URL of the Önvizit API, e.g. ``http://127.0.0.1:8000`` in dev. */
  apiBase: string;
  /** The partner-backend credential. Held only here, server-side; it is never
   * returned to the browser. */
  adminToken: string;
  /** The registered embed tenant id (dev: the synthetic ``dev-partner-alpha``
   * row in infra/tenants/embed_registry.yaml). */
  tenantId: string;
  /** Injectable fetch, for tests and non-global hosts. */
  fetchImpl?: typeof fetch;
}

/** A refusal from the partner backend. ``status`` is the HTTP status this
 * backend returns to its own page — never the upstream status verbatim, so a
 * Önvizit-internal detail is not reflected to the browser. */
export class PartnerBackendError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "PartnerBackendError";
    this.status = status;
  }
}

function trimTrailingSlash(base: string): string {
  return base.endsWith("/") ? base.slice(0, -1) : base;
}

/** Validate the wire shape Önvizit returns. The SDK re-validates in the browser
 * (and additionally enforces an https ``launch_url`` before opening it); this
 * backend only asserts the contract so a malformed upstream body never reaches
 * the page as a "success". */
function parseLaunchResponse(body: unknown): LaunchResponse {
  if (typeof body !== "object" || body === null) {
    throw new PartnerBackendError("Önvizit returned a non-object launch response", 502);
  }
  const record = body as Record<string, unknown>;
  const ticket = record["ticket"];
  const launch_url = record["launch_url"];
  const expires_at = record["expires_at"];
  if (typeof ticket !== "string" || ticket.length === 0) {
    throw new PartnerBackendError("Önvizit launch response is missing a ticket", 502);
  }
  if (typeof launch_url !== "string" || launch_url.length === 0) {
    throw new PartnerBackendError("Önvizit launch response is missing launch_url", 502);
  }
  if (typeof expires_at !== "number") {
    throw new PartnerBackendError("Önvizit launch response is missing expires_at", 502);
  }
  return { ticket, launch_url, expires_at };
}

/**
 * Mint a launch ticket for {@link MintOptions.tenantId} against the real Önvizit
 * embed endpoint. Returns the validated public launch response. Throws
 * {@link PartnerBackendError} on any reach failure, non-2xx upstream, or
 * malformed body — none of which leak the token or the upstream body.
 */
export async function mintLaunchTicket(options: MintOptions): Promise<LaunchResponse> {
  const doFetch = options.fetchImpl ?? globalThis.fetch;
  if (typeof doFetch !== "function") {
    throw new PartnerBackendError("no fetch implementation is available", 500);
  }
  const url = `${trimTrailingSlash(options.apiBase)}/embed/v1/launch-tickets`;
  let response: Response;
  try {
    response = await doFetch(url, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${options.adminToken}`,
      },
      body: JSON.stringify({ tenant_id: options.tenantId }),
    });
  } catch {
    // the token is in the request we could not send; surface a generic reach
    // error, never the cause (which may echo the header)
    throw new PartnerBackendError("could not reach the Önvizit embed API", 502);
  }
  if (!response.ok) {
    // 401/403 (bad admin bearer), 404 (tenant not registered), 503 (signing key
    // not seeded / embed unconfigured) all land here — the operator reads the
    // status from this backend's own log, the browser gets a generic refusal
    throw new PartnerBackendError(
      `Önvizit refused the mint (upstream status ${response.status})`,
      502,
    );
  }
  return parseLaunchResponse(await response.json());
}

/** The JSON body this backend returns to its page: the public launch response,
 * or an id-shaped error (never a token, never the upstream body). */
export type TicketResponseBody = LaunchResponse | { error: string };

export interface TicketHttpResult {
  status: number;
  body: TicketResponseBody;
  /** A server-side-only line for the operator's terminal. Not sent to the
   * browser; carries no secret, only the id-shaped reason. */
  logLine: string;
}

/**
 * The one route the partner page calls (``POST /onvizit/ticket``). Wraps
 * {@link mintLaunchTicket} into an HTTP-shaped result: a 200 with the public
 * launch response, or a refusal with an id-shaped error. The credential and the
 * upstream body never appear in {@link TicketHttpResult.body}.
 */
export async function handleTicketRequest(options: MintOptions): Promise<TicketHttpResult> {
  if (options.adminToken.length === 0) {
    return {
      status: 500,
      body: { error: "partner_backend_unconfigured" },
      logLine: "partner_backend_unconfigured: set ONVIZIT_ADMIN_TOKEN to the dev admin bearer",
    };
  }
  try {
    const launch = await mintLaunchTicket(options);
    return { status: 200, body: launch, logLine: "ok: minted a launch ticket" };
  } catch (error) {
    if (error instanceof PartnerBackendError) {
      return {
        status: error.status,
        body: { error: "launch_unavailable" },
        logLine: error.message,
      };
    }
    return {
      status: 500,
      body: { error: "launch_unavailable" },
      logLine: error instanceof Error ? error.message : String(error),
    };
  }
}
