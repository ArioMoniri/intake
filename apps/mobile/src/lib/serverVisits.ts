/**
 * INT-510 — the local→server visit id map.
 *
 * A visit the patient adds on the phone gets a LOCAL id (`v-local-N`,
 * `buildLocalVisit`); a visit from the hospital feed carries the feed's id. The
 * server knows neither: its visits have their own ids, minted by `POST
 * /v1/visits` and found again by `GET /v1/visits`. Before INT-510 the share
 * centre and the Doctor Link put the local id straight into
 * `/v1/visits/{id}/…`, and the server — correctly — refused an id it had never
 * issued.
 *
 * The session holds this map and nothing else does. Every `/v1/visits/*` call
 * starts from a resolver over it, so a screen never has a visit id to misuse:
 * it hands the resolver its route param and gets back the server's id, or
 * `null` when the server has no such visit (nothing was ever sent for it).
 * The map holds ids only — no visit content, nothing written to disk, nothing
 * logged (invariant 6) — and is forgotten on every sign-in, sign-out and wipe.
 */

/**
 * The server's id for a local visit, or null when the server has none.
 * Throws (as the records resolver does) when the server cannot be reached —
 * "we could not ask" is never reported as "there is nothing".
 */
export type ServerVisitResolver = (visitId: string) => Promise<string | null>;

/**
 * The session's resolver: the map first, then the records resolver — which,
 * with `create`, makes the server visit when it is missing.
 */
export type SessionServerVisitResolver = (
  visitId: string,
  options: { create: boolean },
) => Promise<string | null>;

/** Local visit id → server visit id. */
export type ServerVisitMap = Readonly<Record<string, string>>;

/** The map with one more (or one corrected) entry; the input is untouched. */
export function rememberServerVisit(
  map: ServerVisitMap,
  visitId: string,
  serverVisitId: string,
): ServerVisitMap {
  return map[visitId] === serverVisitId ? map : { ...map, [visitId]: serverVisitId };
}
