/**
 * Intake extract client (INT-199): the recorded free-speech transcript goes
 * to OUR qwen extract daemon on the team GPU box (port 8804, same dev-lane
 * probing as the whisper bridge) and comes back as per-question ANSWER
 * SUGGESTIONS with the patient's verbatim words as provenance.
 *
 * The wire is never trusted: every response is re-validated here against the
 * pack — unknown question ids and option ids are dropped, and a single-select
 * candidate must carry exactly one value (ambiguity is dropped, never
 * guessed). Candidates are suggestions the patient confirms one question at
 * a time — never triage, never a diagnosis (invariant 1 posture); the
 * transcript itself is patient data, rendered only as quotes, never
 * interpreted.
 */
import { reachableBaseUrl } from "./dev/hosts";
import type { IntakeQuestion } from "./intake/questions";

export const EXTRACT_PORT = 8804;
/** Server contract: the transcript body is capped at this many characters. */
export const TRANSCRIPT_MAX_CHARS = 2000;
/** A full extract is chunked LLM work; the daemon says it can take up to
 * ninety seconds, so the client waits twice that before giving up. */
const EXTRACT_TIMEOUT_MS = 180_000;

export interface ExtractQuestionSpec {
  id: string;
  kind: "chips" | "single" | "text";
  options: string[] | null;
}

export interface ExtractCandidate {
  values: string[];
  /** The patient's verbatim words this suggestion came from. */
  quote: string;
}

export interface ExtractSuccess {
  ok: true;
  candidates: Record<string, ExtractCandidate>;
  dropped: string[];
  model: string;
}

export type ExtractFailureReason = "unreachable" | "unavailable" | "invalid_response" | "aborted";

export interface ExtractFailure {
  ok: false;
  reason: ExtractFailureReason;
}

export type ExtractResult = ExtractSuccess | ExtractFailure;

/**
 * The pack, as the daemon expects it: option ids for chips/single, null for
 * text.
 *
 * A `text_only` step (files/13 §13) never reaches the extractor. `spokenPack`
 * already drops those before the dialogue lane is built, so this filter is
 * defence in depth — but it is the layer that makes it a TYPE fact rather
 * than a caller's promise, which is what keeps invariant 22's "no numeral
 * reaches any TTS model" from depending on somebody remembering.
 */
export function toQuestionSpecs(pack: readonly IntakeQuestion[]): ExtractQuestionSpec[] {
  return pack
    .filter(
      (q): q is IntakeQuestion & { kind: "chips" | "single" | "text" } =>
        q.kind !== "measure" && q.delivery !== "text_only",
    )
    .map((q) => ({
      id: q.id,
      kind: q.kind,
      options: q.options ? q.options.map((o) => o.id) : null,
    }));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function sanitizeValues(rawValues: unknown[], question: ExtractQuestionSpec): string[] | null {
  const strings = rawValues
    .filter((v): v is string => typeof v === "string")
    .map((v) => v.trim())
    .filter((v) => v.length > 0);
  if (question.options === null) {
    return strings.length > 0 ? strings : null;
  }
  const known = new Set(question.options);
  const filtered: string[] = [];
  for (const value of strings) {
    if (known.has(value) && !filtered.includes(value)) {
      filtered.push(value);
    }
  }
  if (question.kind === "single") {
    // single = exactly one value; an ambiguous candidate is dropped, never guessed
    return filtered.length === 1 ? filtered : null;
  }
  return filtered.length > 0 ? filtered : null;
}

/** Client-side mirror of the server rules — never trust the wire. */
export function validateExtractResponse(
  raw: unknown,
  questions: readonly ExtractQuestionSpec[],
): ExtractResult {
  if (!isRecord(raw) || !isRecord(raw.candidates)) {
    return { ok: false, reason: "invalid_response" };
  }
  const byId = new Map(questions.map((q) => [q.id, q]));
  const candidates: Record<string, ExtractCandidate> = {};
  for (const [qid, entry] of Object.entries(raw.candidates)) {
    const question = byId.get(qid);
    if (
      question === undefined ||
      !isRecord(entry) ||
      typeof entry.quote !== "string" ||
      !Array.isArray(entry.values)
    ) {
      continue;
    }
    const values = sanitizeValues(entry.values, question);
    if (values === null) {
      continue;
    }
    candidates[qid] = { values, quote: entry.quote.trim() };
  }
  const dropped = Array.isArray(raw.dropped)
    ? raw.dropped.filter((d): d is string => typeof d === "string")
    : [];
  const model = typeof raw.model === "string" ? raw.model : "";
  return { ok: true, candidates, dropped, model };
}

export interface ExtractRequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

/** POST /extract on a known base; every failure mode becomes a typed result. */
export async function requestExtract(
  base: string,
  transcript: string,
  pack: string,
  questions: readonly ExtractQuestionSpec[],
  options: ExtractRequestOptions = {},
): Promise<ExtractResult> {
  const { signal, timeoutMs = EXTRACT_TIMEOUT_MS, fetchImpl = fetch } = options;
  if (signal?.aborted) {
    return { ok: false, reason: "aborted" };
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const onAbort = () => controller.abort();
  signal?.addEventListener("abort", onAbort);
  try {
    const res = await fetchImpl(`${base}/extract`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        transcript: transcript.slice(0, TRANSCRIPT_MAX_CHARS),
        pack,
        questions,
      }),
      signal: controller.signal,
    });
    if (!res.ok) {
      return { ok: false, reason: "unavailable" };
    }
    let raw: unknown;
    try {
      raw = await res.json();
    } catch {
      return { ok: false, reason: "invalid_response" };
    }
    return validateExtractResponse(raw, questions);
  } catch {
    return { ok: false, reason: signal?.aborted ? "aborted" : "unreachable" };
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onAbort);
  }
}

/** Probe the candidate bases, then run the extract against the first live one.
 * One short retry rides out the dev daemon's fast-restart window (its
 * supervisor relaunches within ~5s after an external kill); an abort is
 * never retried. */
export async function extractFromCandidates(
  candidates: readonly string[],
  transcript: string,
  pack: string,
  questions: readonly IntakeQuestion[],
  options: ExtractRequestOptions = {},
): Promise<ExtractResult> {
  const specs = toQuestionSpecs(questions);
  const attempt = async (): Promise<ExtractResult> => {
    const base = await reachableBaseUrl(candidates, { fetchImpl: options.fetchImpl });
    if (base === null) {
      return { ok: false, reason: "unreachable" };
    }
    return requestExtract(base, transcript, pack, specs, options);
  };
  const first = await attempt();
  if (first.ok || first.reason === "aborted") {
    return first;
  }
  await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY_MS));
  if (options.signal?.aborted) {
    return { ok: false, reason: "aborted" };
  }
  return attempt();
}

/** Delay before the single retry — longer than the supervisor's restart gap. */
const RETRY_DELAY_MS = 8000;
