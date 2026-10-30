/**
 * INT-562 — the Safety queue's copy. `tr` is the source of truth (invariant
 * 5); `en` mirrors it key for key, and the type makes a missing key a compile
 * error. Operator copy: nominal, short, no verdict and no diagnosis word
 * (invariant 2's categories hold here too); the triage level is the word the
 * rules engine gave, never a reading of the patient.
 */
import type { Lang } from "../ops/copy";
import { EMPTIES, FILLS } from "../ui/fills";

export type { Lang } from "../ops/copy";

const tr = {
  title: "Güvenlik kuyruğu",
  intro:
    "Klinik güvenlik gelen kutusu: her KIRMIZI, yerinde bildirimi ve KIRMIZI bir ziyaretin ertelenmesi ya da iptali, kiracının SLA'sına karşı saatiyle. Yalnızca kimlikler ve saatler; hasta sözü yok.",
  unknown: "Bilinmiyor",
  fills: FILLS.tr,
  empties: EMPTIES.tr,
  reasons: {} as Record<string, string>,
  refusals: {
    no_credentials: "Oturum bilgisi yok. Konsol yalnızca yönetici rolüyle açılır.",
    token_refused: "Oturum doğrulanamadı.",
    role_not_permitted: "Bu rol güvenlik kuyruğunu göremez.",
    source_ip_refused: "Bu ağ adresinden konsola erişim yok (IP izin listesi).",
    console_unconfigured: "Yönetici konsolu yapılandırılmamış; kimse kabul edilmiyor.",
  },
  unavailable: {
    api_base_unconfigured: "API adresi yapılandırılmamış.",
    api_unreachable: "API'ye ulaşılamıyor.",
    payload_refused: "API yanıtı reddedildi; gösterilmedi.",
  },
  inboxUnavailable: {
    safety_inbox_unconfigured:
      "Klinik güvenlik gelen kutusu bu kurulumda bağlı değil; kuyruk okunamıyor. Boş bir kuyruk “bekleyen yok” anlamına gelirdi, bu yüzden hiçbir satır gösterilmiyor.",
    safety_inbox_unreachable: "Gelen kutusu deposuna ulaşılamıyor; kuyruk okunamıyor.",
    safety_inbox_contended: "Gelen kutusu deposu şu anda meşgul; kuyruk okunamadı.",
  },
  tile: "Kuyruk",
  summary: { open: "bekleyen", pastSla: "SLA aşıldı" },
  whoMayAcknowledge:
    "Görüldü işaretlemek tek anahtardır ve yalnızca kiracının klinik sorumlusuna açıktır; ikinci bir onay gerekmez. Her işaretleme, depoya yazılmadan önce denetim zincirine kaydedilir.",
  acknowledge: "Görüldü işaretleyin",
  minutes: "dk",
  sla: "SLA",
  cols: {
    entry: "Kayıt",
    session: "Oturum",
    kind: "Tür",
    rules: "Kurallar",
    register: "Bildirim tarzı",
    created: "Oluşturulma",
    age: "Yaş · SLA",
    acknowledged: "Görüldü",
    action: "İşlem",
  },
  kinds: {
    red: "KIRMIZI",
    red_on_site: "KIRMIZI · yerinde bildirim",
    visit_rescheduled: "Ziyaret ertelendi",
    visit_cancelled: "Ziyaret iptal edildi",
  },
  registers: {
    ALERT: "Uyarı",
    CALM: "Sakin",
    SILENT: "Sessiz",
    DEFERRED_CLINICIAN: "Klinisyene bırakıldı",
  },
  bands: { within_sla: "SLA içinde", past_sla: "SLA aşıldı" },
  none: "—",
  results: {
    acknowledged: "Kayıt görüldü olarak işaretlendi.",
    cross_site_refused: "İstek başka bir siteden geldi; gönderilmedi.",
    api_base_unconfigured: "API adresi yapılandırılmamış; gönderilmedi.",
    no_credentials: "Oturum bilgisi yok; gönderilmedi.",
    action_unknown: "Bilinmeyen işlem; gönderilmedi.",
    safety_entry_invalid: "Kayıt kimliği beklenen biçimde değil; gönderilmedi.",
    api_unreachable: "API'ye ulaşılamadı.",
    api_refused: "API isteği reddetti.",
    token_refused: "Oturum doğrulanamadı.",
    forbidden: "Bu rol görüldü işaretleyemez; yalnızca kiracının klinik sorumlusu işaretler.",
    source_ip_refused: "Bu ağ adresinden konsola erişim yok.",
    admin_console_unconfigured: "Yönetici konsolu yapılandırılmamış.",
    tenant_required:
      "Hesabınız bir kiracıya bağlı değil; kiracı dışı bir hesap görüldü işaretleyemez.",
    safety_entry_not_found: "Kiracınızda böyle bir kayıt yok.",
    safety_entry_already_acknowledged: "Bu kayıt daha önce görüldü işaretlenmiş.",
    safety_inbox_unconfigured: "Gelen kutusu bağlı değil; işaretlenemedi.",
    safety_inbox_unreachable: "Gelen kutusu deposuna ulaşılamadı; işaretlenemedi.",
    safety_inbox_contended: "Gelen kutusu deposu meşguldü; yeniden deneyin.",
    body_not_json: "İstek beklenmeyen bir gövde taşıdı; reddedildi.",
    unexpected_field: "İstek beklenmeyen bir alan taşıdı; reddedildi.",
  },
};

export type SafetyQueueCopy = typeof tr;

const en: SafetyQueueCopy = {
  title: "Safety queue",
  intro:
    "The clinic's safety inbox: every RED, its on-site notification, and a reschedule or cancellation of a RED visit, each with its clock against the tenant's SLA. Ids and clocks only; no patient words.",
  unknown: "Unknown",
  fills: FILLS.en,
  empties: EMPTIES.en,
  reasons: {},
  refusals: {
    no_credentials: "No session. The console opens only for an admin role.",
    token_refused: "The session could not be verified.",
    role_not_permitted: "This role cannot see the safety queue.",
    source_ip_refused: "The console is not reachable from this network address (IP allow-list).",
    console_unconfigured: "The admin console is not configured; nobody is admitted.",
  },
  unavailable: {
    api_base_unconfigured: "The API base URL is not configured.",
    api_unreachable: "The API is unreachable.",
    payload_refused: "The API response was refused; nothing is shown.",
  },
  inboxUnavailable: {
    safety_inbox_unconfigured:
      "The clinic safety inbox is not wired on this deployment, so the queue cannot be read. An empty queue would read as “nobody is waiting”, so no row is shown.",
    safety_inbox_unreachable: "The inbox store is unreachable; the queue cannot be read.",
    safety_inbox_contended: "The inbox store is busy right now; the queue could not be read.",
  },
  tile: "Queue",
  summary: { open: "waiting", pastSla: "past SLA" },
  whoMayAcknowledge:
    "Acknowledging takes one key and is open only to the tenant's clinical responsible; no second approval is needed. Every acknowledgement is written to the audit chain before the store.",
  acknowledge: "Acknowledge",
  minutes: "min",
  sla: "SLA",
  cols: {
    entry: "Entry",
    session: "Session",
    kind: "Kind",
    rules: "Rules",
    register: "Register",
    created: "Raised",
    age: "Age · SLA",
    acknowledged: "Acknowledged",
    action: "Action",
  },
  kinds: {
    red: "RED",
    red_on_site: "RED · on-site notification",
    visit_rescheduled: "Visit rescheduled",
    visit_cancelled: "Visit cancelled",
  },
  registers: {
    ALERT: "Alert",
    CALM: "Calm",
    SILENT: "Silent",
    DEFERRED_CLINICIAN: "Deferred to the clinician",
  },
  bands: { within_sla: "within SLA", past_sla: "past SLA" },
  none: "—",
  results: {
    acknowledged: "The entry is acknowledged.",
    cross_site_refused: "The request came from another site; nothing was sent.",
    api_base_unconfigured: "The API base URL is not configured; nothing was sent.",
    no_credentials: "No session; nothing was sent.",
    action_unknown: "Unknown action; not sent.",
    safety_entry_invalid: "The entry id is not in the expected shape; nothing was sent.",
    api_unreachable: "The API could not be reached.",
    api_refused: "The API refused the request.",
    token_refused: "The session could not be verified.",
    forbidden: "This role cannot acknowledge; only the tenant's clinical responsible does.",
    source_ip_refused: "The console is not reachable from this network address.",
    admin_console_unconfigured: "The admin console is not configured.",
    tenant_required:
      "Your account is not bound to a tenant; an account outside a tenant cannot acknowledge.",
    safety_entry_not_found: "There is no such entry in your tenant.",
    safety_entry_already_acknowledged: "This entry was already acknowledged.",
    safety_inbox_unconfigured: "The inbox is not wired; nothing was acknowledged.",
    safety_inbox_unreachable: "The inbox store could not be reached; nothing was acknowledged.",
    safety_inbox_contended: "The inbox store was busy; try again.",
    body_not_json: "The request carried an unexpected body; refused.",
    unexpected_field: "The request carried an unexpected field; refused.",
  },
};

export const COPY: Record<Lang, SafetyQueueCopy> = { tr, en };
