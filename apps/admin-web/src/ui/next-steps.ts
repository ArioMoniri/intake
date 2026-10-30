/**
 * INT-459 — what a refused or unavailable page tells the operator to do next,
 * beside the reason it already gives. Shared by every console page, because
 * the reasons are the loaders' (`../ops/load`, and the access review's own
 * two in `../access/load`), not the pages'.
 *
 * `tr` is the source of truth (invariant 5) and the type makes a missing key a
 * compile error. Each step is nominal: it names who or what can change the
 * outcome, and never promises one. Only a source that may come back (the API,
 * the identity directory) offers a retry; for a refusal of the caller,
 * reloading cannot help.
 */
import type { AccessUnconfigured } from "../access/load";
import type { Lang } from "../ops/copy";
import type { RefusalReason, UnavailableReason } from "../ops/load";
import type { InboxUnavailable } from "../safety-queue/load";

export type NextStepReason =
  RefusalReason | UnavailableReason | AccessUnconfigured | InboxUnavailable;

/** The reasons whose source may come back, so retrying can help. */
export const RETRYABLE: readonly NextStepReason[] = [
  "api_unreachable",
  "directory_unavailable",
  "safety_inbox_unreachable",
  "safety_inbox_contended",
];

export interface NextStepCopy {
  reasons: Record<NextStepReason, string>;
  retry: string;
}

export const NEXT_STEPS: Record<Lang, NextStepCopy> = {
  tr: {
    reasons: {
      no_credentials: "Yönetici rolü olan bir hesapla oturum açın.",
      token_refused: "Oturumunuz sona ermiş olabilir. Yeniden oturum açın.",
      role_not_permitted:
        "Bu sayfa için rolünüzün değişmesi gerekiyorsa platform yöneticisine başvurun.",
      source_ip_refused: "Konsola izin verilen kurum ağından bağlanın.",
      console_unconfigured: "Konsolun kimlik ayarı tamamlanmalı. Platform ekibine bildirin.",
      api_base_unconfigured: "Bu kurulumun API adresi ayarlanmalı. Platform ekibine bildirin.",
      api_unreachable: "API yeniden yanıt verdiğinde sayfa açılır.",
      payload_refused: "Yanıt beklenen biçime uymadı. Platform ekibine bildirin.",
      access_review_unconfigured:
        "Keycloak ve OpenBao yönetim erişimi ayarlanmalı. Platform ekibine bildirin.",
      directory_unavailable: "Dizin yeniden okunabildiğinde gözden geçirme açılır.",
      safety_inbox_unconfigured:
        "`INTAKE_SAFETY_INBOX_REDIS_URL`, ses çalışma zamanının yazdığı gelen kutusu deposunu gösterdiğinde kuyruk açılır. Platform ekibine bildirin.",
      safety_inbox_unreachable: "Gelen kutusu deposu yeniden yanıt verdiğinde kuyruk açılır.",
      safety_inbox_contended: "Depo boşaldığında kuyruk açılır; yeniden deneyin.",
    },
    retry: "Yeniden deneyin",
  },
  en: {
    reasons: {
      no_credentials: "Sign in with an account that holds an admin role.",
      token_refused: "Your session may have ended. Sign in again.",
      role_not_permitted: "If your role should change for this page, ask the platform admin.",
      source_ip_refused: "Connect from a network the console allows.",
      console_unconfigured:
        "The console's identity settings need completing. Tell the platform team.",
      api_base_unconfigured: "This deployment's API address needs setting. Tell the platform team.",
      api_unreachable: "The page opens once the API answers again.",
      payload_refused: "The response did not match the expected shape. Tell the platform team.",
      access_review_unconfigured:
        "Keycloak and OpenBao admin access need setting up. Tell the platform team.",
      directory_unavailable: "The review opens once the directory can be read again.",
      safety_inbox_unconfigured:
        "The queue opens once `INTAKE_SAFETY_INBOX_REDIS_URL` names the inbox store the voice runtime writes. Tell the platform team.",
      safety_inbox_unreachable: "The queue opens once the inbox store answers again.",
      safety_inbox_contended: "The queue opens once the store is free; try again.",
    },
    retry: "Try again",
  },
};
