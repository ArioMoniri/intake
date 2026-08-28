/**
 * Dev-lane service discovery, shared by the whisper ASR bridge (INT-194,
 * port 8802) and the intake extract bridge (INT-199, port 8804): both
 * daemons live on the team GPU box behind the dev Mac's port forwards, so
 * the same host-candidate walk finds them. Pure and node-testable — the
 * expo-constants reading lives in expoHosts.ts.
 */

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

/** True when the base's /health answers 2xx before the timeout. */
export async function probeHealth(
  base: string,
  { timeoutMs = 1500, fetchImpl = fetch }: ProbeOptions = {},
): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetchImpl(`${base}/health`, { signal: controller.signal });
    return res.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

/** First candidate whose /health answers wins; null when nothing does. */
export async function reachableBaseUrl(
  candidates: readonly string[],
  options: ProbeOptions = {},
): Promise<string | null> {
  for (const base of candidates) {
    if (await probeHealth(base, options)) {
      return base;
    }
  }
  return null;
}
