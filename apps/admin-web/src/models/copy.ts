/**
 * INT-564 — the Models & self-hosting page's words, `tr` the source of truth
 * (invariant 5); `en` mirrors it key for key. Registry text (licences, hosts,
 * findings, block reasons) is the registry's own and is shown as data. No
 * figure is called good and no target sits beside one (invariant 20).
 */
import type { Lang } from "../ops/copy";
import type { RefusalReason, UnavailableReason } from "../ops/load";
import type { EmptyCopy } from "../ui/fills";
import { FILLS } from "../ui/fills";
import type { BenchmarkResult } from "./actions";
import type { Severity } from "./module";

const tr = {
  title: "Modeller ve kendi barındırma",
  unknown: "Bilinmiyor",
  fills: FILLS.tr,
  reasons: {} as Record<string, string>,
  tiles: { release: "Sürüm kapısı", registry: "Kayıt defteri" },
  blocked:
    "Sürüm engelli: PHI yolundaki şu bileşenlerin sağlıklı, kendi barındırılan bir yedeği yok.",
  clear:
    "Sürüm kapısı açık: PHI yolundaki her etkin bileşenin sağlıklı, kendi barındırılan bir yedeği var.",
  sweepOk: "Prob taraması okundu.",
  sweepUnknown: "Prob taraması okunamadı; kapı göremediği her yedekte engeller.",
  yes: "evet",
  no: "hayır",
  severity: { ok: "uygun", attention: "dikkat", blocking: "engelliyor" } satisfies Record<
    Severity,
    string
  >,
  cols: {
    component: "Bileşen",
    severity: "Durum",
    phiPath: "PHI yolu",
    selfHosted: "Şu an kendi barındırılıyor",
    licence: "Lisans",
    probe: "Prob",
    budget: "Bütçe",
    fallback: "Yedek",
    findings: "Bulgular",
    benchmark: "Kıyaslama",
  },
  lanes: { latency: "Gecikme", quality: "Kalite" },
  none: "yok",
  empties: {
    registry: {
      title: "Kayıt defteri boş",
      why: "Bir model ya da hizmet kayıt defterine eklendiğinde burada satır olarak görünür.",
    },
  } satisfies Record<"registry", EmptyCopy>,
  results: {
    benchmark_requested: "Kıyaslama istendi; sonucu bu bileşenin satırında görünür.",
    cross_site_refused: "Form başka bir kaynaktan geldi; gönderilmedi.",
    api_base_unconfigured: "API adresi yapılandırılmamış.",
    no_credentials: "Oturum bilgisi yok.",
    action_unknown: "Bilinmeyen bileşen ya da hat; gönderilmedi.",
    api_unreachable: "API'ye ulaşılamıyor.",
    api_refused: "API isteği reddetti.",
    token_refused: "Oturum doğrulanamadı.",
    forbidden: "Bu rol kıyaslama başlatamaz.",
    unknown_component: "Kayıt defterinde böyle bir bileşen yok.",
    unknown_kind: "Böyle bir kıyaslama hattı yok.",
    unexpected_field: "Beklenmeyen alan; gönderilmedi.",
    no_named_corpus:
      "Kalite kıyaslaması için adı, tarihi ve lisansı belli bir değerlendirme kümesi yok (HB-C10).",
  } satisfies Record<BenchmarkResult, string>,
  refusals: {
    no_credentials: "Oturum bilgisi yok; konsola giriş yapın.",
    token_refused: "Oturum doğrulanamadı; yeniden giriş yapın.",
    role_not_permitted: "Bu sayfa platform kapsamlı rollere açıktır.",
    source_ip_refused: "Bu ağ adresinden erişilemez.",
    console_unconfigured: "Yönetici konsolu yapılandırılmamış.",
  } satisfies Record<RefusalReason, string>,
  unavailable: {
    api_base_unconfigured: "API adresi yapılandırılmamış.",
    api_unreachable: "API'ye ulaşılamıyor.",
    payload_refused:
      "API'nin yanıtı gösterilmedi: engelleyen bir satır varken sürümü açık gösteriyordu.",
  } satisfies Record<UnavailableReason, string>,
};

export type ModelsCopy = typeof tr;

const en: ModelsCopy = {
  title: "Models & self-hosting",
  unknown: "Unknown",
  fills: FILLS.en,
  reasons: {},
  tiles: { release: "Release gate", registry: "Registry" },
  blocked: "Release blocked: these PHI-path components have no healthy self-hosted fallback.",
  clear: "Release gate clear: every enabled PHI-path component has a healthy self-hosted fallback.",
  sweepOk: "The probe sweep was read.",
  sweepUnknown:
    "The probe sweep could not be read; the gate blocks on every fallback it cannot see.",
  yes: "yes",
  no: "no",
  severity: { ok: "ok", attention: "attention", blocking: "blocking" },
  cols: {
    component: "Component",
    severity: "State",
    phiPath: "PHI path",
    selfHosted: "Self-hosted now",
    licence: "Licence",
    probe: "Probe",
    budget: "Budget",
    fallback: "Fallback",
    findings: "Findings",
    benchmark: "Benchmark",
  },
  lanes: { latency: "Latency", quality: "Quality" },
  none: "none",
  empties: {
    registry: {
      title: "The registry is empty",
      why: "A model or service appears here as a row once it is added to the registry.",
    },
  },
  results: {
    benchmark_requested: "Benchmark requested; its result appears on this component's row.",
    cross_site_refused: "The form came from another origin; nothing was sent.",
    api_base_unconfigured: "The API address is not configured.",
    no_credentials: "No session credentials.",
    action_unknown: "Unknown component or lane; nothing was sent.",
    api_unreachable: "The API is unreachable.",
    api_refused: "The API refused the request.",
    token_refused: "The session could not be verified.",
    forbidden: "This role cannot start a benchmark.",
    unknown_component: "The registry has no such component.",
    unknown_kind: "There is no such benchmark lane.",
    unexpected_field: "Unexpected field; nothing was sent.",
    no_named_corpus:
      "A quality benchmark needs a named, dated, licensed evaluation set, and there is none (HB-C10).",
  },
  refusals: {
    no_credentials: "No session credentials; sign in to the console.",
    token_refused: "The session could not be verified; sign in again.",
    role_not_permitted: "This page is open to platform-scope roles.",
    source_ip_refused: "Not reachable from this network address.",
    console_unconfigured: "The admin console is not configured.",
  },
  unavailable: {
    api_base_unconfigured: "The API address is not configured.",
    api_unreachable: "The API is unreachable.",
    payload_refused:
      "The API's answer was not shown: it claimed a clear release while a row was blocking.",
  },
};

export const COPY: Record<Lang, ModelsCopy> = { tr, en };
