/**
 * Session state for the shell (INT-130/179/193): the signed-in account, the
 * per-visit note state, locally added visits and the active locale.
 * In-memory only — persistence and real auth are INT-131; nothing here may
 * write to disk (patient state on device is a privacy decision that arrives
 * with the consent ledger, not the UI shell).
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
import type { ConsentState, RecordFixture, TestAccount, VisitFixture } from "./dev/accounts";
import { setLocale, type Locale } from "./i18n";
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
  const [notes, setNotes] = useState<Record<string, NoteState>>({});
  const [locale, setLocaleState] = useState<Locale>("tr");
  const [visitSeq, setVisitSeq] = useState(1);
  const [integrity, setIntegrity] = useState<DeviceIntegrity>("unknown");

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

  const signIn = useCallback((next: TestAccount) => {
    setAccount({ ...next, kind: "dev" });
    setConsents({ ...next.consents });
    setExtraVisits([]);
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
    setNotes({});
    setLocale("tr");
    setLocaleState("tr");
  }, []);

  const signOut = useCallback(() => {
    setAccount(null);
    setConsents(null);
    setExtraVisits([]);
    setNotes({});
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

  const switchLocale = useCallback((next: Locale) => {
    setLocale(next);
    setLocaleState(next);
  }, []);

  const visits = useMemo(
    () => (account ? [...account.visits, ...extraVisits] : []),
    [account, extraVisits],
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
      addVisit,
      notes,
      updateNote,
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
