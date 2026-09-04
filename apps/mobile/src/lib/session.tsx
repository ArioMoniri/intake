/**
 * Session state for the shell (INT-130/179/193): the signed-in account, the
 * per-visit note state, locally added visits and the active locale.
 *
 * Almost all of it is in-memory — it dies with the process, which is the point:
 * consents are session-local demo mechanics, and the real product mutates them
 * only through the consent ledger (invariant 4). The ONE thing that survives a
 * relaunch is the OTP restore snapshot (INT-131): the tokenized patient id, the
 * MASKED phone and the Acıbadem name + upcoming visits, written to SecureStore
 * (encrypted, device-only, never synced or backed up — auth/sessionSnapshot*),
 * cleared on sign-out. The raw phone is never kept in app state or on disk, so
 * restore rebuilds the account from that masked snapshot rather than by
 * re-reading the feed. No clinical value, no consent grant and no raw number
 * are ever persisted here.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import type { DeviceIntegrity } from "./auth/integrityState";
import type { RestorableSession } from "./auth/sessionSnapshot";
import type { ConsentState, RecordFixture, TestAccount, VisitFixture } from "./dev/accounts";
import { setLocale, type Locale } from "./i18n";
import { offerableAppLocales } from "./i18n/locale";
import type { CarriedFact } from "./intake/carriedFacts";
import { emptyNoteState, noteReducer, type NoteAction, type NoteState } from "./intake/note";
import { buildLocalVisit, type NewVisitInput } from "./visits";

export type { RecordFixture, TestAccount, VisitFixture } from "./dev/accounts";

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

/**
 * Rebuild the signed-in OTP account from a restore snapshot after a relaunch
 * (INT-131). The name prefers the hospital display name and falls back to the
 * masked phone — never the raw number, which is not in the snapshot to reach.
 * A reload is not a fresh grant, so every consent is off exactly as a new
 * signInOtp leaves it (invariant 4): the consent gate re-earns the wellbeing
 * tab in context (INT-132), it is never restored. Pure, so the mapping is
 * pinned without a renderer.
 */
export function accountFromSnapshot(snapshot: RestorableSession): SessionAccount {
  return {
    kind: "otp",
    id: snapshot.patientId,
    name: snapshot.displayName ?? snapshot.maskedPhone,
    ageYears: null,
    locale: "tr",
    consents: { ...OTP_ACCOUNT_CONSENTS },
    visits: [],
    carriedFacts: [],
    records: [],
  };
}

export interface Session {
  account: SessionAccount | null;
  /**
   * False until the one-shot restore attempt (INT-131) has resolved. The entry
   * route waits on it so a session about to restore never flashes the
   * signed-out screen underneath itself.
   */
  hydrated: boolean;
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
  /** Active UI language; tr is the source of truth (invariant 5). */
  locale: Locale;
  switchLocale: (locale: Locale) => void;
}

const SessionContext = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [account, setAccount] = useState<SessionAccount | null>(null);
  const [consents, setConsents] = useState<ConsentState | null>(null);
  const [extraVisits, setExtraVisits] = useState<VisitFixture[]>([]);
  const [apiVisits, setApiVisitsState] = useState<VisitFixture[]>([]);
  // The last-persisted restore snapshot (INT-131), mirrored in memory so a
  // display update rewrites the whole record. Null for a dev fixture or a
  // signed-out shell — neither is restorable.
  const snapshotRef = useRef<RestorableSession | null>(null);
  // True once a real sign-in/out has happened this launch: it makes the async
  // restore below stand down rather than overwrite a live decision.
  const authActedRef = useRef(false);
  // False until the restore attempt resolves (see the mount effect below).
  const [hydrated, setHydrated] = useState(false);
  const [notes, setNotes] = useState<Record<string, NoteState>>({});
  const [locale, setLocaleState] = useState<Locale>("tr");
  const [visitSeq, setVisitSeq] = useState(1);
  const [integrity, setIntegrity] = useState<DeviceIntegrity>("unknown");

  // Persist (or clear, on null) the restore snapshot. The encrypted device
  // write lives in a lazily-imported module — the integrity-probe pattern in
  // this file — so importing session state from node never loads a native
  // module, and a write failure never breaks the flow that triggered it.
  const writeSnapshot = useCallback((next: RestorableSession | null) => {
    snapshotRef.current = next;
    void import("./auth/sessionSnapshotStore")
      .then((store) => (next ? store.saveSessionSnapshot(next) : store.clearSessionSnapshot()))
      .catch(() => {});
  }, []);

  // INT-318 visits fold into the same restore record as they arrive, so a
  // relaunch keeps them (the reload defect this fixes). The reset paths below
  // use the raw setter directly — a reset is not a snapshot write.
  const setApiVisits = useCallback(
    (nextVisits: VisitFixture[]) => {
      setApiVisitsState(nextVisits);
      if (snapshotRef.current) {
        writeSnapshot({ ...snapshotRef.current, visits: nextVisits });
      }
    },
    [writeSnapshot],
  );

  const setDisplayName = useCallback(
    (name: string) => {
      setAccount((prev) => (prev ? { ...prev, name } : prev));
      if (snapshotRef.current) {
        writeSnapshot({ ...snapshotRef.current, displayName: name });
      }
    },
    [writeSnapshot],
  );

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

  // One-shot restore (INT-131): rebuild the signed-in OTP account from the
  // encrypted snapshot so a relaunch keeps the patient, their Acıbadem name and
  // their upcoming visits — without the raw phone, which is never stored. The
  // load is lazy for the same node-testability reason as the probe above, and
  // a live sign-in/out that raced it wins (authActedRef). `hydrated` flips true
  // either way, so the entry route stops waiting.
  useEffect(() => {
    let active = true;
    void import("./auth/sessionSnapshotStore")
      .then((store) => store.loadSessionSnapshot())
      .then((snapshot) => {
        if (active && snapshot !== null && !authActedRef.current) {
          snapshotRef.current = snapshot;
          setAccount(accountFromSnapshot(snapshot));
          setConsents({ ...OTP_ACCOUNT_CONSENTS });
          setApiVisitsState(snapshot.visits);
        }
      })
      .catch(() => {})
      .finally(() => {
        if (active) {
          setHydrated(true);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const signIn = useCallback(
    (next: TestAccount) => {
      authActedRef.current = true;
      setAccount({ ...next, kind: "dev" });
      setConsents({ ...next.consents });
      setExtraVisits([]);
      setApiVisitsState([]);
      setNotes({});
      setLocale(next.locale);
      setLocaleState(next.locale);
      // A dev fixture is not a restorable session: drop any OTP snapshot so a
      // relaunch after using one does not silently restore a real account.
      writeSnapshot(null);
    },
    [writeSnapshot],
  );

  const signInOtp = useCallback((patientId: string, maskedPhone: string) => {
    authActedRef.current = true;
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
    setApiVisitsState([]);
    setNotes({});
    setLocale("tr");
    setLocaleState("tr");
    // Persist the identity restore is built on now — the tokenized id and the
    // masked phone, never the raw number. The Acıbadem name and visits fold
    // into this same record as the sync resolves (setDisplayName/setApiVisits).
    const snapshot: RestorableSession = { patientId, maskedPhone, displayName: null, visits: [] };
    snapshotRef.current = snapshot;
    void import("./auth/sessionSnapshotStore")
      .then((store) => store.saveSessionSnapshot(snapshot))
      .catch(() => {});
  }, []);

  const signOut = useCallback(() => {
    authActedRef.current = true;
    setAccount(null);
    setConsents(null);
    setExtraVisits([]);
    setApiVisitsState([]);
    setNotes({});
    // The restore snapshot is patient data bound to this session: sign-out
    // drops it with the rest (files/10 §2 credential hygiene). tokens.ts
    // clearSession() drops it too for the token-revoked path.
    writeSnapshot(null);
  }, [writeSnapshot]);

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
      hydrated,
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
      locale,
      switchLocale,
    }),
    [
      account,
      hydrated,
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
