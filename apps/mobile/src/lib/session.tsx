/**
 * Session state for the shell (INT-130/179/193): the signed-in account, the
 * per-visit note state, locally added visits and the active locale.
 *
 * INT-142 adds offline draft resilience: the per-visit note is the working
 * copy, and every change is mirrored to the ENCRYPTED-at-rest draft store
 * (src/lib/intake/offline) so a draft survives an app restart with no network.
 * The native at-rest calls (keychain key custody + encrypted filesystem blobs)
 * live only in that module and are reached through a lazy `import()`, so this
 * provider stays node-importable and holds no plaintext draft itself. A draft
 * is typed/structured text only — raw audio never touches this path
 * (invariant 3) — and sign-out crypto-shreds every draft and its key.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { DeviceIntegrity } from "./auth/integrityState";
import { setLocale, type Locale } from "./i18n";
import { offerableAppLocales } from "./i18n/locale";
import type { CarriedFact } from "./intake/carriedFacts";
import { emptyNoteState, noteReducer, type NoteAction, type NoteState } from "./intake/note";
import { kioskSuppressesPersistence } from "./kiosk";
import type { ConsentState, RecordFixture, TestAccount, VisitFixture } from "./types/account";
import { buildLocalVisit, type NewVisitInput } from "./visits";

export type { RecordFixture, TestAccount, VisitFixture } from "./types/account";

/**
 * The signed-in account the shell renders. Two kinds exist honestly side by
 * side: `dev` wraps an INT-130 synthetic fixture, `otp` is a REAL account
 * created through phone verification (INT-131) — it starts with no visits,
 * no records and ageYears null (nothing invented), and with EVERY consent
 * off: consents arrive in context via INT-132/INT-038, never as a side
 * effect of signing in.
 */
export interface SessionAccount {
  kind: "dev" | "otp";
  id: string;
  name: string;
  ageYears: number | null;
  locale: Locale;
  consents: ConsentState;
  visits: VisitFixture[];
  /**
   * Facts carried from earlier visits (INT-247). A real (`otp`) account is
   * created with none: nothing enters a session that did not come out of
   * that patient's own confirmed history, and nothing here is current until
   * the visit's own review says so (invariant 12).
   */
  carriedFacts: CarriedFact[];
  records: RecordFixture[];
}

const OTP_ACCOUNT_CONSENTS: ConsentState = {
  core: false,
  voice: false,
  wellbeing: false,
  documents: false,
  health: false,
};

export interface Session {
  account: SessionAccount | null;
  signIn: (account: TestAccount) => void;
  /** INT-131: sign in the freshly verified patient (masked phone as the
   * display name — the full number is never kept in app state). */
  signInOtp: (patientId: string, maskedPhone: string) => void;
  signOut: () => void;
  /** Jailbreak/root soft signal (10 §4): compromised → typed + warn. */
  integrity: DeviceIntegrity;
  /**
   * Live consent state, seeded from the account fixture on sign-in.
   * Session-local DEMO mechanics on synthetic accounts: the real product
   * mutates consents only through the versioned consent ledger (invariant 4,
   * INT-060s); this exists so the consent gate is demonstrable — flipping
   * wellbeing off removes the tab in front of you.
   */
  consents: ConsentState | null;
  setConsent: (key: keyof ConsentState, on: boolean) => void;
  /** Fixture visits + locally created ones, additions last. */
  visits: VisitFixture[];
  /** INT-318: replace the API-sourced upcoming visits (from the Acibadem feed). */
  setApiVisits: (visits: VisitFixture[]) => void;
  /** INT-318: the matched patient's display name from the hospital feed. */
  setDisplayName: (name: string) => void;
  addVisit: (input: NewVisitInput) => VisitFixture;
  /** Per-visit pre-visit note state (in-memory only — INT-179). */
  notes: Record<string, NoteState>;
  updateNote: (visitId: string, action: NoteAction) => void;
  /**
   * Kiosk mode (INT-143): a shared clinic device. While active, no draft is
   * persisted (the offline store is bypassed and its blobs crypto-shredded),
   * and the session is wiped between patients. Entering and leaving are gated
   * by the staff-held clinic PIN in KioskGate — never patient-reachable, and
   * never set here without that check.
   */
  kioskActive: boolean;
  setKioskActive: (on: boolean) => void;
  /**
   * Clear every trace of the current patient — the in-memory notes and any
   * locally created visits — and crypto-shred the offline drafts. This is the
   * 60 s idle / background wipe (INT-143) so the next patient inherits nothing.
   */
  wipeSession: () => void;
  /** Active UI language; tr is the source of truth (invariant 5). */
  locale: Locale;
  switchLocale: (locale: Locale) => void;
}

const SessionContext = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [account, setAccount] = useState<SessionAccount | null>(null);
  const [consents, setConsents] = useState<ConsentState | null>(null);
  const [extraVisits, setExtraVisits] = useState<VisitFixture[]>([]);
  const [apiVisits, setApiVisits] = useState<VisitFixture[]>([]);
  const setDisplayName = useCallback((name: string) => {
    setAccount((prev) => (prev ? { ...prev, name } : prev));
  }, []);
  const [notes, setNotes] = useState<Record<string, NoteState>>({});
  const [locale, setLocaleState] = useState<Locale>("tr");
  const [visitSeq, setVisitSeq] = useState(1);
  const [integrity, setIntegrity] = useState<DeviceIntegrity>("unknown");
  // INT-143 — kiosk mode. Off by default; KioskGate flips it on only after the
  // clinic PIN verifies against the MDM-provisioned hash.
  const [kioskActive, setKioskActiveState] = useState(false);

  useEffect(() => {
    // lazy: the probe touches expo-device; loading it only when the
    // provider actually mounts keeps session state node-testable
    let mounted = true;
    void import("./auth/integrity").then(async (probe) => {
      const state = await probe.checkDeviceIntegrity();
      if (mounted) {
        setIntegrity(state);
      }
    });
    return () => {
      mounted = false;
    };
  }, []);

  // INT-142 — restore this account's encrypted drafts after an app restart.
  // In-memory edits win over the disk copy, so a live session is never clobbered
  // by a stale hydrate. Scoped to the account: another patient's drafts (should
  // any survive an un-signed-out restart) are filtered out, not surfaced.
  const accountId = account?.id ?? null;
  useEffect(() => {
    if (accountId === null) {
      return;
    }
    let mounted = true;
    void import("./intake/offline/sessionDrafts")
      .then((offline) => offline.hydrateAccountDrafts(accountId))
      .then((restored) => {
        if (mounted && Object.keys(restored).length > 0) {
          setNotes((prev) => ({ ...restored, ...prev }));
        }
      })
      .catch(() => {
        // no drafts, or the store is unavailable: the session simply starts empty
      });
    return () => {
      mounted = false;
    };
  }, [accountId]);

  // INT-142 — mirror every note change to the encrypted-at-rest draft store.
  // Fire-and-forget: a failed write leaves the working copy untouched, and
  // nothing here logs an id or a value (invariant 6).
  useEffect(() => {
    if (accountId === null) {
      return;
    }
    // INT-143 — no persistence in kiosk mode: a shared clinic device never
    // writes a draft or answer to disk. The offline mirror is bypassed
    // entirely while the kiosk is active (invariant 3 reinforced for the
    // typed draft, invariant 6 no ids in logs).
    if (kioskSuppressesPersistence(kioskActive)) {
      return;
    }
    let mounted = true;
    const entries = Object.entries(notes);
    if (entries.length === 0) {
      return;
    }
    void import("./intake/offline/sessionDrafts")
      .then((offline) => {
        if (!mounted) {
          return;
        }
        for (const [visitId, note] of entries) {
          void offline.persistNoteDraft(accountId, visitId, note).catch(() => {});
        }
      })
      .catch(() => {});
    return () => {
      mounted = false;
    };
  }, [notes, accountId, kioskActive]);

  const signIn = useCallback((next: TestAccount) => {
    setAccount({ ...next, kind: "dev" });
    setConsents({ ...next.consents });
    setExtraVisits([]);
    setApiVisits([]);
    setNotes({});
    setLocale(next.locale);
    setLocaleState(next.locale);
  }, []);

  const signInOtp = useCallback((patientId: string, maskedPhone: string) => {
    setAccount({
      kind: "otp",
      id: patientId,
      name: maskedPhone,
      ageYears: null,
      locale: "tr",
      consents: { ...OTP_ACCOUNT_CONSENTS },
      visits: [],
      carriedFacts: [],
      records: [],
    });
    setConsents({ ...OTP_ACCOUNT_CONSENTS });
    setExtraVisits([]);
    setApiVisits([]);
    setNotes({});
    setLocale("tr");
    setLocaleState("tr");
  }, []);

  const signOut = useCallback(() => {
    setAccount(null);
    setConsents(null);
    setExtraVisits([]);
    setApiVisits([]);
    setNotes({});
    // INT-583: this device stops being told about new sign-ins to the
    // account it just left, and then its session ends on the server too
    // (review round four): its refresh family, its push token and its place
    // among the account's known devices, so its next sign-in is new and the
    // other devices are told. The token goes first, while the session still
    // signs. Best-effort and lazy, like the shred below: the native modules
    // stay out of node imports, and sign-out never waits on the network.
    void import("./push/native")
      .then((push) => push.forgetPushRegistration())
      .catch(() => {
        // the registration stays on the server; the session's end drops it
      })
      .then(() => import("./sessions/native"))
      .then((sessions) => sessions.endThisDeviceSession())
      .catch(() => {
        // the session ends at its expiry instead; nothing to show the patient
      });
    // INT-142: sign-out crypto-shreds every persisted draft and the DEK, so
    // nothing readable survives the session. Lazy so node import stays clean.
    void import("./intake/offline/sessionDrafts")
      .then((offline) => offline.shredDrafts())
      .catch(() => {
        // best-effort hygiene; never surface a native error to the UI
      });
  }, []);

  const setConsent = useCallback((key: keyof ConsentState, on: boolean) => {
    setConsents((prev) => (prev === null ? prev : { ...prev, [key]: on }));
  }, []);

  const addVisit = useCallback(
    (input: NewVisitInput): VisitFixture => {
      const visit = buildLocalVisit(input, visitSeq);
      setVisitSeq((n) => n + 1);
      setExtraVisits((prev) => [...prev, visit]);
      return visit;
    },
    [visitSeq],
  );

  const updateNote = useCallback((visitId: string, action: NoteAction) => {
    setNotes((prev) => ({
      ...prev,
      [visitId]: noteReducer(prev[visitId] ?? emptyNoteState(), action),
    }));
  }, []);

  // INT-143 — the kiosk wipe: drop every trace of the current patient and
  // crypto-shred the offline drafts (reusing INT-142's shred). Fire-and-forget
  // like the offline mirror; nothing here logs an id or a value (invariant 6).
  const wipeSession = useCallback(() => {
    setNotes({});
    setExtraVisits([]);
    void import("./intake/offline/sessionDrafts")
      .then((offline) => offline.shredDrafts())
      .catch(() => {
        // best-effort hygiene; never surface a native error to the UI
      });
  }, []);

  // INT-143 — enter/leave kiosk mode. KioskGate calls this only after the
  // clinic PIN verifies. Entering shreds anything already at rest so the shared
  // device starts clean; the no-persistence gate above keeps it that way.
  const setKioskActive = useCallback((on: boolean) => {
    setKioskActiveState(on);
    if (on) {
      setNotes({});
      void import("./intake/offline/sessionDrafts")
        .then((offline) => offline.shredDrafts())
        .catch(() => {});
    }
  }, []);

  // INT-296 — the ONE explicit act that changes a session's language, and the
  // only one. It goes through the registry rather than trusting its caller: a
  // locale the chooser should never have rendered must not become the session
  // language just because something rendered it. Nothing infers a language
  // from speech anywhere on this path.
  const switchLocale = useCallback((next: Locale) => {
    if (!offerableAppLocales().includes(next)) {
      return;
    }
    setLocale(next);
    setLocaleState(next);
  }, []);

  const visits = useMemo(
    () => (account ? [...apiVisits, ...account.visits, ...extraVisits] : []),
    [account, apiVisits, extraVisits],
  );

  const value = useMemo(
    () => ({
      account,
      signIn,
      signInOtp,
      signOut,
      integrity,
      consents,
      setConsent,
      visits,
      setApiVisits,
      setDisplayName,
      addVisit,
      notes,
      updateNote,
      kioskActive,
      setKioskActive,
      wipeSession,
      locale,
      switchLocale,
    }),
    [
      account,
      signIn,
      signInOtp,
      signOut,
      integrity,
      consents,
      setConsent,
      visits,
      addVisit,
      notes,
      updateNote,
      kioskActive,
      setKioskActive,
      wipeSession,
      locale,
      switchLocale,
    ],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const ctx = useContext(SessionContext);
  if (ctx === null) {
    throw new Error("useSession must be used inside SessionProvider");
  }
  return ctx;
}

/** Tab ids in rail order (02 §4). */
export type TabId = "today" | "visits" | "records" | "wellbeing" | "me";

/**
 * The consent-gated tab rule (02 §4): wellbeing exists on screen only after
 * the wellbeing consent is ON. Pure so the rule is testable without React.
 */
export function visibleTabs(consents: ConsentState | null): TabId[] {
  const base: TabId[] = ["today", "visits", "records"];
  if (consents?.wellbeing) {
    base.push("wellbeing");
  }
  base.push("me");
  return base;
}
