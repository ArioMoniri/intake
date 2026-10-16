/**
 * INT-510 — the session's outbox: where a tapped Gönder becomes a PUT.
 *
 * A note whose `delivery` is `sending` is sent once (`inFlight` stops a
 * re-render, or React's double-invoked effects, from doubling the request).
 * The transport (./noteSendClient) is reached through a lazy `import()` so the
 * session stays node-importable — the records resolver it reuses reads picked
 * files through a native module. The outcome lands only on the note it was
 * for (`settleSend`), and only if no sign-in, sign-out, wipe or kiosk switch
 * bumped the generation while the request was out; the server id it carries
 * is remembered in the session's map.
 *
 * A queued send waits where every note already waits — the sealed draft
 * mirror (INT-142) persists `delivery` with the rest of the note — and is put
 * back in flight after `SEND_RETRY_MS`, never in a tight loop. A send the
 * server refused is not retried behind the patient's back: Gönder again is
 * theirs to press. Nothing here logs (invariant 6).
 */
import {
  useEffect,
  useRef,
  type Dispatch,
  type MutableRefObject,
  type SetStateAction,
} from "react";

import type { SessionKind } from "../profile/badge";
import { rememberServerVisit, type ServerVisitMap } from "../serverVisits";
import type { VisitFixture } from "../types/account";
import type { NoteAccount, NoteState } from "./note";
import {
  SEND_RETRY_MS,
  hasQueuedSend,
  retryQueuedSends,
  sendsDue,
  settleSend,
  type SendOutcome,
} from "./noteSend";

export interface NoteOutboxInput {
  account: (NoteAccount & SessionKind) | null;
  notes: Record<string, NoteState>;
  setNotes: Dispatch<SetStateAction<Record<string, NoteState>>>;
  visitsRef: MutableRefObject<VisitFixture[]>;
  serverVisits: MutableRefObject<ServerVisitMap>;
  sendGeneration: MutableRefObject<number>;
}

/** A transport that could not even load is a send that waits, not one that failed. */
const UNLOADED: SendOutcome = { kind: "queued", serverVisitId: null };

export function useNoteOutbox({
  account,
  notes,
  setNotes,
  visitsRef,
  serverVisits,
  sendGeneration,
}: NoteOutboxInput): void {
  // One set per generation: a request still out for the previous patient must
  // not hold back the same visit id in the next session.
  const inFlight = useRef({ generation: -1, visits: new Set<string>() });

  useEffect(() => {
    if (account === null) {
      return;
    }
    const generation = sendGeneration.current;
    if (inFlight.current.generation !== generation) {
      inFlight.current = { generation, visits: new Set<string>() };
    }
    const flights = inFlight.current.visits;
    for (const visitId of sendsDue(notes, flights)) {
      const note = notes[visitId];
      const visit = visitsRef.current.find((v) => v.id === visitId) ?? null;
      flights.add(visitId);
      void import("./noteSendClient")
        .then((client) =>
          client.deliverVisitNote({
            note,
            account,
            visit,
            knownServerVisitId: serverVisits.current[visitId] ?? null,
          }),
        )
        .catch(() => UNLOADED)
        .then((outcome) => {
          if (generation !== sendGeneration.current) {
            return;
          }
          if (outcome.serverVisitId !== null) {
            serverVisits.current = rememberServerVisit(
              serverVisits.current,
              visitId,
              outcome.serverVisitId,
            );
          }
          setNotes((prev) => settleSend(prev, visitId, outcome));
        })
        .finally(() => {
          flights.delete(visitId);
        });
    }
  }, [notes, account, setNotes, visitsRef, serverVisits, sendGeneration]);

  useEffect(() => {
    if (!hasQueuedSend(notes)) {
      return;
    }
    const timer = setTimeout(() => setNotes(retryQueuedSends), SEND_RETRY_MS);
    return () => clearTimeout(timer);
  }, [notes, setNotes]);
}
