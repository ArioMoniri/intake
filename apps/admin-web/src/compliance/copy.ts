/**
 * INT-564 — the Compliance page's words, `tr` the source of truth (invariant
 * 5); `en` mirrors it key for key and the type makes a missing key a compile
 * error. Staff copy, `siz` register, no verdict and no figure (invariant 20).
 */
import type { Lang } from "../ops/copy";
import type { RefusalReason, UnavailableReason } from "../ops/load";
import type { EmptyCopy } from "../ui/fills";
import { FILLS } from "../ui/fills";

type Tables = "transfers" | "consents" | "dsar" | "audit" | "evidence";

const tr = {
  title: "Uyum",
  unknown: "Bilinmiyor",
  fills: FILLS.tr,
  reasons: {} as Record<string, string>,
  generatedAt: "Oluşturulma",
  tiles: {
    transfers: "Veri aktarım kaydı",
    consents: "Onam kapsamı",
    dsar: "İlgili kişi başvuruları (KVKK m.13)",
    audit: "Denetim kaydı (son 24 saat, yalnızca kimlikler)",
    evidence: "Kanıt paketi",
  } satisfies Record<Tables, string>,
  cols: {
    host: "Hedef",
    purpose: "Amaç",
    category: "Kategori",
    basis: "Hukuki dayanak",
    retention: "Saklama",
    dataClass: "Veri sınıfı",
    transfers: "Aktarım",
    bytes: "Bayt",
    notification: "Bildirim",
    scope: "Kapsam",
    version: "Sürüm",
    granted: "Verilen",
    withdrawn: "Geri çekilen",
    request: "Başvuru",
    kind: "Tür",
    status: "Durum",
    dueAt: "Son gün",
    seq: "Sıra",
    at: "Zaman",
    actor: "Aktör",
    action: "İşlem",
  },
  dueBy: "son gün",
  elapsed: "süre doldu",
  overdue: "gecikmiş",
  onTime: "süresinde",
  belowFloor: "10'dan az",
  floorNote:
    "1 ile 9 arasındaki sayılar gösterilmez: küçük bir sayı kişiyi tanınır kılar (k ≥ 10).",
  auditCap: "En yeni satırlar gösterilir; tamamı için denetim aramasını filtreleyin.",
  legalRefs: "Dayanaklar",
  digest: "Paket özeti",
  sections: "Bölümler",
  rows: "satır",
  empties: {
    transfers: {
      title: "Henüz aktarım yok",
      why: "Bir dış hedefe ilk aktarım çıkış kaydına düştüğünde burada satır olarak görünür.",
    },
    consents: {
      title: "Onam kaydı yok",
      why: "Bu kiracıda bir onam verildiğinde ya da geri çekildiğinde kapsamı burada görünür.",
    },
    dsar: {
      title: "Açık başvuru yok",
      why: "Bir ilgili kişi başvurusu açıldığında son günüyle birlikte burada görünür.",
    },
    audit: {
      title: "Son 24 saatte kayıt yok",
      why: "Bir yönetim işlemi denetim zincirine yazıldığında burada görünür.",
    },
    evidence: {
      title: "Paket boş",
      why: "Kayıt, onam ya da başvuru verisi oluştuğunda paketin bölümleri dolar.",
    },
  } satisfies Record<Tables, EmptyCopy>,
  refusals: {
    no_credentials: "Oturum bilgisi yok; konsola giriş yapın.",
    token_refused: "Oturum doğrulanamadı; yeniden giriş yapın.",
    role_not_permitted: "Bu sayfa compliance_officer, auditor ve platform_owner rollerine açıktır.",
    source_ip_refused: "Bu ağ adresinden erişilemez.",
    console_unconfigured: "Yönetici konsolu yapılandırılmamış.",
  } satisfies Record<RefusalReason, string>,
  unavailable: {
    api_base_unconfigured: "API adresi yapılandırılmamış.",
    api_unreachable: "API'ye ulaşılamıyor.",
    payload_refused:
      "API'nin yanıtı gösterilmedi: dayanaksız bir aktarım, tablo formülü ya da zincir özeti taşıyordu.",
  } satisfies Record<UnavailableReason, string>,
};

export type ComplianceCopy = typeof tr;

const en: ComplianceCopy = {
  title: "Compliance",
  unknown: "Unknown",
  fills: FILLS.en,
  reasons: {},
  generatedAt: "Generated",
  tiles: {
    transfers: "Data transfer register",
    consents: "Consent coverage",
    dsar: "Data subject requests (KVKK art. 13)",
    audit: "Audit log (last 24 hours, ids only)",
    evidence: "Evidence bundle",
  },
  cols: {
    host: "Destination",
    purpose: "Purpose",
    category: "Category",
    basis: "Lawful basis",
    retention: "Retention",
    dataClass: "Data class",
    transfers: "Transfers",
    bytes: "Bytes",
    notification: "Notification",
    scope: "Scope",
    version: "Version",
    granted: "Granted",
    withdrawn: "Withdrawn",
    request: "Request",
    kind: "Kind",
    status: "Status",
    dueAt: "Due",
    seq: "Seq",
    at: "Time",
    actor: "Actor",
    action: "Action",
  },
  dueBy: "due",
  elapsed: "window elapsed",
  overdue: "overdue",
  onTime: "on time",
  belowFloor: "fewer than 10",
  floorNote: "Counts from 1 to 9 are not shown: a small count identifies a person (k ≥ 10).",
  auditCap: "The newest rows are shown; filter the audit search for the rest.",
  legalRefs: "Legal references",
  digest: "Bundle digest",
  sections: "Sections",
  rows: "rows",
  empties: {
    transfers: {
      title: "No transfers yet",
      why: "The first transfer to an outside destination appears here once the egress log records it.",
    },
    consents: {
      title: "No consent records",
      why: "A scope appears here once a consent is given or withdrawn in this tenant.",
    },
    dsar: {
      title: "No open requests",
      why: "A data subject request appears here with its deadline once it is opened.",
    },
    audit: {
      title: "No rows in the last 24 hours",
      why: "An admin action appears here once it is written to the audit chain.",
    },
    evidence: {
      title: "The bundle is empty",
      why: "Its sections fill once there is register, consent or request data.",
    },
  },
  refusals: {
    no_credentials: "No session credentials; sign in to the console.",
    token_refused: "The session could not be verified; sign in again.",
    role_not_permitted: "This page is open to compliance_officer, auditor and platform_owner.",
    source_ip_refused: "Not reachable from this network address.",
    console_unconfigured: "The admin console is not configured.",
  },
  unavailable: {
    api_base_unconfigured: "The API address is not configured.",
    api_unreachable: "The API is unreachable.",
    payload_refused:
      "The API's answer was not shown: it carried a transfer with no basis, a spreadsheet formula or a chain digest.",
  },
};

export const COPY: Record<Lang, ComplianceCopy> = { tr, en };
