/**
 * INT-591 — a release build offers no consent it cannot use.
 *
 * Voice cannot run in a release build, yet İzinleriniz offered the voice and
 * lane:affect consents there: an illusion of choice that records
 * special-category consent evidence for nothing (KVKK m.4 proportionality) and
 * misstates the build's features. In release the grant action is not offered
 * for those two purposes, and the voice group says why; a grant already
 * standing stays visible with its withdraw control, because withdrawal must
 * always be possible (files/06 §2). The dev build is unchanged.
 *
 * No consent text, data category, retention, closed purpose list or server
 * snapshot changes: this is the screen deciding what to offer.
 */
import { describe, expect, it } from "vitest";

import { consentActions, voiceGroupNoteKey } from "./buildCopy";
import {
  applyTexts,
  freshLedger,
  grant,
  seedFromSession,
  viewOf,
  type PurposeView,
  type TextEntry,
} from "./consent/ledger";
import { PURPOSES, type PurposeId } from "./consent/purposes";
import { en } from "./i18n/en";
import { tr } from "./i18n/tr";

const LOADED: TextEntry = {
  status: "loaded",
  text: { version: "syn1", textHash: "f".repeat(64), body: "Deneme metni." },
};
const AT = "2026-10-30T12:00:00Z";

/** Every purpose with a loaded text, nothing granted — every grant is open. */
function openLedger() {
  const texts: Partial<Record<PurposeId, TextEntry>> = {};
  for (const purpose of PURPOSES) {
    texts[purpose.id] = LOADED;
  }
  return applyTexts(freshLedger(), texts);
}

function view(state: ReturnType<typeof openLedger>, id: PurposeId): PurposeView {
  const found = viewOf(state).find((v) => v.id === id);
  if (found === undefined) throw new Error(`fixture: ${id}`);
  return found;
}

/** voice granted against its text, so lane:affect is grantable too. */
function withVoice() {
  return grant(openLedger(), "voice", AT).state;
}

describe("in a release build the voice-only consents cannot be granted", () => {
  it("voice offers no grant action, though the ledger would allow one", () => {
    const voice = view(openLedger(), "voice");
    expect(voice.grantable).toBe(true); // the ledger is unchanged …
    expect(consentActions(voice, "release").grant).toBe(false); // … the screen offers nothing
  });

  it("lane:affect offers no grant action either", () => {
    const affect = view(withVoice(), "lane:affect");
    expect(affect.grantable).toBe(true);
    expect(consentActions(affect, "release").grant).toBe(false);
  });

  it("says why, on the row's own screen and on the group", () => {
    expect(consentActions(view(openLedger(), "voice"), "release").note).toBe(
      "consent.group.voice.release",
    );
    expect(voiceGroupNoteKey("release")).toBe("consent.group.voice.release");
    expect(tr["consent.group.voice.release"]).toBe(
      "Bu sürümde sesli görüşme yok; bu izinler kullanılmaz.",
    );
    expect(en["consent.group.voice.release"].length).toBeGreaterThan(0);
  });
});

describe("near miss: a standing grant can still be withdrawn in release", () => {
  it("a voice grant made before keeps its withdraw control, and stays visible as on", () => {
    const seeded = seedFromSession({
      core: true,
      voice: true,
      wellbeing: false,
      documents: false,
      health: false,
    });
    const voice = view(seeded, "voice");
    expect(voice.display).toBe("on");
    const actions = consentActions(voice, "release");
    expect(actions.withdraw).toBe(true);
    expect(actions.grant).toBe(false);
  });

  it("a lane:affect grant made before keeps its withdraw control", () => {
    const granted = grant(withVoice(), "lane:affect", AT).state;
    expect(consentActions(view(granted, "lane:affect"), "release").withdraw).toBe(true);
  });
});

describe("near miss: nothing else changes", () => {
  it("every other purpose is granted in release exactly as in dev", () => {
    const state = openLedger();
    for (const purpose of PURPOSES) {
      if (purpose.id === "voice" || purpose.id === "lane:affect") continue;
      const v = view(state, purpose.id);
      expect(consentActions(v, "release"), purpose.id).toEqual(consentActions(v, "dev"));
      expect(consentActions(v, "release").note, purpose.id).toBeNull();
    }
  });

  it("the dev build offers the voice grants as before, with no release line", () => {
    expect(consentActions(view(openLedger(), "voice"), "dev")).toEqual({
      grant: true,
      withdraw: false,
      note: null,
    });
    expect(consentActions(view(withVoice(), "lane:affect"), "dev").grant).toBe(true);
    expect(voiceGroupNoteKey("dev")).toBeNull();
  });
});
