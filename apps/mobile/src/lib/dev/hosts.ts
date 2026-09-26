/**
 * Dev-lane service discovery, shared by the whisper ASR bridge (INT-194,
 * port 8802) and the intake extract bridge (INT-199, port 8804): both
 * daemons live on the team GPU box behind the dev Mac's port forwards, so
 * the same host-candidate walk finds them. Pure and node-testable — the
 * expo-constants reading lives in expoHosts.ts.
 *
 * INT-246 adds the DETAILED form of the walk. A bare `null` cannot say which
 * bases were tried or why each one refused, and that silence cost hours the
 * day a port forward died: the app fell through to the typed steps exactly as
 * designed, and nothing anywhere could tell a dead tunnel from an unbuilt
 * feature. `probeReachability` reports the whole walk; `reachableBaseUrl`
 * keeps its signature on top of it, so no caller had to change.
 */

/**
 * The dev LAN walk exists only in a dev build (INT-328's rule, audit F01/F17).
 * A release build gets no candidate — no Metro host, no `extra.asrHosts`
 * entry, no loopback or LAN address — and the walk is never run, so a store
 * build neither raises the iOS local-network prompt nor waits on a lane that
 * cannot exist on a patient's network. Every voice lane then reports
 * unreachable and the intake takes the typed door, as it does today when a
 * tunnel is down. Pass `__DEV__`, never a literal.
 */
export function devLanCandidates<T>(isDev: boolean, walk: () => T[]): T[] {
  return isDev ? walk() : [];
}

/**
 * Candidate service bases, most specific first. The Metro hostUri names the
 * dev Mac directly in LAN mode; in tunnel mode it is an exp.direct name with
 * no route back to the Mac, so only the configured dev hosts remain.
 */
export function serviceCandidates(
  hostUri: string | undefined,
  extraHosts: readonly string[],
  port: number,
): string[] {
  const hosts: string[] = [];
  if (hostUri) {
    const host = hostUri.split(":")[0];
    if (!host.endsWith(".exp.direct")) {
      hosts.push(host);
    }
  }
  for (const host of extraHosts) {
    if (!hosts.includes(host)) {
      hosts.push(host);
    }
  }
  return hosts.map((h) => `http://${h}:${port}`);
}

export interface ProbeOptions {
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

/**
 * Why a candidate did not serve. `refused` is every transport error the app
 * can see — connection refused, no route, a name that does not resolve; from
 * inside fetch they are one rejection, and telling them apart is exactly what
 * `make voice-doctor` does on the host, where the socket errors survive.
 */
export type ProbeFailure =
  | { readonly kind: "timeout"; readonly timeoutMs: number }
  | { readonly kind: "refused" }
  | { readonly kind: "status"; readonly status: number };

export interface CandidateProbe {
  readonly base: string;
  /** null when this base answered 2xx. */
  readonly failure: ProbeFailure | null;
}

export interface ReachabilityReport {
  /** First base that answered, or null when the whole walk failed. */
  readonly base: string | null;
  /** Every base tried, in order. The walk stops at the first that answers. */
  readonly probes: readonly CandidateProbe[];
}

/** One candidate, once. Never retried — a dead host is not worth a second ask. */
async function probeCandidate(
  base: string,
  { timeoutMs = 1500, fetchImpl = fetch }: ProbeOptions,
): Promise<CandidateProbe> {
  const controller = new AbortController();
  // Our own flag rather than the rejection's name: a fetch polyfill is free
  // to reject with whatever it likes, but only this timer can fire.
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  try {
    const res = await fetchImpl(`${base}/health`, { signal: controller.signal });
    return { base, failure: res.ok ? null : { kind: "status", status: res.status } };
  } catch {
    return { base, failure: timedOut ? { kind: "timeout", timeoutMs } : { kind: "refused" } };
  } finally {
    clearTimeout(timer);
  }
}

/** True when the base's /health answers 2xx before the timeout. */
export async function probeHealth(base: string, options: ProbeOptions = {}): Promise<boolean> {
  return (await probeCandidate(base, options)).failure === null;
}

/**
 * The whole walk, said out loud: which bases were tried and how each one
 * failed. Stops at the first base that answers, so a healthy first candidate
 * costs exactly one request.
 */
export async function probeReachability(
  candidates: readonly string[],
  options: ProbeOptions = {},
): Promise<ReachabilityReport> {
  const probes: CandidateProbe[] = [];
  for (const base of candidates) {
    const probe = await probeCandidate(base, options);
    probes.push(probe);
    if (probe.failure === null) {
      return { base, probes };
    }
  }
  return { base: null, probes };
}

/** First candidate whose /health answers wins; null when nothing does. */
export async function reachableBaseUrl(
  candidates: readonly string[],
  options: ProbeOptions = {},
): Promise<string | null> {
  return (await probeReachability(candidates, options)).base;
}
