/**
 * INT-563 (ADR-043) — the step-up's words, `tr` the source of truth.
 *
 * Every outcome the start and callback routes can redirect with has a sentence
 * here in both languages (`satisfies Record<StepUpResult, string>` holds it),
 * and no sentence carries a submitted value — the page reflects codes only
 * (invariant 6). Staff copy, `siz` register.
 */
import type { Lang } from "../ops/copy";
import type { StepUpResult } from "./results";

const tr = {
  title: "Onay",
  explain:
    "Onaylamak için parolanız ve güvenlik anahtarınız yeniden istenir. Onay tek kullanımlıktır ve yalnızca bu talep içindir.",
  approve: "Onayla",
  actionId: "Talep kimliği",
  noAction: "Onaylanacak talep belirtilmedi. Talebi modül sayfasından açın.",
  results: {
    approved: "Onaylandı; değişiklik uygulandı.",
    step_up_cancelled: "Doğrulama iptal edildi; onay verilmedi.",
    step_up_unknown:
      "Doğrulamanın süresi doldu ya da bu oturuma ait değil; Onayla düğmesine yeniden basın.",
    step_up_not_fresh: "Yeni bir giriş yapılmadı; Onayla düğmesine yeniden basın.",
    step_up_without_webauthn: "Giriş güvenlik anahtarı olmadan tamamlandı; onay verilmedi.",
    step_up_token_refused: "Giriş yanıtı doğrulanamadı; onay verilmedi.",
    step_up_replayed: "Bu doğrulama daha önce kullanıldı; onay verilmedi.",
    step_up_exchange_failed: "Kimlik sunucusu yanıt vermedi; onay verilmedi.",
    step_up_unconfigured: "Onay adımı yapılandırılmamış; hiçbir talep onaylanamaz.",
    step_up_body_refused: "İstek okunamadı; onay verilmedi.",
    four_eyes_self_approval: "Kendi talebinizi onaylayamazsınız; başka bir kişi onaylamalı.",
    four_eyes_approver_role: "Bu rol bu talebi onaylayamaz.",
    four_eyes_shared_credential: "Talep edenin güvenlik anahtarı kullanıldı; onay verilmedi.",
    four_eyes_shared_session: "Talep edenin oturumu kullanıldı; onay verilmedi.",
    four_eyes_shared_organisation: "Bu talebi başka bir kuruluştan biri onaylamalı.",
    four_eyes_expired: "Talebin süresi doldu; yeni bir talep açın.",
    four_eyes_already_decided: "Bu talep zaten karara bağlandı.",
    four_eyes_assertion_reused: "Bu doğrulama daha önce kullanıldı; onay verilmedi.",
    not_found: "Böyle bekleyen bir talep yok.",
    cross_site_refused: "Form başka bir kaynaktan geldi; gönderilmedi.",
    api_base_unconfigured: "API adresi yapılandırılmamış.",
    no_credentials: "Oturum bilgisi yok.",
    action_unknown: "Bu talep konsoldan onaylanamaz.",
    api_unreachable: "API'ye ulaşılamıyor.",
    api_refused: "API onayı reddetti; talebin özetini modül sayfasında yeniden okuyun.",
    token_refused: "Oturum doğrulanamadı.",
    forbidden: "Bu rol bu işlemi yapamaz.",
    source_ip_refused: "Bu ağ adresinden işlem yapılamaz.",
    admin_console_unconfigured: "Yönetici konsolu yapılandırılmamış.",
  } satisfies Record<StepUpResult, string>,
};

export type StepUpCopy = typeof tr;

const en: StepUpCopy = {
  title: "Approval",
  explain:
    "Approving asks for your password and security key again. The approval is single-use and covers this request only.",
  approve: "Approve",
  actionId: "Request id",
  noAction: "No request to approve was named. Open it from its module page.",
  results: {
    approved: "Approved; the change is applied.",
    step_up_cancelled: "The verification was cancelled; nothing was approved.",
    step_up_unknown: "The verification expired or belongs to another session; press Approve again.",
    step_up_not_fresh: "No fresh sign-in was made; press Approve again.",
    step_up_without_webauthn:
      "The sign-in completed without the security key; nothing was approved.",
    step_up_token_refused: "The sign-in answer did not verify; nothing was approved.",
    step_up_replayed: "That verification was already used; nothing was approved.",
    step_up_exchange_failed: "The identity server did not answer; nothing was approved.",
    step_up_unconfigured: "The approval step is not configured; no request can be approved.",
    step_up_body_refused: "The request could not be read; nothing was approved.",
    four_eyes_self_approval: "You cannot approve your own request; another person must.",
    four_eyes_approver_role: "This role cannot approve this request.",
    four_eyes_shared_credential: "The requester's security key was used; nothing was approved.",
    four_eyes_shared_session: "The requester's session was used; nothing was approved.",
    four_eyes_shared_organisation: "Someone from another organisation must approve this request.",
    four_eyes_expired: "The request expired; open a new one.",
    four_eyes_already_decided: "This request is already decided.",
    four_eyes_assertion_reused: "That verification was already used; nothing was approved.",
    not_found: "There is no such pending request.",
    cross_site_refused: "The form came from another origin; nothing was sent.",
    api_base_unconfigured: "The API address is not configured.",
    no_credentials: "No session credentials.",
    action_unknown: "This request cannot be approved from the console.",
    api_unreachable: "The API is unreachable.",
    api_refused: "The API refused the approval; read the request's brief on its module page again.",
    token_refused: "The session could not be verified.",
    forbidden: "This role cannot do that.",
    source_ip_refused: "Actions are not accepted from this network address.",
    admin_console_unconfigured: "The admin console is not configured.",
  },
};

export const COPY: Record<Lang, StepUpCopy> = { tr, en };
