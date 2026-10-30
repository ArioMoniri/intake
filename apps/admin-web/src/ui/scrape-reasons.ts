/**
 * INT-565 — why a scrape-backed figure is not shown, by the API's reason code
 * (`intake_api.admin.console_sources` and `ops_prom`). Shared by the Clinical
 * quality & safety and Security pages; what fills each one is `./fills`.
 * `tr` is the source of truth (invariant 5); `en` mirrors it key for key and
 * the type makes a missing key a compile error.
 */
import type { Lang } from "../ops/copy";

const tr = {
  prometheus_unconfigured: "Prometheus adresi yapılandırılmamış",
  prometheus_misconfigured: "Prometheus adresi geçersiz",
  prometheus_unreachable: "Prometheus'a ulaşılamıyor",
  prometheus_query_error: "Sorgu hatası",
  prometheus_bad_response: "Beklenmeyen yanıt",
  unexpected_label: "Beklenmeyen etiket; gösterilmedi",
  label_not_id_shaped: "Etiket kimlik biçiminde değil; gösterilmedi",
};

const en: Record<keyof typeof tr, string> = {
  prometheus_unconfigured: "No Prometheus address is configured",
  prometheus_misconfigured: "The Prometheus address is not valid",
  prometheus_unreachable: "Prometheus is unreachable",
  prometheus_query_error: "Query error",
  prometheus_bad_response: "Unexpected response",
  unexpected_label: "Unexpected label; not shown",
  label_not_id_shaped: "Label is not id-shaped; not shown",
};

export const SCRAPE_REASONS: Record<Lang, Readonly<Record<string, string>>> = { tr, en };
