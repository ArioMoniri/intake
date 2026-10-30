/**
 * INT-564 — the Experience page's words, `tr` the source of truth (invariant
 * 5); `en` mirrors it key for key. Every figure names its window and cohort
 * size; no target and no verdict sit beside one (invariant 20).
 */
import type { Lang } from "../ops/copy";
import type { RefusalReason, UnavailableReason } from "../ops/load";
import { FILLS } from "../ui/fills";
import type { EmptyCopy } from "../ui/fills";

const tr = {
  title: "Deneyim ve bekleme süreleri",
  unknown: "Bilinmiyor",
  fills: FILLS.tr,
  reasons: {} as Record<string, string>,
  window: "Pencere",
  windowFrom: "Başlangıç günü",
  windowTo: "Bitiş günü",
  windowApply: "Pencereyi uygula",
  measuredAt: "Ölçüm zamanı",
  tiles: {
    window: "Ölçüm penceresi",
    csat: "Memnuniyet (CSAT, 1-5)",
    nps: "Tavsiye (NPS, 0-10)",
    pulse: "Klinisyen nabzı (1-5)",
    filters: "Filtreler",
    sds01: "Bekleme süreleri (SDS-01, toplu)",
  },
  n: "Yanıt sayısı",
  mean: "Ortalama",
  nps: "NPS",
  score: "Puan",
  reason: "Neden",
  count: "Adet",
  suppressed:
    "Yanıt sayısı 10'un altında: kişiler tanınabilir olmasın diye yalnızca sayı gösterilir (k ≥ 10).",
  unavailableFilter: "kullanılamıyor",
  filtersNote:
    "Bu toplamlarda şube, profil ya da klinik boyutu yok; eklemek bir veri envanteri kararıdır. Kiracı oturumdan gelir, sorgudan değil.",
  sds01Note: "Kiracı kapsamlı, yalnızca toplu; klinik, şube, klinisyen ya da hasta sütunu yok.",
  splitLabels: { promoters: "Destekleyen", passives: "Pasif", detractors: "Eleştiren" } as Record<
    string,
    string
  >,
  empties: {
    sds01: {
      title: "Bu pencerede satır yok",
      why: "Bekleme kaynakları kayıt ürettiğinde satırlar burada görünür.",
    },
    scores: {
      title: "Dağılım yok",
      why: "Yanıt sayısı 10'a ulaştığında puan dağılımı burada görünür.",
    },
  } satisfies Record<"sds01" | "scores", EmptyCopy>,
  refusals: {
    no_credentials: "Oturum bilgisi yok; konsola giriş yapın.",
    token_refused: "Oturum doğrulanamadı; yeniden giriş yapın.",
    role_not_permitted: "Bu rol deneyim toplamlarını göremez.",
    source_ip_refused: "Bu ağ adresinden erişilemez.",
    console_unconfigured: "Yönetici konsolu yapılandırılmamış.",
  } satisfies Record<RefusalReason, string>,
  unavailable: {
    api_base_unconfigured: "API adresi yapılandırılmamış.",
    api_unreachable: "API'ye ulaşılamıyor.",
    payload_refused:
      "API'nin yanıtı gösterilmedi: eşiğin altındaki bir grup için rakam, serbest metin ya da hedef taşıyordu.",
  } satisfies Record<UnavailableReason, string>,
};

export type ExperienceCopy = typeof tr;

const en: ExperienceCopy = {
  title: "Experience & wait times",
  unknown: "Unknown",
  fills: FILLS.en,
  reasons: {},
  window: "Window",
  windowFrom: "First day",
  windowTo: "Last day",
  windowApply: "Apply window",
  measuredAt: "Measured at",
  tiles: {
    window: "Measurement window",
    csat: "Satisfaction (CSAT, 1-5)",
    nps: "Recommendation (NPS, 0-10)",
    pulse: "Clinician pulse (1-5)",
    filters: "Filters",
    sds01: "Wait times (SDS-01, aggregate)",
  },
  n: "Responses",
  mean: "Mean",
  nps: "NPS",
  score: "Score",
  reason: "Reason",
  count: "Count",
  suppressed:
    "Fewer than 10 responses: only the count is shown, so no one can be recognised (k ≥ 10).",
  unavailableFilter: "unavailable",
  filtersNote:
    "These aggregates carry no branch, profile or clinic dimension; adding one is a data-inventory decision. The tenant comes from the session, never the query.",
  sds01Note: "Tenant-scoped and aggregate only; no clinic, branch, clinician or patient column.",
  splitLabels: { promoters: "Promoters", passives: "Passives", detractors: "Detractors" },
  empties: {
    sds01: {
      title: "No rows in this window",
      why: "Rows appear here once the wait sources record observations.",
    },
    scores: {
      title: "No distribution",
      why: "The score distribution appears here once there are 10 responses.",
    },
  },
  refusals: {
    no_credentials: "No session credentials; sign in to the console.",
    token_refused: "The session could not be verified; sign in again.",
    role_not_permitted: "This role cannot see experience aggregates.",
    source_ip_refused: "Not reachable from this network address.",
    console_unconfigured: "The admin console is not configured.",
  },
  unavailable: {
    api_base_unconfigured: "The API address is not configured.",
    api_unreachable: "The API is unreachable.",
    payload_refused:
      "The API's answer was not shown: it carried a figure below the floor, free text or a target.",
  },
};

export const COPY: Record<Lang, ExperienceCopy> = { tr, en };
