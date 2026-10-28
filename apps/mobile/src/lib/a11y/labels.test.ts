import { describe, expect, it } from "vitest";

import { joinParts, labelled, spoken, withContext } from "./labels";

describe("joinParts", () => {
  it("joins peer parts with one separator", () => {
    expect(joinParts("Kardiyoloji", "3 Eylül")).toBe("Kardiyoloji · 3 Eylül");
  });

  it("drops absent and blank parts instead of leaving gaps", () => {
    expect(joinParts("Kardiyoloji", null, "   ", undefined, "3 Eylül")).toBe(
      "Kardiyoloji · 3 Eylül",
    );
  });

  it("returns the empty string when nothing is present", () => {
    expect(joinParts(null, undefined, "  ")).toBe("");
  });

  it("trims each part so layout whitespace never reaches the reader", () => {
    expect(joinParts("  Kardiyoloji  ", " 3 Eylül ")).toBe("Kardiyoloji · 3 Eylül");
  });
});

describe("labelled", () => {
  it("reads label then value", () => {
    expect(labelled("Telefon numaranız", "0532 111 44 55")).toBe(
      "Telefon numaranız: 0532 111 44 55",
    );
  });

  it("degrades to the bare label rather than a dangling colon", () => {
    expect(labelled("Telefon numaranız", null)).toBe("Telefon numaranız");
    expect(labelled("Telefon numaranız", "")).toBe("Telefon numaranız");
  });

  it("keeps a value that is itself joined", () => {
    expect(labelled("Şikâyet süresi", joinParts("İki gün", "Onaylandı"))).toBe(
      "Şikâyet süresi: İki gün · Onaylandı",
    );
  });
});

describe("withContext — SC 2.5.3 Label in Name", () => {
  it("puts the VISIBLE label first so voice control can reach the control", () => {
    const name = withContext("Onaylayın", "Şikâyet süresi");
    expect(name.startsWith("Onaylayın")).toBe(true);
    expect(name).toBe("Onaylayın · Şikâyet süresi");
  });

  it("is the bare visible label when there is no context to add", () => {
    expect(withContext("Onaylayın")).toBe("Onaylayın");
  });
});

describe("spoken — the two-sided transcript", () => {
  it("attributes every turn to its speaker, speaker first", () => {
    expect(spoken("Önvizit", "Ağrınız ne zaman başladı?")).toBe(
      "Önvizit: Ağrınız ne zaman başladı?",
    );
    expect(spoken("Siz", "İki gün önce")).toBe("Siz: İki gün önce");
  });

  it("joins the bubble's own lines under one attribution", () => {
    expect(spoken("Önvizit", "Şunu anladım", "İki gün", "Doğru mu?")).toBe(
      "Önvizit: Şunu anladım · İki gün · Doğru mu?",
    );
  });

  it("still attributes a turn whose body has not arrived yet", () => {
    expect(spoken("Siz", null)).toBe("Siz");
  });
});
