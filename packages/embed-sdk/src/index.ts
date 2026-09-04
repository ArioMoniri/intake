/**
 * INT-320 — partner "Start pre-visit" embed SDK (ADR-028).
 *
 * A partner embeds Vizite as a button. This SDK is the thin launcher: on a tap
 * it asks the PARTNER'S OWN backend for a launch response (the ticket is minted
 * server-to-server, so the SDK never calls Vizite directly and holds NO Vizite
 * secret), then opens the branded intake at the `launch_url` Vizite returned.
 *
 * The trust boundary lives in the ticket, not here. This code's whole job is to
 * (1) never accept a non-https destination it would open, and (2) never hold a
 * credential. Both are enforced below and covered by tests.
 */

export interface LaunchResponse {
  /** The opaque, single-use, short-lived launch ticket. */
  ticket: string;
  /** The Vizite URL that starts the branded intake, carrying the ticket. */
  launch_url: string;
  /** Unix seconds at which the ticket expires. */
  expires_at: number;
}

export interface StartPrevisitConfig {
  /**
   * The PARTNER'S own backend endpoint that mints a launch ticket
   * server-to-server. Must be an https URL or a same-origin relative path
   * (starting with "/"); anything else is refused so the SDK cannot be pointed
   * at a `javascript:`/`data:` sink.
   */
  ticketEndpoint: string;
  /** Optional request init the partner backend needs (auth cookie, body). It is
   * opaque to the SDK and must never carry a Vizite credential. */
  requestInit?: RequestInit;
  /** Injectable fetch, for tests and non-browser hosts. */
  fetchImpl?: typeof fetch;
  /** How to open the branded intake. Default: `location.assign`. */
  open?: (url: string) => void;
}

export class EmbedError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "EmbedError";
  }
}

function assertPartnerEndpoint(endpoint: string): void {
  if (endpoint.startsWith("/")) {
    return; // same-origin relative path
  }
  let parsed: URL;
  try {
    parsed = new URL(endpoint);
  } catch {
    throw new EmbedError("ticketEndpoint must be an https URL or a same-origin path");
  }
  if (parsed.protocol !== "https:") {
    throw new EmbedError("ticketEndpoint must use https");
  }
}

function assertLaunchUrl(url: unknown): string {
  if (typeof url !== "string") {
    throw new EmbedError("launch response is missing launch_url");
  }
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    throw new EmbedError("launch_url is not a valid URL");
  }
  // the only destination the SDK will ever open is an https Vizite URL — this
  // is what stops a tampered response from turning the button into an open
  // redirect or a `javascript:` sink.
  if (parsed.protocol !== "https:") {
    throw new EmbedError("launch_url must use https");
  }
  return url;
}

function parseLaunchResponse(body: unknown): LaunchResponse {
  if (typeof body !== "object" || body === null) {
    throw new EmbedError("launch response is not an object");
  }
  const record = body as Record<string, unknown>;
  const launch_url = assertLaunchUrl(record["launch_url"]);
  const ticket = record["ticket"];
  const expires_at = record["expires_at"];
  if (typeof ticket !== "string" || ticket.length === 0) {
    throw new EmbedError("launch response is missing a ticket");
  }
  if (typeof expires_at !== "number") {
    throw new EmbedError("launch response is missing expires_at");
  }
  return { ticket, launch_url, expires_at };
}

/**
 * Ask the partner backend for a launch response and open the branded intake.
 * Returns the validated response. Throws {@link EmbedError} on any bad input,
 * a failed request or an unsafe destination.
 */
export async function startPrevisit(config: StartPrevisitConfig): Promise<LaunchResponse> {
  assertPartnerEndpoint(config.ticketEndpoint);
  const doFetch = config.fetchImpl ?? globalThis.fetch;
  if (typeof doFetch !== "function") {
    throw new EmbedError("no fetch implementation is available");
  }
  const init: RequestInit = { method: "POST", ...config.requestInit };
  const response = await doFetch(config.ticketEndpoint, init);
  if (!response.ok) {
    throw new EmbedError(`partner backend refused the launch (status ${response.status})`);
  }
  const launch = parseLaunchResponse(await response.json());
  const open = config.open ?? ((url: string) => globalThis.location.assign(url));
  open(launch.launch_url);
  return launch;
}

export interface StartButtonConfig extends StartPrevisitConfig {
  /** Button label. Default is Turkish, the product's primary language. */
  label?: string;
  /** Document to create the element in (injectable for tests). */
  document?: Document;
  /** Called if the launch fails; by default the error is swallowed so a failed
   * tap never throws into the partner's page. */
  onError?: (error: unknown) => void;
}

const DEFAULT_LABEL = "Ön muayeneyi başlat";

/**
 * Create a "Start pre-visit" button wired to {@link startPrevisit}. The button
 * carries no state and no secret; each tap performs a fresh handshake.
 */
export function createStartButton(config: StartButtonConfig): HTMLButtonElement {
  const doc = config.document ?? globalThis.document;
  const button = doc.createElement("button");
  button.type = "button";
  button.textContent = config.label ?? DEFAULT_LABEL;
  button.dataset["viziteEmbed"] = "start-previsit";
  button.addEventListener("click", () => {
    void startPrevisit(config).catch(config.onError ?? (() => undefined));
  });
  return button;
}
