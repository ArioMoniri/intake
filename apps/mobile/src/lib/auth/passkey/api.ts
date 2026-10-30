/**
 * INT-582 (D36) — the `/v1/me/passkeys` transport over the DPoP-bound session.
 *
 * Every answer is reduced to a `ServerAnswer`: the body on success; on a
 * refusal only the machine-readable error code and whether the server named
 * the manual path. No server narrative reaches the screen (02 §8.2), and
 * nothing here logs, stores or puts a credential or a grant in a URL.
 */
import { authedFetch } from "@/lib/auth/api";

import type { AssertionCredential, RegistrationCredential, ServerAnswer } from "./ceremony";
import { STEP_UP_GRANT_HEADER, type StepUpAction } from "./rp";

const BASE = "/v1/me/passkeys";

async function json(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

/** A Response reduced to what a decision needs. */
export async function toAnswer(response: Response): Promise<ServerAnswer> {
  const body = await json(response);
  if (response.ok) {
    return { ok: true, status: response.status, body };
  }
  const row = typeof body === "object" && body !== null ? (body as Record<string, unknown>) : {};
  return {
    ok: false,
    status: response.status,
    error: typeof row.error === "string" ? row.error : "",
    manualPath: typeof row.manual_path === "string" && row.manual_path.length > 0,
  };
}

async function send(path: string, init: RequestInit): Promise<ServerAnswer> {
  try {
    return await toAnswer(await authedFetch(path, init));
  } catch {
    // no session or no network: never a passkey, never a grant
    return { ok: false, status: 0, error: "", manualPath: false };
  }
}

function post(body?: unknown, headers: Record<string, string> = {}): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}

export const passkeyApi = {
  registrationOptions: (): Promise<ServerAnswer> => send(`${BASE}/registration/options`, post()),
  register: (credential: RegistrationCredential): Promise<ServerAnswer> =>
    send(`${BASE}/registration`, post({ credential })),
  stepUpOptions: (action: StepUpAction): Promise<ServerAnswer> =>
    send(`${BASE}/step-up/options`, post({ action })),
  stepUp: (action: StepUpAction, credential: AssertionCredential): Promise<ServerAnswer> =>
    send(`${BASE}/step-up`, post({ action, credential })),
  list: (): Promise<ServerAnswer> => send(BASE, { method: "GET" }),
  startRecovery: (): Promise<ServerAnswer> => send(`${BASE}/recovery`, post()),
  cancelRecovery: (grant: string): Promise<ServerAnswer> =>
    send(`${BASE}/recovery`, { method: "DELETE", headers: { [STEP_UP_GRANT_HEADER]: grant } }),
  remove: (passkeyId: string, grant: string): Promise<ServerAnswer> =>
    send(`${BASE}/${encodeURIComponent(passkeyId)}`, {
      method: "DELETE",
      headers: { [STEP_UP_GRANT_HEADER]: grant },
    }),
};
