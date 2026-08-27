/**
 * Dev-lane voice note (INT-194): recorded audio goes to OUR whisper-tr
 * ASR on the team GPU box (through the dev Mac's port forward) and the
 * transcript lands in the intake's patient-note field.
 *
 * This is the demo bridge, not the product voice path: the product runtime
 * (INT-090s/135) is LiveKit with mlocked ≤60 s buffers and never writes
 * audio to disk (invariant 3). This lane is __DEV__-gated, synthetic
 * content only, and the recording file is deleted right after upload.
 */
import Constants from "expo-constants";
import * as FileSystem from "expo-file-system/legacy";

/**
 * Candidate ASR hosts, most specific first. The Metro hostUri names the dev
 * Mac directly in LAN mode; in tunnel mode it is an exp.direct name with no
 * route back to the Mac, so the configured dev hosts (app.json
 * extra.asrHosts: localhost for the simulator, the Mac's LAN IP for a
 * same-network phone) are probed instead. First /health that answers wins.
 */
export function asrCandidates(hostUri: string | undefined, extraHosts: string[]): string[] {
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
  return hosts.map((h) => `http://${h}:8802`);
}

function configuredCandidates(): string[] {
  const extra = (Constants.expoConfig?.extra ?? {}) as { asrHosts?: string[] };
  return asrCandidates(Constants.expoConfig?.hostUri, extra.asrHosts ?? []);
}

async function probe(base: string, timeoutMs: number): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${base}/health`, { signal: controller.signal });
    return res.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

export async function reachableAsrBaseUrl(): Promise<string | null> {
  for (const base of configuredCandidates()) {
    if (await probe(base, 1500)) {
      return base;
    }
  }
  return null;
}

export async function transcribeRecording(uri: string): Promise<string> {
  const base = await reachableAsrBaseUrl();
  if (base === null) {
    throw new Error("asr_unreachable");
  }
  try {
    const result = await FileSystem.uploadAsync(`${base}/transcribe`, uri, {
      httpMethod: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      uploadType: FileSystem.FileSystemUploadType.BINARY_CONTENT,
    });
    const parsed: { text?: string } = JSON.parse(result.body);
    return (parsed.text ?? "").trim();
  } finally {
    // invariant-3 posture even in the dev lane: no audio lingers on disk
    await FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => undefined);
  }
}
