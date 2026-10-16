/**
 * INT-490 — the Analytics page's copy. `tr` is the source of truth
 * (invariant 5); `en` mirrors it key for key, and the type makes a missing key
 * a compile error rather than a blank cell. Operator copy: nominal, short, no
 * verdicts. Every figure is described as a measurement of a named week and
 * named tenants, never as a property of the product, and the recognition band
 * is "measured" — no accuracy wording anywhere (invariant 20).
 */
import type { Lang } from "../ops/copy";
import type { ViewKind } from "./payload";

export type { Lang } from "../ops/copy";

const tr = {
  title: "Analitik — araştırma ve iyileştirme",
  lede: "Yalnızca anonim toplamlar (KVKK m.28/1-b; LD-06). Hücreler farklı kişileri sayar; her kişi bir protokol sürümünde haftada bir kez sayılır.",
  floor: (k: number): string =>
    `Bir tabloda 1 ile ${k - 1} arası kişili bir hücre varsa tablonun tamamı gizlenir (<${k}). Nüfusu ${k} kişinin altındaki tablolar hiç listelenmez.`,
  measurement:
    "Her sayı, adı geçen hafta ve kabul edilen kurumlar için alınmış bir ölçümdür; ürünün bir özelliği değildir.",
  kept: "Bu sayfa hiçbir toplamı saklamaz; her istekte yeniden hesaplanır.",
  generatedAt: "Hesaplanma",
  week: "Hafta",
  weekRange: "ISO haftası, UTC",
  previousWeek: "Önceki hafta",
  nextWeek: "Sonraki hafta",
  scope: "Kapsam ve saklama",
  tenants: {
    title: "Kurumlar",
    unconfigured: "Hiçbir kurum kabul edilmedi (kurum listesi yapılandırılmamış).",
    admitted: "Kabul edilen",
    refused: "Dışarıda bırakılan (veri işleyen sıfatıyla, sözleşme izni yok)",
  },
  retention: {
    title: "Saklama süreleri",
    aggregates: "Toplamlar",
    rawTelemetry: "Ham telemetri",
    undecided: "Karar bekliyor (LD-06) — hiçbir şey saklanmıyor",
    days: (days: string): string => `${days} gün`,
  },
  family: { protocol: "Protokol", version: "Sürüm", question: "Soru" },
  columns: {
    value: "Grup",
    people: "Kişi",
    reached: "En az bu aşamaya ulaşan",
    share: "Tablodaki pay",
    dropOff: "Önceki aşamadan kayıp",
    population: "Tablodaki kişi",
  },
  withheld: {
    below_k: (k: number): string =>
      `Bu tablodaki bir grupta ${k} kişiden az var; tablonun tamamı gizlendi.`,
    cross_view: (k: number): string =>
      `Gösterilseydi, başka bir tablodan çıkarma yapılarak ${k} kişiden az bir grup hesaplanabilirdi; gizlendi.`,
  },
  views: {
    funnel: "Huni: davet → başladı → bitirdi → paylaştı",
    triage: "Kural motorunun triyaj düzeyi",
    locale: "Soruların sorulduğu dil",
    platform: "Cihaz platformu",
    question_outcome: "Sonuç",
    question_mode: "Yazılı ya da sesli yanıt",
    question_repeat: "Tekrar ya da açıklama isteği",
    question_time: "Yanıt süresi",
    question_asr: "Ölçülen konuşma tanıma kalitesi bandı",
  } satisfies Record<ViewKind, string>,
  values: {
    invited: "Davet edildi",
    started: "Başladı",
    finished: "Bitirdi",
    shared: "Paylaştı",
    red: "KIRMIZI",
    yellow: "SARI",
    green: "YEŞİL",
    not_evaluated: "Değerlendirilmedi",
    ios: "iOS",
    android: "Android",
    web: "Web",
    answered: "Yanıtlandı",
    skipped: "Atlandı",
    abandoned: "Yarıda bırakıldı",
    typed: "Yazılı",
    voice: "Sesli",
    none: "Yok",
    one_or_more: "Bir ya da daha fazla",
    under_10s: "10 sn'den kısa",
    "10s_to_30s": "10–30 sn",
    "30s_to_60s": "30–60 sn",
    over_60s: "60 sn'den uzun",
    high: "Yüksek",
    medium: "Orta",
    low: "Düşük",
    tr: "Türkçe",
  } as Record<string, string>,
  questions: "Soru başına",
  notCollected: {
    title: "Henüz toplanmayan ölçüler",
    lede: "Bu ölçülerin kaynağı yok; sayfa onları tahmin etmez.",
    reasons: {
      triage_level_not_recorded:
        "Triyaj düzeyi yalnızca şifreli ön-vizit belgesinin içinde duruyor; bu sayfa hasta içeriği okumaz.",
      raw_telemetry_retention_undecided:
        "Ham telemetri (soru başına ve cihaz platformu) kaydedilmiyor: saklama süresi sahibin kararını bekliyor (LD-06).",
      raw_telemetry_not_recorded:
        "Saklama süresi belirlendi; ham telemetriyi kaydeden bileşen henüz yok.",
    } as Record<string, string>,
  },
  empty: (k: number): string =>
    `Bu hafta için listelenecek tablo yok: bir tablonun nüfusu en az ${k} kişi olmalı ve en az bir kurum kabul edilmiş olmalı.`,
  refusals: {
    no_credentials: "Oturum bilgisi yok. Sayfa yalnızca yönetici rolüyle açılır.",
    token_refused: "Oturum doğrulanamadı.",
    role_not_permitted: "Bu rol analitik sayfasını göremez.",
    source_ip_refused: "Bu ağ adresinden konsola erişim yok (IP izin listesi).",
    console_unconfigured: "Yönetici konsolu yapılandırılmamış; kimse kabul edilmiyor.",
  },
  unavailable: {
    api_base_unconfigured: "API adresi yapılandırılmamış.",
    api_unreachable: "API'ye ulaşılamıyor.",
    payload_refused: "API yanıtı reddedildi; gösterilmedi.",
  },
};

export type AnalyticsCopy = typeof tr;

const en: AnalyticsCopy = {
  title: "Analytics — research and improvement",
  lede: "Anonymised aggregates only (KVKK m.28(1)(b); LD-06). Cells count distinct people; each person counts once per protocol version per week.",
  floor: (k: number): string =>
    `If any cell of a table holds between 1 and ${k - 1} people, the whole table is withheld (<${k}). Tables whose population is under ${k} are not listed at all.`,
  measurement:
    "Every figure is a measurement of the named week and the admitted tenants, never a property of the product.",
  kept: "This page keeps no aggregate; it is recomputed on every request.",
  generatedAt: "Computed",
  week: "Week",
  weekRange: "ISO week, UTC",
  previousWeek: "Previous week",
  nextWeek: "Next week",
  scope: "Scope and retention",
  tenants: {
    title: "Tenants",
    unconfigured: "No tenant is admitted (the tenant list is not configured).",
    admitted: "Admitted",
    refused: "Left out (processor, no DPA authorisation)",
  },
  retention: {
    title: "Retention periods",
    aggregates: "Aggregates",
    rawTelemetry: "Raw telemetry",
    undecided: "Awaiting decision (LD-06) — nothing is kept",
    days: (days: string): string => `${days} days`,
  },
  family: { protocol: "Protocol", version: "Version", question: "Question" },
  columns: {
    value: "Group",
    people: "People",
    reached: "Reached at least this stage",
    share: "Share of this table",
    dropOff: "Lost since the previous stage",
    population: "People in this table",
  },
  withheld: {
    below_k: (k: number): string =>
      `A group in this table holds fewer than ${k} people; the whole table is withheld.`,
    cross_view: (k: number): string =>
      `Shown, it would let a group of fewer than ${k} people be computed by subtracting another table; withheld.`,
  },
  views: {
    funnel: "Funnel: invited → started → finished → shared",
    triage: "Rules-engine triage level",
    locale: "Language the questions were asked in",
    platform: "Device platform",
    question_outcome: "Outcome",
    question_mode: "Typed or spoken answer",
    question_repeat: "Repeat or clarification request",
    question_time: "Time to answer",
    question_asr: "Measured speech-recognition quality band",
  },
  values: {
    invited: "Invited",
    started: "Started",
    finished: "Finished",
    shared: "Shared",
    red: "RED",
    yellow: "YELLOW",
    green: "GREEN",
    not_evaluated: "Not evaluated",
    ios: "iOS",
    android: "Android",
    web: "Web",
    answered: "Answered",
    skipped: "Skipped",
    abandoned: "Abandoned",
    typed: "Typed",
    voice: "Spoken",
    none: "None",
    one_or_more: "One or more",
    under_10s: "Under 10 s",
    "10s_to_30s": "10–30 s",
    "30s_to_60s": "30–60 s",
    over_60s: "Over 60 s",
    high: "High",
    medium: "Medium",
    low: "Low",
    tr: "Turkish",
  },
  questions: "Per question",
  notCollected: {
    title: "Measures not collected yet",
    lede: "These measures have no source; the page does not estimate them.",
    reasons: {
      triage_level_not_recorded:
        "The triage level sits only inside the encrypted previsit document; this page reads no patient content.",
      raw_telemetry_retention_undecided:
        "Raw telemetry (per question, and the device platform) is not recorded: its retention period awaits the owner's decision (LD-06).",
      raw_telemetry_not_recorded:
        "A retention period is set; nothing records the raw telemetry yet.",
    },
  },
  empty: (k: number): string =>
    `No table to list for this week: a table needs a population of at least ${k} people and at least one admitted tenant.`,
  refusals: {
    no_credentials: "No session. The page opens only for a console role.",
    token_refused: "The session could not be verified.",
    role_not_permitted: "This role may not see the Analytics page.",
    source_ip_refused: "The console is not reachable from this address (IP allow-list).",
    console_unconfigured: "The admin console is not configured; nobody is admitted.",
  },
  unavailable: {
    api_base_unconfigured: "The API address is not configured.",
    api_unreachable: "The API is unreachable.",
    payload_refused: "The API answer was refused; nothing is shown.",
  },
};

export const COPY: Record<Lang, AnalyticsCopy> = { tr, en };
