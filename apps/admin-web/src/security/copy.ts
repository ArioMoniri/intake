/**
 * INT-565 — the Security page's words, `tr` the source of truth (invariant 5);
 * `en` mirrors it key for key. Security counts and an integrity verdict, never
 * an accuracy claim (invariant 20); "not configured" and "nothing detected"
 * are worded apart (invariant 17).
 */
import type { Lang } from "../ops/copy";
import type { RefusalReason, UnavailableReason } from "../ops/load";
import { FILLS, type EmptyCopy } from "../ui/fills";
import { SCRAPE_REASONS } from "../ui/scrape-reasons";

const tr = {
  title: "Güvenlik",
  unknown: "Bilinmiyor",
  fills: FILLS.tr,
  reasons: SCRAPE_REASONS.tr,
  yes: "evet",
  no: "hayır",
  bands: { detection: "Algılama", integrity: "Bütünlük ve bulgular" },
  tiles: {
    siem: "SIEM özetleri",
    egress: "Engellenen çıkışlar",
    auditChain: "Denetim zinciri",
    pentest: "Sızma testi bulguları",
  },
  feedConfigured: "Akış bağlı",
  total: "Uyarı",
  refused: "Reddedilen",
  detector: "Algılayıcı",
  configured: "Bağlı",
  count: "Adet",
  why: "Neden",
  signal: "Sinyal",
  severity: "Önem",
  detectorWhy: {
    crowdsec: "Kenar engelleyicisinin kararları için konsol akışı yok; kurallar kenarda uygulanır.",
    stream: "Uyarı akışı bağlanmamış: bağlanmamış akış, hiçbir şey algılanmadı anlamına gelmez.",
  },
  siemNote: "Sayılar sinyal ve öneme göre; her uyarı kimlik taşır, anlatı taşımaz.",
  window: "Pencere",
  denied: "Engellenen deneme",
  target: "Katalog hedefi",
  egressNote:
    "PHI yolundan dışarıya yapılan ve izin listesince engellenen denemeler. İzin listesi varsayılan olarak reddeder.",
  outcome: "Sonuç",
  attested: "Doğrulandı",
  anchor: "Dış çapa",
  outcomes: {
    intact: "Dış çapaya karşı doğrulandı.",
    chain_broken: "Zincir dış çapayla uyuşmuyor.",
    anchor_missing:
      "Dış çapa yayımlanmadığı için zincir doğrulanmış sayılmaz; kendi içinde tutarlı bir zincir kesilmiş ya da yeniden yazılmış olabilir (HB-I12).",
  } as Record<string, string>,
  chainNote:
    "Konsol zincirin başını taşımaz ve zinciri okumaz: baş, bu konsolun içinde bulunduğu yetki alanının dışında yayımlanır.",
  assessment: "Değerlendirme",
  assessments: {
    none_recorded: "Kayıtlı değerlendirme yok",
    assessed: "Değerlendirildi",
  } as Record<string, string>,
  lastAssessment: "Son değerlendirme",
  sla: "Kapanış süresi (gün)",
  finding: "Bulgu",
  status: "Durum",
  age: "Yaş (gün)",
  discovered: "Bulunma",
  pentestNote:
    "İlk dış sızma testi P2 pilotundan önce yapılır; bulgular kapanış süresine göre izlenir.",
  empties: {
    findings: {
      title: "Bulgu yok",
      why: "Bir dış sızma testi kaydedildiğinde bulguları burada görünür.",
    },
    distribution: {
      title: "Dağılım yok",
      why: "Uyarı akışı bağlandığında sinyal ve önem dağılımı burada görünür.",
    },
    sla: {
      title: "Kapanış süresi yok",
      why: "Önem düzeyleri için kapanış süreleri tanımlandığında burada görünür.",
    },
    detectors: {
      title: "Algılayıcı yok",
      why: "Bir algılayıcı tanımlandığında burada görünür.",
    },
  } satisfies Record<"findings" | "distribution" | "sla" | "detectors", EmptyCopy>,
  refusals: {
    no_credentials: "Oturum bilgisi yok; konsola giriş yapın.",
    token_refused: "Oturum doğrulanamadı; yeniden giriş yapın.",
    role_not_permitted: "Bu rol güvenlik modülünü göremez.",
    source_ip_refused: "Bu ağ adresinden erişilemez.",
    console_unconfigured: "Yönetici konsolu yapılandırılmamış.",
  } satisfies Record<RefusalReason, string>,
  unavailable: {
    api_base_unconfigured: "API adresi yapılandırılmamış.",
    api_unreachable: "API'ye ulaşılamıyor.",
    payload_refused:
      "API'nin yanıtı gösterilmedi: bağlanmamış bir akış için sayı, kazınmamış bir çıkış sayısı, zincir başı ya da çapasız bir doğrulama taşıyordu.",
  } satisfies Record<UnavailableReason, string>,
};

export type SecurityCopy = typeof tr;

const en: SecurityCopy = {
  title: "Security",
  unknown: "Unknown",
  fills: FILLS.en,
  reasons: SCRAPE_REASONS.en,
  yes: "yes",
  no: "no",
  bands: { detection: "Detection", integrity: "Integrity and findings" },
  tiles: {
    siem: "SIEM summaries",
    egress: "Egress denials",
    auditChain: "Audit chain",
    pentest: "Pen-test findings",
  },
  feedConfigured: "Feed wired",
  total: "Alerts",
  refused: "Refused",
  detector: "Detector",
  configured: "Wired",
  count: "Count",
  why: "Why",
  signal: "Signal",
  severity: "Severity",
  detectorWhy: {
    crowdsec:
      "The edge bouncer's decisions have no console feed; its rules are enforced at the edge.",
    stream:
      "The alert stream is not mounted: an unwired stream does not mean nothing was detected.",
  },
  siemNote: "Counts by signal and severity; every alert carries ids, not narrative.",
  window: "Window",
  denied: "Denied attempts",
  target: "Catalogue target",
  egressNote:
    "Attempts to leave the PHI path that the allow-list refused. The allow-list denies by default.",
  outcome: "Outcome",
  attested: "Attested",
  anchor: "External anchor",
  outcomes: {
    intact: "Verified against the external anchor.",
    chain_broken: "The chain does not match the external anchor.",
    anchor_missing:
      "No external anchor is published, so the chain is not attested; a self-consistent chain may have been truncated or rewritten (HB-I12).",
  },
  chainNote:
    "The console carries no chain head and reads no chain: the head is published outside the blast radius this console sits in.",
  assessment: "Assessment",
  assessments: { none_recorded: "No assessment recorded", assessed: "Assessed" },
  lastAssessment: "Last assessment",
  sla: "Closure SLA (days)",
  finding: "Finding",
  status: "Status",
  age: "Age (days)",
  discovered: "Discovered",
  pentestNote:
    "The first external pen-test is before the P2 pilot; findings are tracked against the closure SLA.",
  empties: {
    findings: {
      title: "No finding",
      why: "Findings show here once an external pen-test is recorded.",
    },
    distribution: {
      title: "No distribution",
      why: "The signal and severity split shows here once the alert stream is mounted.",
    },
    sla: {
      title: "No closure SLA",
      why: "Shows here once closure times are set for the severities.",
    },
    detectors: {
      title: "No detector",
      why: "Shows here once a detector is declared.",
    },
  },
  refusals: {
    no_credentials: "No session credentials; sign in to the console.",
    token_refused: "The session could not be verified; sign in again.",
    role_not_permitted: "This role cannot see the security module.",
    source_ip_refused: "Not reachable from this network address.",
    console_unconfigured: "The admin console is not configured.",
  },
  unavailable: {
    api_base_unconfigured: "The API address is not configured.",
    api_unreachable: "The API is unreachable.",
    payload_refused:
      "The API's answer was not shown: it carried a count for an unwired feed, an egress count with no scrape, a chain head, or a verdict with no anchor.",
  },
};

export const COPY: Record<Lang, SecurityCopy> = { tr, en };
