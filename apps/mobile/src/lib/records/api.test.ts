/**
 * INT-229 — records client over the INT-197 document endpoints.
 *
 * What this file pins:
 * - the client-side pre-check MIRRORS the server allow-list (pdf/jpeg/png,
 *   20 MiB) without replacing it — the server stays the enforcer;
 * - upload runs slot-mint (POST, declared sha256 computed from the real
 *   bytes) then byte ingest (PUT through the API — presigned MinIO URLs
 *   point at the server's loopback and are unreachable from a device);
 * - every wire error maps to a TYPED kind (02 §8.2: generic errors, the UI
 *   maps kinds to tr copy) — 403 consent, 413 size, 503 scan, 422 shapes;
 * - a 409 on the download URL is a typed SCANNING state, not an error;
 * - the visit picker rule: exactly one upcoming visit auto-selects,
 *   otherwise the caller shows a chooser.
 */
import { sha256 } from "@noble/hashes/sha2.js";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ALLOWED_DOCUMENT_TYPES,
  MAX_DOCUMENT_BYTES,
  RecordsApiError,
  downloadUrl,
  ensureServerVisit,
  listDocuments,
  pickUploadVisit,
  precheckFile,
  upload,
} from "./api";

const mocks = vi.hoisted(() => {
  class AuthApiError extends Error {
    readonly kind: string;
    readonly retryAfterS: number | null = null;
    constructor(kind: string) {
      super(kind);
      this.kind = kind;
    }
  }
  return {
    authedFetch: vi.fn(),
    AuthApiError,
    fileBytes: { current: new Uint8Array([1, 2, 3]) },
  };
});

vi.mock("@/lib/auth/api", () => ({
  authedFetch: mocks.authedFetch,
  AuthApiError: mocks.AuthApiError,
}));

vi.mock("expo-file-system", () => ({
  File: class {
    async bytes(): Promise<Uint8Array> {
      return mocks.fileBytes.current;
    }
  },
}));

const PDF_BYTES = new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d, 0x31, 0x2e, 0x37]);

function hex(bytes: Uint8Array): string {
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status });
}

afterEach(() => {
  mocks.authedFetch.mockReset();
  mocks.fileBytes.current = new Uint8Array([1, 2, 3]);
});

describe("precheckFile — mirrors the server allow-list, never replaces it", () => {
  it("accepts the three allowed types", () => {
    expect(ALLOWED_DOCUMENT_TYPES).toEqual(["application/pdf", "image/jpeg", "image/png"]);
    for (const mimeType of ALLOWED_DOCUMENT_TYPES) {
      expect(precheckFile({ uri: "file:///a", name: "a", mimeType })).toEqual({
        ok: true,
        contentType: mimeType,
      });
    }
  });

  it("refuses a type outside the list", () => {
    expect(precheckFile({ uri: "file:///a", name: "a.zip", mimeType: "application/zip" })).toEqual({
      ok: false,
      reason: "type",
    });
  });

  it("falls back to the file extension when the picker gives no mime type", () => {
    expect(precheckFile({ uri: "file:///a", name: "tahlil.PDF" })).toEqual({
      ok: true,
      contentType: "application/pdf",
    });
    expect(precheckFile({ uri: "file:///a", name: "belge.bin" })).toEqual({
      ok: false,
      reason: "type",
    });
  });

  it("refuses a file over the 20 MiB cap (server mirror)", () => {
    expect(MAX_DOCUMENT_BYTES).toBe(20 * 1024 * 1024);
    expect(
      precheckFile({
        uri: "file:///a",
        name: "a.pdf",
        mimeType: "application/pdf",
        size: MAX_DOCUMENT_BYTES + 1,
      }),
    ).toEqual({ ok: false, reason: "size" });
  });
});

describe("upload — slot mint then byte ingest through the API", () => {
  it("declares the sha256 of the REAL bytes and PUTs them with the content type", async () => {
    mocks.fileBytes.current = PDF_BYTES;
    mocks.authedFetch
      .mockResolvedValueOnce(
        json(201, {
          id: "doc-1",
          state: "quarantined",
          content_type: "application/pdf",
          sha256: hex(sha256(PDF_BYTES)),
          upload_url: "https://minio.local/quarantine/x",
          expires_s: 300,
        }),
      )
      .mockResolvedValueOnce(
        json(200, { id: "doc-1", state: "clean", sha256: hex(sha256(PDF_BYTES)) }),
      );

    const outcome = await upload("visit-1", {
      uri: "file:///cache/tahlil.pdf",
      name: "tahlil.pdf",
      mimeType: "application/pdf",
    });

    expect(outcome).toEqual({ id: "doc-1", state: "clean" });
    const [mintPath, mintInit] = mocks.authedFetch.mock.calls[0];
    expect(mintPath).toBe("/v1/visits/visit-1/documents");
    expect(JSON.parse(mintInit.body as string)).toEqual({
      content_type: "application/pdf",
      sha256: hex(sha256(PDF_BYTES)),
    });
    const [putPath, putInit] = mocks.authedFetch.mock.calls[1];
    expect(putPath).toBe("/v1/visits/visit-1/documents/doc-1/content");
    expect(putInit.method).toBe("PUT");
    expect(putInit.body).toBeInstanceOf(Uint8Array);
    expect(putInit.headers["Content-Type"]).toBe("application/pdf");
    // no filename crosses the wire in any direction (invariant 6)
    expect(mintInit.body as string).not.toContain("tahlil");
  });

  it("refuses a disallowed type before any network call", async () => {
    await expect(
      upload("visit-1", { uri: "file:///a", name: "a.zip", mimeType: "application/zip" }),
    ).rejects.toMatchObject({ kind: "type" });
    expect(mocks.authedFetch).not.toHaveBeenCalled();
  });

  it("refuses oversized bytes before any network call", async () => {
    mocks.fileBytes.current = new Uint8Array(MAX_DOCUMENT_BYTES + 1);
    await expect(
      upload("visit-1", { uri: "file:///a", name: "a.pdf", mimeType: "application/pdf" }),
    ).rejects.toMatchObject({ kind: "size" });
    expect(mocks.authedFetch).not.toHaveBeenCalled();
  });

  it("maps 413 to a typed size error (the server stays the enforcer)", async () => {
    mocks.authedFetch
      .mockResolvedValueOnce(
        json(201, { id: "doc-1", state: "quarantined", upload_url: "u", expires_s: 300 }),
      )
      .mockResolvedValueOnce(json(413, { error: "too_large" }));
    await expect(
      upload("visit-1", { uri: "file:///a", name: "a.pdf", mimeType: "application/pdf" }),
    ).rejects.toMatchObject({ kind: "size" });
  });

  it("maps 403 consent_required to a typed consent error", async () => {
    mocks.authedFetch.mockResolvedValueOnce(
      json(403, { error: "consent_required", scope: "documents" }),
    );
    await expect(
      upload("visit-1", { uri: "file:///a", name: "a.pdf", mimeType: "application/pdf" }),
    ).rejects.toMatchObject({ kind: "consent" });
  });

  it("maps 503 scan_not_configured to scan_unavailable — fail closed, never fake", async () => {
    mocks.authedFetch
      .mockResolvedValueOnce(
        json(201, { id: "doc-1", state: "quarantined", upload_url: "u", expires_s: 300 }),
      )
      .mockResolvedValueOnce(json(503, { error: "scan_not_configured" }));
    await expect(
      upload("visit-1", { uri: "file:///a", name: "a.pdf", mimeType: "application/pdf" }),
    ).rejects.toMatchObject({ kind: "scan_unavailable" });
  });

  it("a 422 document_rejected is an OUTCOME (state rejected), not a throw", async () => {
    mocks.authedFetch
      .mockResolvedValueOnce(
        json(201, { id: "doc-9", state: "quarantined", upload_url: "u", expires_s: 300 }),
      )
      .mockResolvedValueOnce(json(422, { error: "document_rejected" }));
    await expect(
      upload("visit-1", { uri: "file:///a", name: "a.pdf", mimeType: "application/pdf" }),
    ).resolves.toEqual({ id: "doc-9", state: "rejected" });
  });

  it("surfaces AuthApiError network as a typed network error", async () => {
    mocks.authedFetch.mockRejectedValueOnce(new mocks.AuthApiError("network"));
    await expect(
      upload("visit-1", { uri: "file:///a", name: "a.pdf", mimeType: "application/pdf" }),
    ).rejects.toMatchObject({ kind: "network" });
  });
});

describe("listDocuments — defensive parse of the wire shape", () => {
  it("keeps only rows in the closed state set", async () => {
    mocks.authedFetch.mockResolvedValueOnce(
      json(200, [
        {
          id: "d1",
          state: "quarantined",
          content_type: "application/pdf",
          sha256: "0".repeat(64),
          created_at: "2026-08-28T10:00:00+00:00",
        },
        {
          id: "d2",
          state: "clean",
          content_type: "image/png",
          sha256: "1".repeat(64),
          created_at: "2026-08-28T11:00:00+00:00",
        },
        { id: "d3", state: "weird", content_type: "application/pdf", created_at: "x" },
        "garbage",
      ]),
    );
    const docs = await listDocuments("visit-1");
    expect(docs).toEqual([
      {
        id: "d1",
        state: "quarantined",
        contentType: "application/pdf",
        createdAt: "2026-08-28T10:00:00+00:00",
      },
      {
        id: "d2",
        state: "clean",
        contentType: "image/png",
        createdAt: "2026-08-28T11:00:00+00:00",
      },
    ]);
  });

  it("maps 403 consent_required to the consent kind", async () => {
    mocks.authedFetch.mockResolvedValueOnce(
      json(403, { error: "consent_required", scope: "documents" }),
    );
    await expect(listDocuments("visit-1")).rejects.toBeInstanceOf(RecordsApiError);
    mocks.authedFetch.mockResolvedValueOnce(
      json(403, { error: "consent_required", scope: "documents" }),
    );
    await expect(listDocuments("visit-1")).rejects.toMatchObject({ kind: "consent" });
  });
});

describe("downloadUrl — 409 is a typed scanning state, never an error", () => {
  it("returns the short-TTL url for a clean document", async () => {
    mocks.authedFetch.mockResolvedValueOnce(
      json(200, { url: "https://minio.local/clean/doc", expires_s: 300 }),
    );
    await expect(downloadUrl("visit-1", "doc-1")).resolves.toEqual({
      kind: "url",
      url: "https://minio.local/clean/doc",
    });
  });

  it("maps 409 document_not_scanned to the scanning state", async () => {
    mocks.authedFetch.mockResolvedValueOnce(json(409, { error: "document_not_scanned" }));
    await expect(downloadUrl("visit-1", "doc-1")).resolves.toEqual({ kind: "scanning" });
  });

  it("still throws typed errors for the other refusals", async () => {
    mocks.authedFetch.mockResolvedValueOnce(json(404, { error: "not_found" }));
    await expect(downloadUrl("visit-1", "doc-1")).rejects.toMatchObject({ kind: "not_found" });
  });
});

describe("ensureServerVisit — match first, create only when asked", () => {
  const LOCAL = {
    hospital: "Ankara Şehir Hastanesi",
    department: "İç Hastalıkları",
    date: "2026-09-03",
  };

  it("reuses the server visit that matches hospital+department+date", async () => {
    mocks.authedFetch.mockResolvedValueOnce(
      json(200, [{ id: "sv-1", ...LOCAL, note_status: null }]),
    );
    await expect(ensureServerVisit(LOCAL, { create: true })).resolves.toBe("sv-1");
    expect(mocks.authedFetch).toHaveBeenCalledTimes(1);
  });

  it("creates the visit on the server when no match exists and create is set", async () => {
    mocks.authedFetch
      .mockResolvedValueOnce(json(200, []))
      .mockResolvedValueOnce(json(201, { id: "sv-2", ...LOCAL, note_status: null }));
    await expect(ensureServerVisit(LOCAL, { create: true })).resolves.toBe("sv-2");
    const [path, init] = mocks.authedFetch.mock.calls[1];
    expect(path).toBe("/v1/visits");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual(LOCAL);
  });

  it("returns null instead of creating when create is not set (list is read-only)", async () => {
    mocks.authedFetch.mockResolvedValueOnce(json(200, []));
    await expect(ensureServerVisit(LOCAL, { create: false })).resolves.toBeNull();
    expect(mocks.authedFetch).toHaveBeenCalledTimes(1);
  });
});

describe("pickUploadVisit — the 'exactly one upcoming' rule", () => {
  const v = (id: string, date: string) => ({ id, date });

  it("auto-selects the single upcoming visit", () => {
    const one = v("a", "2026-09-01");
    expect(pickUploadVisit([v("z", "2026-01-01"), one], "2026-08-28")).toEqual({
      kind: "one",
      visit: one,
    });
  });

  it("asks for a chooser when several visits qualify, upcoming first", () => {
    const past = v("p", "2026-01-01");
    const up1 = v("u1", "2026-09-01");
    const up2 = v("u2", "2026-09-09");
    expect(pickUploadVisit([past, up1, up2], "2026-08-28")).toEqual({
      kind: "choose",
      visits: [up1, up2, past],
    });
  });

  it("past-only accounts still get a chooser (results arrive after the visit)", () => {
    const past = v("p", "2026-01-01");
    expect(pickUploadVisit([past], "2026-08-28")).toEqual({ kind: "choose", visits: [past] });
  });

  it("no visits at all → none (the screen shows guidance, never a dead end)", () => {
    expect(pickUploadVisit([], "2026-08-28")).toEqual({ kind: "none" });
  });
});
