/**
 * INT-143 — kiosk mode. This barrel re-exports the PURE policy only, so it is
 * safe to import from node-tested code (session.tsx, the specs). The native
 * adapter (nativeKiosk.ts: MDM managed-config read, guided-access probe, idle
 * timer, AppState) is deliberately NOT re-exported here — callers reach it
 * through a lazy `import()`, the same pattern the offline barrel uses for its
 * native backend.
 */
export {
  CLINIC_PIN_MAX_LENGTH,
  CLINIC_PIN_MIN_LENGTH,
  KIOSK_IDLE_WARNING_MS,
  KIOSK_IDLE_WIPE_MS,
  KIOSK_MAX_PIN_FAILURES,
  KIOSK_PIN_KDF_ROUNDS,
  decodeKioskProvisioning,
  hashClinicPin,
  initialKioskMode,
  isKioskProvisioned,
  isWellFormedPin,
  kioskFontScale,
  kioskIdleDue,
  kioskIdleReducer,
  kioskIdleStart,
  kioskReducer,
  kioskSuppressesPersistence,
  mustWipeOn,
  pinLockedOut,
  startKioskIdleClock,
  tamperDetected,
  verifyClinicPin,
  type KioskActivity,
  type KioskEvent,
  type KioskIdleClock,
  type KioskIdleEvent,
  type KioskIdlePhase,
  type KioskIdleState,
  type KioskIdleTimers,
  type KioskLockdown,
  type KioskModeState,
  type KioskPhase,
  type KioskProvisioning,
} from "./kioskState";
