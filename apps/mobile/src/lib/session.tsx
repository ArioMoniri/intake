/**
 * Session state for the shell (INT-130): which account is signed in and what
 * they consented to. In-memory only — persistence and real auth are INT-131;
 * nothing here may write to disk (patient state on device is a privacy
 * decision that arrives with the consent ledger, not the UI shell).
 */
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import type { ConsentState, TestAccount } from "./dev/accounts";
import { emptyNoteState, noteReducer, type NoteAction, type NoteState } from "./intake/note";

export type { RecordFixture, TestAccount } from "./dev/accounts";

export interface Session {
  account: TestAccount | null;
  signIn: (account: TestAccount) => void;
  signOut: () => void;
  /** Per-visit pre-visit note state (in-memory only — INT-179). */
  notes: Record<string, NoteState>;
  updateNote: (visitId: string, action: NoteAction) => void;
}

const SessionContext = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [account, setAccount] = useState<TestAccount | null>(null);
  const [notes, setNotes] = useState<Record<string, NoteState>>({});
  const signIn = useCallback((next: TestAccount) => {
    setAccount(next);
    setNotes({});
  }, []);
  const signOut = useCallback(() => {
    setAccount(null);
    setNotes({});
  }, []);
  const updateNote = useCallback((visitId: string, action: NoteAction) => {
    setNotes((prev) => ({ ...prev, [visitId]: noteReducer(prev[visitId] ?? emptyNoteState(), action) }));
  }, []);
  const value = useMemo(
    () => ({ account, signIn, signOut, notes, updateNote }),
    [account, signIn, signOut, notes, updateNote],
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
