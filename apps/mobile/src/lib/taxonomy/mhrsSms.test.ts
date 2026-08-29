/**
 * INT-134 — MHRS appointment-SMS paste-parse. Pure text in, structure out:
 * the parser never touches network or storage, and the fixtures below are
 * SYNTHETIC, real-shaped MHRS message bodies (no real PHI anywhere).
 */
import { describe, expect, it } from "vitest";

import { SEED_BRANCHES } from "./branches";
import { parseMhrsSms } from "./mhrsSms";

const parse = (text: string) => parseMhrsSms(text, SEED_BRANCHES);

describe("parseMhrsSms — the standard MHRS confirmation shapes", () => {
  it("reads the ASCII-folded uppercase MHRS shape", () => {
    const parsed = parse(
      "Sayin A*** Y***, 03.09.2026 Persembe saat 14:30 icin ANKARA BILKENT SEHIR " +
        "HASTANESI KARDIYOLOJI poliklinigi randevunuz olusturulmustur. Randevu no: ABC123. MHRS",
    );
    expect(parsed.dateIso).toBe("2026-09-03");
    expect(parsed.time).toBe("14:30");
    expect(parsed.branchId).toBe("kardiyoloji");
    expect(parsed.hospital).toBe("ANKARA BILKENT SEHIR HASTANESI");
  });

  it("reads a Turkish-charset variant with a multi-word branch", () => {
    const parsed = parse(
      "Sayın H*** K***, 15.10.2026 Perşembe saat 09.40 için İSTANBUL EĞİTİM VE ARAŞTIRMA " +
        "HASTANESİ GÖZ HASTALIKLARI polikliniği randevunuz oluşturulmuştur. MHRS",
    );
    expect(parsed.dateIso).toBe("2026-10-15");
    expect(parsed.time).toBe("09:40");
    expect(parsed.branchId).toBe("goz_hastaliklari");
    expect(parsed.hospital).toBe("İSTANBUL EĞİTİM VE ARAŞTIRMA HASTANESİ");
  });

  it("prefers the longest branch name (yan dal over its parent token)", () => {
    const child = parse(
      "Sayin B*** C***, 05.09.2026 saat 10:00 icin IZMIR SEHIR HASTANESI COCUK " +
        "KARDIYOLOJISI randevunuz olusturulmustur. MHRS",
    );
    expect(child.branchId).toBe("cocuk_kardiyolojisi");
    const surgical = parse(
      "Sayin B*** C***, 05.09.2026 saat 10:00 icin IZMIR SEHIR HASTANESI GASTROENTEROLOJI " +
        "CERRAHISI randevunuz olusturulmustur. MHRS",
    );
    expect(surgical.branchId).toBe("gastroenteroloji_cerrahisi");
  });
});

describe("parseMhrsSms — the honest partial results", () => {
  it("an unknown clinic name yields branchId null (the screen offers the picker)", () => {
    const parsed = parse(
      "Sayin D*** E***, 07.09.2026 saat 11:20 icin BURSA DEVLET HASTANESI CILDIYE " +
        "randevunuz olusturulmustur. MHRS",
    );
    expect(parsed.branchId).toBeNull();
    expect(parsed.dateIso).toBe("2026-09-07");
    expect(parsed.hospital).toBe("BURSA DEVLET HASTANESI");
  });

  it("a message without a date yields dateIso null, never an invented one", () => {
    const parsed = parse("NOROLOJI randevunuz ADANA SEHIR HASTANESI icin olusturulmustur. MHRS");
    expect(parsed.dateIso).toBeNull();
    expect(parsed.time).toBeNull();
    expect(parsed.branchId).toBe("noroloji");
  });

  it("an impossible calendar date is refused, not passed through", () => {
    const parsed = parse("31.02.2026 saat 10:00 KARDIYOLOJI randevunuz. MHRS");
    expect(parsed.dateIso).toBeNull();
    expect(parsed.branchId).toBe("kardiyoloji");
  });

  it("arbitrary text parses to all-null and never throws", () => {
    expect(parse("kombi bakim randevunuz icin tesekkurler")).toEqual({
      dateIso: null,
      time: null,
      hospital: null,
      branchId: null,
      branchText: null,
    });
    expect(parse("")).toEqual({
      dateIso: null,
      time: null,
      hospital: null,
      branchId: null,
      branchText: null,
    });
  });

  it("reports the matched clinic text so the screen can echo it", () => {
    const parsed = parse(
      "Sayin F*** G***, 03.09.2026 saat 14:30 icin ANKARA SEHIR HASTANESI ROMATOLOJI " +
        "poliklinigi randevunuz olusturulmustur. MHRS",
    );
    expect(parsed.branchText).toBe("ROMATOLOJI");
    expect(parsed.branchId).toBe("romatoloji");
  });
});
