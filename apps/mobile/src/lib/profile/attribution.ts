/**
 * INT-133 — who is speaking, on the device (files/02 §3, files/06 §6,
 * files/13 §13).
 *
 * The server derives the authoritative value (`intake_platform.profiles`);
 * this module derives the same thing locally so the screen can show the
 * consequences BEFORE a request is made — which sections will go to text,
 * that safeguarding will not be asked, that the note will carry the proxy
 * flag. The client never SENDS `proxy_reported`: it sends the two facts it
 * can know (who holds the device, who is answering) plus the
 * acknowledgement, and the server decides. A client-settable flag would be
 * a client-clearable one.
 *
 * Nothing here decides anything about age. Minors are the server's age gate
 * (INT-223) and its typed 403 — see `./api.ts`.
 */

/** What the person holding the device declares. Mirrors the base pack's
 * `subject_role` slot ("kendim için" / "yakınım adına"). */
export type SubjectRole = "self" | "companion";

/** Who is actually answering. Only meaningful once the role is `companion`. */
export type Speaker = "patient" | "companion";

/** files/02 §3 — three values, not two. */
export type Attribution = "self_report" | "proxy_report" | "assisted_self_report";

/** The order the copy follows; also the order the server declares. */
export const ATTRIBUTIONS: readonly Attribution[] = [
  "self_report",
  "proxy_report",
  "assisted_self_report",
];

export interface AttributionInput {
  role: SubjectRole;
  speaker: Speaker;
  acknowledged: boolean;
  /** Declared by the patient (or observed): someone else is in the room. */
  thirdPartyPresent: boolean;
}

export interface AttributionOutcome {
  attribution: Attribution;
  /** files/06 §6 — derived, never asserted. */
  proxyReported: boolean;
  thirdPartyPresent: boolean;
  /** files/13 §13 — sensitive sections switch to text. */
  sensitiveTextOnly: boolean;
  /** files/13 §13 — with anyone else involved, it is not asked at all. */
  safeguardingAsked: boolean;
  /** False until the companion acknowledges the role. */
  ready: boolean;
}

/** The default session: the patient, alone, in their own words. */
export const SELF_ALONE: AttributionInput = {
  role: "self",
  speaker: "patient",
  acknowledged: false,
  thirdPartyPresent: false,
};

export function resolveAttribution(input: AttributionInput): AttributionOutcome {
  if (input.role === "self") {
    return {
      attribution: "self_report",
      proxyReported: false,
      thirdPartyPresent: input.thirdPartyPresent,
      sensitiveTextOnly: input.thirdPartyPresent,
      safeguardingAsked: !input.thirdPartyPresent,
      ready: true,
    };
  }
  if (input.speaker === "patient") {
    // files/02 §3: the patient's own words on a family member's device. Not
    // a proxy answer — but a third party is present by definition, which is
    // the whole reason this value exists.
    return {
      attribution: "assisted_self_report",
      proxyReported: false,
      thirdPartyPresent: true,
      sensitiveTextOnly: true,
      safeguardingAsked: false,
      ready: input.acknowledged,
    };
  }
  return {
    attribution: "proxy_report",
    proxyReported: true,
    thirdPartyPresent: input.thirdPartyPresent,
    sensitiveTextOnly: true,
    safeguardingAsked: false,
    ready: input.acknowledged,
  };
}

/** The wire shape `POST /v1/visits` accepts. `proxy_reported` is absent by
 * design — it is the server's conclusion, not the client's claim. */
export interface AttributionBody {
  role: SubjectRole;
  speaker: Speaker;
  acknowledged: boolean;
  third_party_present: boolean;
}

export function attributionBody(input: AttributionInput): AttributionBody {
  return {
    role: input.role,
    speaker: input.speaker,
    acknowledged: input.acknowledged,
    third_party_present: input.thirdPartyPresent,
  };
}
