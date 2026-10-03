/**
 * INT-472: the review screen as iOS grouped inset lists. Each note section is
 * one group; this module decides its rows and its footer, so the screen only
 * draws them.
 *
 * - The answer lines come first: they are the content the patient checks.
 * - A carried-fact block follows in the two sections that review one
 *   (INT-256), never elsewhere.
 * - Then the share switch: on until the patient turns it off (02 §5.1),
 *   read-only once the note is sent.
 * - Then the edit rows, which a sent note never shows (it is frozen).
 * - The section's note (medications, device data) is the group's footer.
 *
 * The share summary above Gönder is a metadata group: what leaves, who
 * receives it, until when (02 §5.4), each label over its values.
 */
import { describe, expect, it } from "vitest";

import { t } from "@/lib/i18n";

import type { NoteSection } from "./note";
import { reviewSectionRows, shareSummaryRows } from "./reviewRows";
import type { ShareSummary } from "./share";

function section(id: string, lines: string[] = ["Halsizlik"]): NoteSection {
  return { id, titleKey: "review.section.cc", lines };
}

const OPEN = { shared: true, sent: false } as const;

describe("reviewSectionRows: one grouped list per note section", () => {
  it("puts the answer lines first, then the share switch, then the edit row", () => {
    const { rows } = reviewSectionRows(
      section("chief_complaint", ["Halsizlik", "Baş ağrısı"]),
      OPEN,
    );
    expect(rows.map((row) => row.kind)).toEqual(["line", "line", "share", "edit"]);
    expect(rows[0]).toEqual({ kind: "line", text: "Halsizlik" });
    expect(rows[1]).toEqual({ kind: "line", text: "Baş ağrısı" });
  });

  it("edits reopen the question they came from", () => {
    expect(reviewSectionRows(section("chief_complaint"), OPEN).rows.at(-1)).toEqual({
      kind: "edit",
      target: "complaint",
      labelKey: "review.edit",
    });
    // The history section reopens the duration, and also the patient's own note.
    const hpi = reviewSectionRows(section("hpi"), OPEN).rows.filter((row) => row.kind === "edit");
    expect(hpi).toEqual([
      { kind: "edit", target: "duration", labelKey: "review.edit" },
      { kind: "edit", target: "extra", labelKey: "review.hpi.patientNote" },
    ]);
  });

  it("a section no question produced has no edit row", () => {
    for (const id of ["pmh", "medications", "allergies", "family_social", "measurements"]) {
      const kinds = reviewSectionRows(section(id), OPEN).rows.map((row) => row.kind);
      expect(kinds, id).not.toContain("edit");
    }
  });

  it("the share switch carries the section's state; absent means shared", () => {
    expect(reviewSectionRows(section("pmh"), OPEN).rows).toContainEqual({
      kind: "share",
      shared: true,
      readOnly: false,
    });
    expect(reviewSectionRows(section("pmh"), { shared: false, sent: false }).rows).toContainEqual({
      kind: "share",
      shared: false,
      readOnly: false,
    });
  });

  it("a sent note is frozen: the switch is read-only and no edit row is offered", () => {
    for (const id of ["chief_complaint", "hpi"]) {
      const { rows } = reviewSectionRows(section(id), { shared: true, sent: true });
      expect(
        rows.map((row) => row.kind),
        id,
      ).not.toContain("edit");
      expect(rows.find((row) => row.kind === "share")).toEqual({
        kind: "share",
        shared: true,
        readOnly: true,
      });
    }
  });

  it("near miss: the same section before sending does offer its edit", () => {
    const kinds = reviewSectionRows(section("chief_complaint"), OPEN).rows.map((row) => row.kind);
    expect(kinds).toContain("edit");
  });

  it("the carried-fact block sits in the medications and allergies groups only, after the lines", () => {
    expect(reviewSectionRows(section("medications"), OPEN).rows.map((row) => row.kind)).toEqual([
      "line",
      "facts",
      "share",
    ]);
    expect(reviewSectionRows(section("medications"), OPEN).rows[1]).toEqual({
      kind: "facts",
      factKind: "medication",
    });
    expect(reviewSectionRows(section("allergies"), OPEN).rows[1]).toEqual({
      kind: "facts",
      factKind: "allergy",
    });
    for (const id of ["chief_complaint", "hpi", "pmh", "device_health"]) {
      const kinds = reviewSectionRows(section(id), OPEN).rows.map((row) => row.kind);
      expect(kinds, id).not.toContain("facts");
    }
  });

  it("the section's note is the group's footer", () => {
    expect(reviewSectionRows(section("medications"), OPEN).footerKey).toBe("review.medsNote");
    expect(reviewSectionRows(section("device_health"), OPEN).footerKey).toBe(
      "review.healthProvenance",
    );
    expect(reviewSectionRows(section("chief_complaint"), OPEN).footerKey).toBeNull();
  });
});

describe("shareSummaryRows: the share summary as a metadata group (02 §5.4)", () => {
  const SUMMARY: ShareSummary = {
    sections: ["review.section.cc", "review.section.hpi"],
    recipient: { hospital: "Ankara Şehir Hastanesi", department: "İç Hastalıkları" },
    expiryAnchor: "visit_datetime",
  };

  it("has all three parts, each label over its values", () => {
    expect(shareSummaryRows(SUMMARY)).toEqual([
      {
        label: t("review.consent.sections"),
        values: [t("review.section.cc"), t("review.section.hpi")],
      },
      {
        label: t("review.consent.recipient"),
        values: ["Ankara Şehir Hastanesi · İç Hastalıkları"],
      },
      { label: t("review.consent.until"), values: [t("review.consent.untilValue")] },
    ]);
  });

  it("says so in words when nothing is shared, rather than showing an empty row", () => {
    const rows = shareSummaryRows({ ...SUMMARY, sections: [] });
    expect(rows[0]).toEqual({
      label: t("review.consent.sections"),
      values: [t("review.consent.nothing")],
    });
  });

  it("omits the recipient row when the visit is unknown, and keeps the other two", () => {
    const rows = shareSummaryRows({ ...SUMMARY, recipient: null });
    expect(rows.map((row) => row.label)).toEqual([
      t("review.consent.sections"),
      t("review.consent.until"),
    ]);
  });

  it("states the expiry anchor in words and no clock (02 §2, invariant 22)", () => {
    const until = shareSummaryRows(SUMMARY).at(-1)!;
    expect(until.values.join(" ")).not.toMatch(/\d/);
  });
});
