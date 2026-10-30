/**
 * INT-565 — the Clinical quality & safety page's words, `tr` the source of
 * truth (invariant 5); `en` mirrors it key for key. Counts and ids, no verdict
 * beside a figure and no rate without a corpus and a date (invariant 20).
 */
import type { Lang } from "../ops/copy";
import type { RefusalReason, UnavailableReason } from "../ops/load";
import { FILLS, type EmptyCopy } from "../ui/fills";
import { SCRAPE_REASONS } from "../ui/scrape-reasons";

const tr = {
  title: "Klinik kalite ve güvenlik",
  unknown: "Bilinmiyor",
  fills: FILLS.tr,
  reasons: SCRAPE_REASONS.tr,
  bands: { routing: "Triyaj ve PolicyGuard", review: "Yanlış RED incelemesi", notes: "Notlar" },
  tiles: {
    triage: "Triyaj olayları",
    policyguard: "PolicyGuard engellemeleri",
    falseRed: "Yanlış RED kuyruğu",
    acceptance: "Branşa göre not kabulü",
  },
  metric: "Ölçüm",
  status: "Katalog durumu",
  level: "Düzey",
  count: "Adet",
  producedBy: "Üreten",
  candidateCap: "LLM aday üst sınırı",
  triageNote:
    "RED, YELLOW ve GREEN yalnızca kural motorunca üretilir. Bir dil modeli en çok YELLOW_REVIEW düzeyinde aday bayrak ekleyebilir.",
  window: "Pencere",
  className: "Sınıf",
  policyNote: "Hastaya giden metinden düşürülen cümleler, ihlal sınıfına göre.",
  queue: "Kuyruk",
  enqueueScope: "Kuyruğa alma amacı",
  reviewers: "İnceleyen roller",
  contentRead: "İçerik okuma",
  contentRefused: "reddedilir",
  blocker: "Açık engel",
  falseRedNote:
    "Kuyruk yalnızca işaretçi tutar ve RED'i asla düşürmez; klinisyen ek not kaydeder. Kalemin arkasındaki hasta içeriği personele açılmaz.",
  item: "Kalem",
  rule: "Kural",
  branch: "Branş",
  created: "Oluşturulma",
  review: "İnceleme",
  delivered: "Teslim edilen",
  accepted: "Kabul edilen",
  rate: "Ölçüm",
  noMeasurement: "ölçüm yok",
  acceptanceNote:
    "Kabul edilen ya da düzeltilen notların teslim edilenlere oranı bir ölçümdür; yalnızca adlandırılmış bir derlem ve tarihle gösterilir.",
  empties: {
    items: {
      title: "Kuyrukta kalem yok",
      why: "Bir klinisyen tetiklenen bir RED'i incelemeye aldığında burada görünür.",
    },
    levels: {
      title: "Düzey yok",
      why: "Triyaj düzeyleri kural motorundan okunduğunda burada görünür.",
    },
    acceptance: {
      title: "Branş yok",
      why: "Ön görüşme branşları taksonomiden okunduğunda burada görünür.",
    },
    classes: {
      title: "Sınıf yok",
      why: "PolicyGuard ihlal sınıfları okunduğunda burada görünür.",
    },
  } satisfies Record<"items" | "levels" | "acceptance" | "classes", EmptyCopy>,
  refusals: {
    no_credentials: "Oturum bilgisi yok; konsola giriş yapın.",
    token_refused: "Oturum doğrulanamadı; yeniden giriş yapın.",
    role_not_permitted:
      "Bu rol klinik kalite modülünü göremez: sayılar tüm kiracıların toplamıdır.",
    source_ip_refused: "Bu ağ adresinden erişilemez.",
    console_unconfigured: "Yönetici konsolu yapılandırılmamış.",
  } satisfies Record<RefusalReason, string>,
  unavailable: {
    api_base_unconfigured: "API adresi yapılandırılmamış.",
    api_unreachable: "API'ye ulaşılamıyor.",
    payload_refused:
      "API'nin yanıtı gösterilmedi: kural motoru dışından bir triyaj sayısı, RED'i düşüren bir kalem, serbest metin ya da kazınmamış bir sayı taşıyordu.",
  } satisfies Record<UnavailableReason, string>,
};

export type QualitySafetyCopy = typeof tr;

const en: QualitySafetyCopy = {
  title: "Clinical quality & safety",
  unknown: "Unknown",
  fills: FILLS.en,
  reasons: SCRAPE_REASONS.en,
  bands: { routing: "Triage and PolicyGuard", review: "False-RED review", notes: "Notes" },
  tiles: {
    triage: "Triage events",
    policyguard: "PolicyGuard blocks",
    falseRed: "False-RED queue",
    acceptance: "Note acceptance by specialty",
  },
  metric: "Metric",
  status: "Catalogue status",
  level: "Level",
  count: "Count",
  producedBy: "Produced by",
  candidateCap: "LLM candidate ceiling",
  triageNote:
    "RED, YELLOW and GREEN are produced by the rules engine alone. A language model may add candidate flags up to YELLOW_REVIEW at most.",
  window: "Window",
  className: "Class",
  policyNote: "Sentences withheld from patient-facing text, by violation class.",
  queue: "Queue",
  enqueueScope: "Enqueue purpose",
  reviewers: "Reviewer roles",
  contentRead: "Content read",
  contentRefused: "refused",
  blocker: "Open blocker",
  falseRedNote:
    "The queue holds pointers and never downgrades a RED; a clinician records an annotation. The patient content behind an item is not opened to staff.",
  item: "Item",
  rule: "Rule",
  branch: "Branch",
  created: "Created",
  review: "Review",
  delivered: "Delivered",
  accepted: "Accepted",
  rate: "Measurement",
  noMeasurement: "no measurement",
  acceptanceNote:
    "Accepted or edited notes over notes delivered is a measurement; it is shown only with a named corpus and a date.",
  empties: {
    items: {
      title: "No item in the queue",
      why: "Shows here once a clinician takes a fired RED into review.",
    },
    levels: {
      title: "No level",
      why: "Shows here once the triage levels are read from the rules engine.",
    },
    acceptance: {
      title: "No branch",
      why: "Shows here once the intake branches are read from the taxonomy.",
    },
    classes: {
      title: "No class",
      why: "Shows here once the PolicyGuard violation classes are read.",
    },
  },
  refusals: {
    no_credentials: "No session credentials; sign in to the console.",
    token_refused: "The session could not be verified; sign in again.",
    role_not_permitted:
      "This role cannot see the clinical quality module: its counts sum every tenant.",
    source_ip_refused: "Not reachable from this network address.",
    console_unconfigured: "The admin console is not configured.",
  },
  unavailable: {
    api_base_unconfigured: "The API address is not configured.",
    api_unreachable: "The API is unreachable.",
    payload_refused:
      "The API's answer was not shown: it carried a triage count from outside the rules engine, an item that downgrades a RED, free text, or a count with no scrape behind it.",
  },
};

export const COPY: Record<Lang, QualitySafetyCopy> = { tr, en };
