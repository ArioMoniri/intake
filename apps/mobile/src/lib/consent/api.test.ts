/**
 * INT-587 — the consent loader now also reads the share text.
 *
 * `GET /v1/consents` serves the parameterised share family's text under the
 * bare purpose id `share` (consents.py `_text_lookup_scope`), alongside the
 * purpose texts. Before this issue the loader dropped it, because `share` is
 * not an İzinleriniz row — which is exactly why the app could not grant the
 * consent the server requires to send a note.
 */
import { describe, expect, it, vi } from "vitest";

import { fetchConsentSnapshot } from "./api";

const mocks = vi.hoisted(() => ({ authedFetch: vi.fn() }));
vi.mock("@/lib/auth/api", () => ({ authedFetch: mocks.authedFetch }));

function served(body: unknown): void {
  mocks.authedFetch.mockResolvedValueOnce({
    ok: true,
    status: 200,
    json: async () => body,
  } as unknown as Response);
}

const SHARE_ROW = {
  purpose: "share",
  version: "2026-10-28.syn1",
  text_hash: "4ef98ca6a13f18cebc7fab34eff11f499fbf2049fa34955e048dd6ea1745d9ed",
  body: "Sentetik test metni: …",
};

describe("the share text", () => {
  it("is read from the snapshot's texts, hash and version intact", async () => {
    served({ scopes: [], texts: [SHARE_ROW] });
    const snapshot = await fetchConsentSnapshot();
    expect(snapshot?.shareText).toEqual({
      status: "loaded",
      text: { version: SHARE_ROW.version, textHash: SHARE_ROW.text_hash, body: SHARE_ROW.body },
    });
  });

  it("is absent when the server serves none — never invented", async () => {
    served({ scopes: [], texts: [] });
    expect((await fetchConsentSnapshot())?.shareText).toBeNull();
  });

  it("an empty or unversioned share body is refused, like any other text", async () => {
    served({ scopes: [], texts: [{ ...SHARE_ROW, body: "  " }] });
    expect((await fetchConsentSnapshot())?.shareText).toBeNull();
    served({ scopes: [], texts: [{ ...SHARE_ROW, version: 3 }] });
    expect((await fetchConsentSnapshot())?.shareText).toBeNull();
  });

  it("never becomes a purpose row: the İzinleriniz list stays the closed list", async () => {
    served({ scopes: [{ scope: "share", reason: "granted" }], texts: [SHARE_ROW] });
    const snapshot = await fetchConsentSnapshot();
    expect(snapshot?.scopes).toEqual([]);
    expect(Object.keys(snapshot?.texts ?? {})).toEqual([]);
  });
});
