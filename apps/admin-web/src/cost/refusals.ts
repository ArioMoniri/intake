/**
 * Cost module refusals (INT-190): what a stale or tampered `GET /admin/cost`
 * body cannot buy. Each is thrown by `renderCostModule` in `./module.ts`.
 */
import { PROFILES } from "./types";

/* ------------------------------------------------------------------ */
/* Refusals — what a stale or tampered payload cannot buy              */
/* ------------------------------------------------------------------ */

/** A cost figure on a component whose price is not configured — the invented zero. */
export class CostFigureWithoutPrice extends Error {
  constructor(where: string) {
    super(
      `refusing to render a cost figure for ${where}: its price is not configured. A figure ` +
        `there — zero included, since zero is the claim that it was free — would be a price ` +
        `nobody supplied (infra/costs/unit-prices.yaml is the only source of money; HB-O8)`,
    );
    this.name = "CostFigureWithoutPrice";
  }
}

/** A cost figure where the usage it multiplies was not observed. */
export class CostFigureWithoutUsage extends Error {
  constructor(where: string, state: string) {
    super(
      `refusing to render a cost figure for ${where}: its usage is '${state}', not observed. ` +
        `An unknown quantity is shown as unknown, never multiplied (invariant 17)`,
    );
    this.name = "CostFigureWithoutUsage";
  }
}

/** A total summed over some of its parts and presented as the whole. */
export class PartialTotalRendered extends Error {
  constructor(where: string) {
    super(
      `refusing to render a total for ${where}: it is incomplete, and a sum over the known ` +
        `parts would be published as the cost and be wrong by exactly the parts it left out`,
    );
    this.name = "PartialTotalRendered";
  }
}

/** A budget verdict the spend and the limit cannot support. */
export class UnsoundBudgetVerdict extends Error {
  constructor(budgetId: string, detail: string) {
    super(
      `refusing to render budget ${budgetId}: ${detail}. A lower bound can prove a budget ` +
        `exceeded and can never prove it kept, and a budget with no limit has no verdict`,
    );
    this.name = "UnsoundBudgetVerdict";
  }
}

/** A price or limit shown without the source and date it came from. */
export class UnsourcedPrice extends Error {
  constructor(where: string) {
    super(
      `refusing to render the value for ${where}: a configured price or limit must carry its ` +
        `source and as_of date, or it is a number nobody can trace`,
    );
    this.name = "UnsourcedPrice";
  }
}

/** A profile outside the closed pair (invariant 19). */
export class UnknownCostProfile extends Error {
  constructor(profile: string) {
    super(
      `refusing to render profile '${profile}': the only profiles are ` +
        `${PROFILES.join(" and ")} (CLAUDE.md invariant 19)`,
    );
    this.name = "UnknownCostProfile";
  }
}

/** An identifier that is not id-shaped — content where only ids belong (invariant 6). */
export class CostContentLeaked extends Error {
  constructor(field: string) {
    super(
      `refusing to render ${field}: it is not id-shaped. This surface carries component, ` +
        `vendor and budget ids only — never prose, a name or a session identifier (invariant 6)`,
    );
    this.name = "CostContentLeaked";
  }
}

/** A state outside its sealed vocabulary — a drifted or tampered body. */
export class UnknownCostState extends Error {
  constructor(field: string, value: string) {
    super(`refusing to render ${field} '${value}': it is not one of the module's sealed states`);
    this.name = "UnknownCostState";
  }
}

/** A currency other than the catalogue's denomination for cost. */
export class CurrencyNotCatalogued extends Error {
  constructor(currency: string) {
    super(
      `refusing to render costs in '${currency}': observability/metrics_catalog.yaml ` +
        `denominates cost_per_session in USD, and a second currency would change what every ` +
        `figure means`,
    );
    this.name = "CurrencyNotCatalogued";
  }
}
