/**
 * INT-142 — offline intake drafts: encryption at rest, a deterministic sync
 * conflict rule, and the airplane-mode-tolerant pass that ties them together.
 * The pure halves (envelope, reconcile, draftStore, sync) are node-testable;
 * the native backend is loaded lazily by callers so this barrel stays safe to
 * import anywhere.
 */
export {
  DraftDecryptError,
  ENVELOPE_VERSION,
  IV_BYTES,
  KEY_BYTES,
  isEncryptedEnvelope,
  openEnvelope,
  sealEnvelope,
  type DraftDecryptKind,
  type EncryptedEnvelope,
} from "./envelope";
export {
  reconcile,
  type DraftMeta,
  type DraftRecord,
  type Resolution,
  type SyncOutcome,
} from "./reconcile";
export {
  conflictBlobId,
  loadAllDrafts,
  loadDraft,
  persistConflictCopy,
  persistDraft,
  removeDraft,
  shredAllDrafts,
  type DraftBackend,
  type DraftBlobStore,
  type DraftVault,
} from "./draftStore";
export { syncVisit, type DraftTransport, type SyncResult } from "./sync";
