/**
 * Session state for the shell (INT-130/179/193): the signed-in account, the
 * per-visit note state, locally added visits and the active locale.
 * In-memory only — persistence and real auth are INT-131; nothing here may
 * write to disk (patient state on device is a privacy decision that arrives
 * with the consent ledger, not the UI shell).
 */
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import type { ConsentState, TestAccount, VisitFixture } from "./dev/accounts";
import { setLocale, type Locale } from "./i18n";
import { emptyNoteState, noteReducer, type NoteAction, type NoteState } from "./intake/note";
import { buildLocalVisit, type NewVisitInput } from "./visits";

export type { RecordFixture, TestAccount } from "./dev/accounts";

export interface Session {
  account: TestAccount | null;
  signIn: (account: TestAccount) => void;
  signOut: () => void;
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
  const [account, setAccount] = useState<TestAccount | null>(null);
  const [extraVisits, setExtraVisits] = useState<VisitFixture[]>([]);
  const [notes, setNotes] = useState<Record<string, NoteState>>({});
  const [locale, setLocaleState] = useState<Locale>("tr");
  const [visitSeq, setVisitSeq] = useState(1);

  const signIn = useCallback((next: TestAccount) => {
    setAccount(next);
    setExtraVisits([]);
    setNotes({});
    setLocale(next.locale);
    setLocaleState(next.locale);
  }, []);

  const signOut = useCallback(() => {
    setAccount(null);
    setExtraVisits([]);
    setNotes({});
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
      signOut,
      visits,
      addVisit,
      notes,
      updateNote,
      locale,
      switchLocale,
    }),
    [account, signIn, signOut, visits, addVisit, notes, updateNote, locale, switchLocale],
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
