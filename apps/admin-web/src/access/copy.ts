/**
 * INT-366 — the access review page's copy. `tr` is the source of truth
 * (invariant 5); `en` mirrors it key for key, and the type makes a missing key
 * a compile error rather than a blank cell. Operator copy: nominal and short;
 * the page states the rule it enforces, never a verdict on a person.
 */
import type { Lang } from "../ops/copy";

export type { Lang } from "../ops/copy";
import { EMPTIES, FILLS } from "../ui/fills";

const tr = {
  title: "Erişim gözden geçirmesi",
  generatedAt: "Oluşturulma",
  unknown: "Bilinmiyor",
  fills: FILLS.tr,
  empties: EMPTIES.tr,
  yes: "evet",
  no: "hayır",
  none: "yok",
  never: "hiç",
  dayUnit: "gün",
  reasons: {} as Record<string, string>,
  refusals: {
    no_credentials: "Oturum bilgisi yok. Konsol yalnızca yönetici rolüyle açılır.",
    token_refused: "Oturum doğrulanamadı.",
    role_not_permitted: "Bu rol erişim gözden geçirmesini göremez.",
    source_ip_refused: "Bu ağ adresinden konsola erişim yok (IP izin listesi).",
    console_unconfigured: "Yönetici konsolu yapılandırılmamış; kimse kabul edilmiyor.",
  },
  unavailable: {
    api_base_unconfigured: "API adresi yapılandırılmamış.",
    api_unreachable: "API'ye ulaşılamıyor.",
    payload_refused: "API yanıtı reddedildi; gösterilmedi.",
    access_review_unconfigured:
      "Keycloak ve OpenBao yönetim erişimi yapılandırılmamış; gözden geçirme üretilemiyor.",
    directory_unavailable: "Keycloak dizini okunamadı; boş bir gözden geçirme gösterilmez.",
  },
  status: {
    title: "Konsol gözden geçirmesi",
    age: "Yaşı",
    neverReviewed: "Hiç karşı imzalanmadı",
    readOnly: "Salt okunur roller",
    rule: "100 günü aşan ya da hiç yapılmamış bir gözden geçirmede platform_owner ve tenant_admin yazamaz (files/08 §2.7).",
  },
  sections: {
    title: "Bölümler",
    section: "Bölüm",
    signer: "İmzalayan",
    countersigner: "Karşı imza",
    external: "başka kurumdan",
    secondPerson: "ikinci kişi",
    holders: "Hesap",
    digest: "Özet",
    lastSigned: "Son karşı imza",
    age: "Yaşı",
    overdue: "Süresi geçti",
  },
  holders: {
    title: "Hesaplar",
    subject: "Keycloak kimliği",
    username: "Kullanıcı adı",
    enabled: "Etkin",
    roles: "Roller",
    tenant: "Kurum",
    lastLogin: "Son giriş",
    idle: "Girişsiz geçen",
    untilDisable: "Otomatik kapatmaya",
    dormant: "60 günü doldu",
    lastAction: "Son konsol işlemi",
    lastReviewed: "Son gözden geçirme",
  },
  offboardings: {
    title: "Tamamlanmamış erişim sonlandırmaları",
    id: "Kayıt",
    subject: "Keycloak kimliği",
    reason: "Neden",
    pending: "Onay bekleyen",
    failed: "Başarısız",
    none: "Açık kayıt yok.",
    noneWhy: "Başlatılan bir hesap kapatma, her adımı tamamlanana dek burada izlenir.",
  },
};

export type AccessCopy = typeof tr;

const en: AccessCopy = {
  title: "Access review",
  generatedAt: "Generated",
  unknown: "Unknown",
  fills: FILLS.en,
  empties: EMPTIES.en,
  yes: "yes",
  no: "no",
  none: "none",
  never: "never",
  dayUnit: "days",
  reasons: {},
  refusals: {
    no_credentials: "No session. The console opens only with an admin role.",
    token_refused: "The session could not be verified.",
    role_not_permitted: "This role cannot see the access review.",
    source_ip_refused: "No console access from this network address (IP allow-list).",
    console_unconfigured: "The admin console is not configured; nobody is admitted.",
  },
  unavailable: {
    api_base_unconfigured: "The API address is not configured.",
    api_unreachable: "The API cannot be reached.",
    payload_refused: "The API response was refused and is not shown.",
    access_review_unconfigured:
      "Keycloak and OpenBao admin access are not configured; no review can be generated.",
    directory_unavailable:
      "The Keycloak directory could not be read; an empty review is not shown.",
  },
  status: {
    title: "Console review",
    age: "Age",
    neverReviewed: "Never countersigned",
    readOnly: "Read-only roles",
    rule: "Past 100 days, or with no review, platform_owner and tenant_admin cannot write (files/08 §2.7).",
  },
  sections: {
    title: "Sections",
    section: "Section",
    signer: "Signs",
    countersigner: "Countersignature",
    external: "another organisation",
    secondPerson: "second person",
    holders: "Accounts",
    digest: "Digest",
    lastSigned: "Last countersigned",
    age: "Age",
    overdue: "Overdue",
  },
  holders: {
    title: "Accounts",
    subject: "Keycloak id",
    username: "Username",
    enabled: "Enabled",
    roles: "Roles",
    tenant: "Tenant",
    lastLogin: "Last login",
    idle: "Without a login",
    untilDisable: "Until auto-disable",
    dormant: "60 days reached",
    lastAction: "Last console action",
    lastReviewed: "Last reviewed",
  },
  offboardings: {
    title: "Offboardings not yet complete",
    id: "Record",
    subject: "Keycloak id",
    reason: "Reason",
    pending: "Awaiting confirmation",
    failed: "Failed",
    none: "No open record.",
    noneWhy: "An offboarding that has started is tracked here until every step completes.",
  },
};

export const COPY: Record<Lang, AccessCopy> = { tr, en };
