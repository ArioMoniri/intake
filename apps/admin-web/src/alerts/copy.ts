/**
 * INT-481 — the Alerts page's copy. `tr` is the source of truth (invariant 5).
 * `en` mirrors it key for key, and the type turns a missing key into a compile
 * error rather than a blank cell. This is operator copy: nominal and short,
 * with no verdicts. An alert is shown by its name and labels and nothing else,
 * so there is no description to translate.
 */
import type { Lang } from "../ops/copy";
import type { AlertState, Severity } from "./module";

export type { Lang } from "../ops/copy";

const tr = {
  title: "Uyarılar",
  generatedAt: "Oluşturulma",
  source: "Kaynak",
  alertmanager: "Alertmanager",
  unknown: "Bilinmiyor",
  none: "yok",
  grafana: "Grafana (personel)",
  reasons: {
    alertmanager_unconfigured: "Alertmanager adresi yapılandırılmamış",
    alertmanager_misconfigured: "Alertmanager adresi geçersiz",
    alertmanager_unreachable: "Alertmanager'a ulaşılamıyor",
    alertmanager_bad_response: "Beklenmeyen yanıt",
    alertmanager_http: "Alertmanager beklenmeyen bir HTTP durumu döndürdü",
  } as Record<string, string>,
  refusals: {
    no_credentials: "Oturum bilgisi yok. Konsol yalnızca yönetici rolüyle açılır.",
    token_refused: "Oturum doğrulanamadı.",
    role_not_permitted: "Bu rol uyarıları göremez.",
    source_ip_refused: "Bu ağ adresinden konsola erişim yok (IP izin listesi).",
    console_unconfigured: "Yönetici konsolu yapılandırılmamış; kimse kabul edilmiyor.",
  },
  unavailable: {
    api_base_unconfigured: "API adresi yapılandırılmamış.",
    api_unreachable: "API'ye ulaşılamıyor.",
    payload_refused: "API yanıtı reddedildi; gösterilmedi.",
  },
  tiles: {
    counts: "Önem derecesine göre",
    alerts: "Uyarı listesi",
  },
  severities: {
    page: "Nöbetçi çağrısı (page)",
    ticket: "İş kaydı (ticket)",
    other: "Diğer",
  } satisfies Record<Severity, string>,
  withheld: "Gösterilmeyen",
  states: {
    active: "etkin",
    suppressed: "susturuldu",
    unprocessed: "işlenmedi",
  } satisfies Record<AlertState, string>,
  cols: {
    alertname: "Uyarı",
    severity: "Önem",
    state: "Durum",
    startsAt: "Başlangıç",
    labels: "Etiketler",
  },
};

export type AlertsCopy = typeof tr;

const en: AlertsCopy = {
  title: "Alerts",
  generatedAt: "Generated",
  source: "Source",
  alertmanager: "Alertmanager",
  unknown: "Unknown",
  none: "none",
  grafana: "Grafana (staff)",
  reasons: {
    alertmanager_unconfigured: "Alertmanager URL not configured",
    alertmanager_misconfigured: "Alertmanager URL invalid",
    alertmanager_unreachable: "Alertmanager unreachable",
    alertmanager_bad_response: "Unexpected response",
    alertmanager_http: "Alertmanager answered with an unexpected HTTP status",
  },
  refusals: {
    no_credentials: "No session. The console opens only for an admin role.",
    token_refused: "The session could not be verified.",
    role_not_permitted: "This role cannot see alerts.",
    source_ip_refused: "The console is not reachable from this network address (IP allow-list).",
    console_unconfigured: "The admin console is not configured; nobody is admitted.",
  },
  unavailable: {
    api_base_unconfigured: "The API base URL is not configured.",
    api_unreachable: "The API is unreachable.",
    payload_refused: "The API response was refused; nothing is shown.",
  },
  tiles: {
    counts: "By severity",
    alerts: "Alert list",
  },
  severities: {
    page: "Page",
    ticket: "Ticket",
    other: "Other",
  },
  withheld: "Withheld",
  states: {
    active: "active",
    suppressed: "suppressed",
    unprocessed: "unprocessed",
  },
  cols: {
    alertname: "Alert",
    severity: "Severity",
    state: "State",
    startsAt: "Started",
    labels: "Labels",
  },
};

export const COPY: Record<Lang, AlertsCopy> = { tr, en };
