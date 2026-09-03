/**
 * Records client (INT-229): typed access to the INT-197 document endpoints
 * over the INT-131 authedFetch (DPoP-bound, base discovered by the shared
 * /healthz host prober on port 8000).
 *
 * Upload is slot-mint (POST, declaring the sha256 computed here from the
 * REAL bytes) followed by byte ingest THROUGH THE API (PUT …/content):
 * the presigned MinIO URL a slot carries points at the server's loopback
 * and is unreachable from a device, so it is never fetched here.
 *
 * The pre-checks mirror the server allow-list (pdf/jpeg/png, 20 MiB) so the
 * patient gets an honest answer before any bytes move — the server stays
 * the enforcer. Errors surface as typed, GENERIC kinds (02 §8.2); no server
 * narrative is rendered, nothing here logs file content or a filename
 * (invariants 6 and 3 by omission: no content ever leaves this module
 * except as the upload body).
 */
import { sha256 } from "@noble/hashes/sha2.js";
import { File } from "expo-file-system";

import { AuthApiError, authedFetch } from "@/lib/auth/api";
import { stripJpegMetadata } from "@/lib/records/jpeg";

/** Server allow-list mirror (intake_platform.documents.ALLOWED_CONTENT_TYPES). */
export const ALLOWED_DOCUMENT_TYPES: readonly string[] = [
  "application/pdf",
  "image/jpeg",
  "image/png",
];

/** Server cap mirror (intake_platform.documents.MAX_DOCUMENT_BYTES). */
export const MAX_DOCUMENT_BYTES = 20 * 1024 * 1024;

export type ScanState = "quarantined" | "clean" | "rejected";

export interface RecordDoc {
  id: string;
  state: ScanState;
  contentType: string;
  createdAt: string;
}

export interface ServerVisit {
  id: string;
  hospital: string;
  department: string;
  /** null when the appointment is not booked yet (INT-134, 02 §2b). */
  date: string | null;
}

export type RecordsErrorKind =
  | "consent"
  | "session"
  | "network"
  | "not_found"
  | "size"
  | "type"
  | "digest"
  | "scan_unavailable"
  | "generic";

export class RecordsApiError extends Error {
  readonly kind: RecordsErrorKind;

  constructor(kind: RecordsErrorKind) {
    super(kind); // the kind IS the message — codes, never narrative
    this.kind = kind;
  }
}

/** What expo-document-picker hands over — name/size may be absent. */
export interface PickedFile {
  uri: string;
  name: string;
  mimeType?: string;
  size?: number;
}

/** What expo-image-picker hands back from a capture (INT-138). */
export interface CapturedAsset {
  uri: string;
  fileName?: string | null;
  mimeType?: string | null;
  fileSize?: number | null;
}

/**
 * A camera capture, as a picked file (INT-138).
 *
 * The capture joins the file picker's path rather than getting one of its own:
 * a second upload path is a second place the server allow-list, the size cap
 * and the metadata strip can each be forgotten. A capture that carries neither
 * a content type nor a name resolves to no type and is refused downstream —
 * fail closed rather than guess what the camera produced.
 */
export function cameraFile(asset: CapturedAsset): PickedFile | null {
  const uri = asset.uri.trim();
  if (uri === "") {
    return null;
  }
  return {
    uri,
    name: asset.fileName?.trim() ?? "",
    mimeType: asset.mimeType ?? undefined,
    size: asset.fileSize ?? undefined,
  };
}

export type Precheck = { ok: true; contentType: string } | { ok: false; reason: "type" | "size" };

const EXTENSION_TYPES: Record<string, string> = {
  pdf: "application/pdf",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
};

/** Honest client-side mirror of the server allow-list and size cap. */
export function precheckFile(file: PickedFile): Precheck {
  let contentType = file.mimeType ?? null;
  if (contentType === null || !ALLOWED_DOCUMENT_TYPES.includes(contentType)) {
    const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
    contentType = EXTENSION_TYPES[extension] ?? null;
  }
  if (contentType === null) {
    return { ok: false, reason: "type" };
  }
  if (file.size !== undefined && file.size > MAX_DOCUMENT_BYTES) {
    return { ok: false, reason: "size" };
  }
  return { ok: true, contentType };
}

// --- wire plumbing ---------------------------------------------------------------------------

async function parseBody(response: Response): Promise<Record<string, unknown>> {
  try {
    return (await response.json()) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function mapError(status: number, body: Record<string, unknown>): RecordsApiError {
  const code = typeof body.error === "string" ? body.error : "";
  if (status === 403 && code === "consent_required") {
    return new RecordsApiError("consent");
  }
  if (status === 404) {
    return new RecordsApiError("not_found");
  }
  if (status === 413 || code === "too_large") {
    return new RecordsApiError("size");
  }
  if (code === "content_type_not_allowed" || code === "content_type_mismatch") {
    return new RecordsApiError("type");
  }
  if (code === "bad_sha256" || code === "digest_mismatch") {
    return new RecordsApiError("digest");
  }
  if (
    code === "scan_not_configured" ||
    code === "scan_failed" ||
    code === "documents_unconfigured"
  ) {
    // no verdict, for any reason: the same honest "we could not check this
    // file yet" to the patient — the distinction is the operator's, not theirs
    return new RecordsApiError("scan_unavailable");
  }
  if (status === 401 || code === "session") {
    return new RecordsApiError("session");
  }
  return new RecordsApiError("generic");
}

/** authedFetch with its transport errors re-typed into this module's kinds. */
async function call(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await authedFetch(path, init);
  } catch (error) {
    if (error instanceof AuthApiError) {
      throw new RecordsApiError(error.kind === "network" ? "network" : "session");
    }
    throw new RecordsApiError("network");
  }
}

const HEX = "0123456789abcdef";

function toHex(bytes: Uint8Array): string {
  let out = "";
  for (const b of bytes) {
    out += HEX[b >> 4] + HEX[b & 0x0f];
  }
  return out;
}

// --- visits (documents hang off a server visit) -----------------------------------------------

const SCAN_STATES: readonly ScanState[] = ["quarantined", "clean", "rejected"];

function parseVisits(raw: unknown): ServerVisit[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  const visits: ServerVisit[] = [];
  for (const item of raw) {
    if (typeof item !== "object" || item === null) {
      continue;
    }
    const entry = item as Record<string, unknown>;
    if (
      typeof entry.id === "string" &&
      typeof entry.hospital === "string" &&
      typeof entry.department === "string" &&
      (typeof entry.date === "string" || entry.date === null)
    ) {
      visits.push({
        id: entry.id,
        hospital: entry.hospital,
        department: entry.department,
        date: entry.date,
      });
    }
  }
  return visits;
}

export async function listServerVisits(): Promise<ServerVisit[]> {
  const response = await call("/v1/visits");
  if (!response.ok) {
    throw mapError(response.status, await parseBody(response));
  }
  return parseVisits(await response.json().catch(() => []));
}

export interface VisitIdentity {
  hospital: string;
  department: string;
  date: string | null;
  /** Taxonomy branch id (INT-134); absent only on a pre-taxonomy visit. */
  branchId?: string | null;
  visitType?: string | null;
}

/**
 * Resolve the server visit a local (session) visit corresponds to, matching
 * on hospital+department+date. With `create`, a missing visit is created via
 * POST /v1/visits; without it the lookup is read-only and resolves to null —
 * listing must never write.
 *
 * A visit that carries a branch is created on the server's TAXONOMY path
 * (branch_id + visit_type, department derived server-side from name_tr); one
 * that does not falls back to the INT-197 free-text department body, which
 * the server still accepts for exactly this case.
 */
export async function ensureServerVisit(
  visit: VisitIdentity,
  { create }: { create: boolean },
): Promise<string | null> {
  const hospital = visit.hospital.trim();
  const department = visit.department.trim();
  const date = visit.date === null ? null : visit.date.trim();
  const existing = await listServerVisits();
  const match = existing.find(
    (v) => v.hospital === hospital && v.department === department && v.date === date,
  );
  if (match !== undefined) {
    return match.id;
  }
  if (!create) {
    return null;
  }
  const branchId = visit.branchId ?? null;
  const payload =
    branchId !== null
      ? { hospital, branch_id: branchId, visit_type: visit.visitType ?? null, date }
      : { hospital, department, date };
  const response = await call("/v1/visits", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await parseBody(response);
  if (!response.ok) {
    throw mapError(response.status, body);
  }
  if (typeof body.id !== "string") {
    throw new RecordsApiError("generic");
  }
  return body.id;
}

/** The "exactly one upcoming visit auto-selects" rule — pure and testable. */
export function pickUploadVisit<V extends { date: string | null }>(
  visits: readonly V[],
  todayIso: string,
): { kind: "one"; visit: V } | { kind: "choose"; visits: V[] } | { kind: "none" } {
  if (visits.length === 0) {
    return { kind: "none" };
  }
  // a dateless visit is upcoming: the patient still intends to attend it
  const upcoming = visits.filter((v) => v.date === null || v.date >= todayIso);
  if (upcoming.length === 1) {
    return { kind: "one", visit: upcoming[0] };
  }
  const past = visits.filter((v) => v.date !== null && v.date < todayIso);
  return { kind: "choose", visits: [...upcoming, ...past] };
}

// --- documents ---------------------------------------------------------------------------------

function parseDocs(raw: unknown): RecordDoc[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  const docs: RecordDoc[] = [];
  for (const item of raw) {
    if (typeof item !== "object" || item === null) {
      continue;
    }
    const entry = item as Record<string, unknown>;
    const state = SCAN_STATES.find((s) => s === entry.state);
    if (
      state === undefined ||
      typeof entry.id !== "string" ||
      typeof entry.content_type !== "string" ||
      typeof entry.created_at !== "string"
    ) {
      continue; // outside the closed shape — never guess a state
    }
    docs.push({
      id: entry.id,
      state,
      contentType: entry.content_type,
      createdAt: entry.created_at,
    });
  }
  return docs;
}

export async function listDocuments(visitId: string): Promise<RecordDoc[]> {
  const response = await call(`/v1/visits/${visitId}/documents`);
  if (!response.ok) {
    throw mapError(response.status, await parseBody(response));
  }
  return parseDocs(await response.json().catch(() => []));
}

export interface UploadOutcome {
  id: string;
  state: "clean" | "rejected";
}

/**
 * Upload one picked file: pre-check → read bytes → declare sha256 (slot
 * mint) → ingest the bytes through the API. A rejected scan is an OUTCOME
 * the caller shows honestly, not an exception. The filename never crosses
 * the wire (invariant 6) — the server key is ids only.
 */
export async function upload(visitId: string, file: PickedFile): Promise<UploadOutcome> {
  const pre = precheckFile(file);
  if (!pre.ok) {
    throw new RecordsApiError(pre.reason);
  }
  // INT-138: a JPEG loses its EXIF/XMP container BEFORE anything else touches
  // it. expo-image-picker's Android exporter copies TAG_GPS_* into the file it
  // hands over, so a photograph of a report would otherwise carry where the
  // patient was standing into the object store — a category of personal data
  // nothing in this repository has declared. The strip comes first because the
  // digest is declared to the server from the bytes that actually travel.
  const picked = await new File(file.uri).bytes();
  const bytes =
    pre.contentType === "image/jpeg" ? stripJpegMetadata(picked) : picked;
  if (bytes.byteLength > MAX_DOCUMENT_BYTES) {
    throw new RecordsApiError("size");
  }
  const digest = toHex(sha256(bytes));

  const mint = await call(`/v1/visits/${visitId}/documents`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content_type: pre.contentType, sha256: digest }),
  });
  const slot = await parseBody(mint);
  if (!mint.ok) {
    throw mapError(mint.status, slot);
  }
  if (typeof slot.id !== "string") {
    throw new RecordsApiError("generic");
  }

  const ingest = await call(`/v1/visits/${visitId}/documents/${slot.id}/content`, {
    method: "PUT",
    headers: { "Content-Type": pre.contentType },
    body: bytes,
  });
  const body = await parseBody(ingest);
  if (ingest.status === 422 && body.error === "document_rejected") {
    return { id: slot.id, state: "rejected" };
  }
  if (!ingest.ok) {
    throw mapError(ingest.status, body);
  }
  return { id: slot.id, state: "clean" };
}

export type DownloadResult = { kind: "url"; url: string } | { kind: "scanning" };

/** Short-TTL download URL; a 409 is the typed SCANNING state, not an error. */
export async function downloadUrl(visitId: string, docId: string): Promise<DownloadResult> {
  const response = await call(`/v1/visits/${visitId}/documents/${docId}/url`);
  const body = await parseBody(response);
  if (response.status === 409) {
    return { kind: "scanning" };
  }
  if (!response.ok) {
    throw mapError(response.status, body);
  }
  if (typeof body.url !== "string") {
    throw new RecordsApiError("generic");
  }
  return { kind: "url", url: body.url };
}

// --- display names (the patient's own data, kept ON DEVICE only) ------------------------------

/**
 * The server stores no filename (invariant 6), so the name the patient
 * picked lives only here, in module memory, for the session — shown back to
 * them, never sent, never logged, gone with the process.
 */
const docNames = new Map<string, string>();

export function rememberDocName(docId: string, name: string): void {
  docNames.set(docId, name);
}

export function docDisplayName(docId: string): string | null {
  return docNames.get(docId) ?? null;
}
