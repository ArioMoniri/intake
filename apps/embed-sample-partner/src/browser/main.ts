/**
 * INT-320 follow-up — the partner page glue (ADR-029).
 *
 * The button is rendered by `@intake/embed-sdk`. It holds no Vizite secret: on
 * a tap it POSTs to this partner app's OWN backend (`/vizite/ticket`), which
 * mints the launch ticket server-to-server, and the SDK then opens the branded
 * Vizite launch URL — which the SDK will only ever do for an https destination.
 */

import { createStartButton } from "@intake/embed-sdk";

/** The partner backend route on this same origin. The SDK accepts a relative
 * path and never sees the Vizite API or its credential. */
const TICKET_ENDPOINT = "/vizite/ticket";

function describe(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function mount(): void {
  const slot = document.getElementById("previsit-slot");
  const status = document.getElementById("status");
  if (slot === null || status === null) {
    return;
  }

  const button = createStartButton({
    ticketEndpoint: TICKET_ENDPOINT,
    open: (url: string): void => {
      // The SDK has already validated that `url` is an https Vizite URL before
      // calling this. Show it, then hand off in a new tab so the sample page
      // stays visible for the operator.
      status.textContent = `Launch ticket minted. Opening the branded intake: ${url}`;
      status.dataset["state"] = "ok";
      window.open(url, "_blank", "noopener");
    },
    onError: (error: unknown): void => {
      status.textContent = `Could not start the pre-visit: ${describe(error)}`;
      status.dataset["state"] = "error";
    },
  });

  slot.replaceChildren(button);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount);
} else {
  mount();
}
