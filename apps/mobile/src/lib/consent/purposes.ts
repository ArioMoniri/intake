/**
 * The 06 §2 consent-purpose registry, as the UI sees it (INT-132). This is a
 * VIEW of the server registry (packages/intake_platform consent/registry.py),
 * never a fork of it: ids, order, bases and defaults mirror the files/06 §2
 * closed list, and the e2e spec pins the mirror so drift fails in CI.
 *
 * Two deliberate absences:
 * - `share` — a share consent is parameterised per visit ({recipient, visit,
 *   sections, expiry}, asked in Review & send). A bare share toggle on a
 *   settings screen would be the bundled consent 06 §2 forbids.
 * - `lane:acoustic` — 06 §2.4 made it an investigational-device informed
 *   consent form. A device consent is not a toggle, so it has no row here.
 *
 * UI classification (the task's layering, 02 §7):
 * - `toggle` — açık rıza purposes: OFF until the patient grants against a
 *   loaded, hash-bound text. There is no representable pre-tick. `core` is
 *   one of them (INT-537): the server registry makes it açık rıza and visits
 *   and notes require it, so it is granted against its text like the rest —
 *   asked in context, at the first visit — and withdrawn in one tap.
 *   No optional purpose is needed to grant it or to use the service it
 *   covers. Withdrawing it closes every other purpose with it (the server
 *   cascade, which the core text states); re-granting it re-opens none.
 * - `optout` — the two learning purposes: on by default under their stated
 *   non-consent bases, with an opt-out switch and honest basis copy.
 */
import type { MessageKey } from "@/lib/i18n";
import type { ConsentState } from "@/lib/types/account";

export type PurposeId =
  | "core"
  | "voice"
  | "wellbeing"
  | "lane:affect"
  | "lane:linguistic"
  | "documents"
  | "learning:personal"
  | "learning:service_improvement"
  | "satisfaction"
  | "research";

export type LegalBasis = "explicit_consent" | "service_performance" | "deidentified_optout";
export type PurposeUi = "toggle" | "optout";

export interface PurposeDef {
  id: PurposeId;
  basis: LegalBasis;
  ui: PurposeUi;
  /** Mirrors the server registry's default_granted — true ONLY for the two
   * non-consent-basis learning purposes. */
  defaultGranted: boolean;
  /** UI nesting only: both lanes render under voice. Cascade is separate. */
  parent: PurposeId | null;
  /** Purposes a withdrawal of this one drags down (server cascade mirror). */
  cascadeChildren: readonly PurposeId[];
  labelKey: MessageKey;
  /** Who-sees-what summary (layer 2 + row sublabels). */
  whoKey: MessageKey;
  /** Honest lawful-basis copy. */
  basisKey: MessageKey;
  /** Legacy session ConsentState key this purpose mirrors into (the
   * existing visibleTabs gate keeps working through it). */
  sessionKey: keyof ConsentState | null;
}

export const PURPOSES: readonly PurposeDef[] = [
  {
    id: "core",
    basis: "explicit_consent",
    ui: "toggle",
    defaultGranted: false,
    parent: null,
    // The server's dependents_of("core"): a withdrawn service consent leaves
    // nothing to ride on, so every other purpose falls with it — explicit
    // grants revoked, default-on ones opted out (consent/service.py). The
    // core text says so to the patient.
    cascadeChildren: [
      "voice",
      "wellbeing",
      "lane:affect",
      "lane:linguistic",
      "documents",
      "learning:personal",
      "learning:service_improvement",
      "satisfaction",
      "research",
    ],
    labelKey: "consent.core",
    whoKey: "consent.who.core",
    basisKey: "consent.basis.explicit",
    sessionKey: "core",
  },
  {
    id: "voice",
    basis: "explicit_consent",
    ui: "toggle",
    defaultGranted: false,
    parent: null,
    // lane:affect rides the voice stream (06 §2.1) and falls with it;
    // lane:linguistic is text-only and deliberately NOT cascaded.
    cascadeChildren: ["lane:affect"],
    labelKey: "consent.voice",
    whoKey: "consent.who.voice",
    basisKey: "consent.basis.explicit",
    sessionKey: "voice",
  },
  {
    id: "wellbeing",
    basis: "explicit_consent",
    ui: "toggle",
    defaultGranted: false,
    parent: null,
    cascadeChildren: [],
    labelKey: "consent.wellbeing",
    whoKey: "consent.who.wellbeing",
    basisKey: "consent.basis.explicit",
    sessionKey: "wellbeing",
  },
  {
    id: "lane:affect",
    basis: "explicit_consent",
    ui: "toggle",
    defaultGranted: false,
    parent: "voice",
    cascadeChildren: [],
    labelKey: "consent.lane.affect",
    whoKey: "consent.who.laneAffect",
    basisKey: "consent.basis.explicit",
    sessionKey: null,
  },
  {
    id: "lane:linguistic",
    basis: "explicit_consent",
    ui: "toggle",
    defaultGranted: false,
    parent: "voice",
    cascadeChildren: [],
    labelKey: "consent.lane.linguistic",
    whoKey: "consent.who.laneLinguistic",
    basisKey: "consent.basis.explicit",
    sessionKey: null,
  },
  {
    id: "documents",
    basis: "explicit_consent",
    ui: "toggle",
    defaultGranted: false,
    parent: null,
    cascadeChildren: [],
    labelKey: "consent.documents",
    whoKey: "consent.who.documents",
    basisKey: "consent.basis.explicit",
    sessionKey: "documents",
  },
  {
    id: "learning:personal",
    basis: "service_performance",
    ui: "optout",
    defaultGranted: true,
    parent: null,
    cascadeChildren: [],
    labelKey: "consent.learning.personal",
    whoKey: "consent.who.learningPersonal",
    basisKey: "consent.basis.learningPersonal",
    sessionKey: null,
  },
  {
    id: "learning:service_improvement",
    basis: "deidentified_optout",
    ui: "optout",
    defaultGranted: true,
    parent: null,
    cascadeChildren: [],
    labelKey: "consent.learning.service",
    whoKey: "consent.who.learningService",
    basisKey: "consent.basis.learningService",
    sessionKey: null,
  },
  {
    id: "satisfaction",
    basis: "explicit_consent",
    ui: "toggle",
    defaultGranted: false,
    parent: null,
    cascadeChildren: [],
    labelKey: "consent.satisfaction",
    whoKey: "consent.who.satisfaction",
    basisKey: "consent.basis.explicit",
    sessionKey: null,
  },
  {
    id: "research",
    basis: "explicit_consent",
    ui: "toggle",
    defaultGranted: false,
    parent: null,
    cascadeChildren: [],
    labelKey: "consent.research",
    whoKey: "consent.who.research",
    basisKey: "consent.basis.explicit",
    sessionKey: null,
  },
];

const BY_ID = new Map<string, PurposeDef>(PURPOSES.map((p) => [p.id, p]));

/** The closed list: unknown scopes resolve to null, never to a guess. */
export function purposeDef(id: string): PurposeDef | null {
  return BY_ID.get(id) ?? null;
}

/** Route-param form, mirroring the server's filename mapping (`:` → `.`). */
export function purposeParam(id: PurposeId): string {
  return id.replace(/:/g, ".");
}

export function purposeFromParam(param: string): PurposeId | null {
  const candidate = param.replace(/\./g, ":");
  return purposeDef(candidate)?.id ?? null;
}
