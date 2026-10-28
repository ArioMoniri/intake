/**
 * INT-459 refresh — what fills an empty place on a console page.
 *
 * - `FILLS`: beside an unknown tile's cause, the one condition that makes it
 *   read, keyed by the loaders' and the API's reason codes. Only a source
 *   reason has one; a reason the page cannot help with (a refused label, a
 *   malformed record) names who repairs it, never a promise.
 * - `EMPTIES`: a table with no row says that it is empty and what puts a row
 *   there, keyed by the table.
 *
 * `tr` is the source of truth (invariant 5); `en` mirrors it key for key and
 * the type makes a missing key a compile error. A name in backticks is an
 * environment variable or a path, set in monospace (`./unknown.tsx`). Nominal
 * operator copy: no verdict, no target, no figure (invariant 20).
 */
import type { Lang } from "../ops/copy";

const trFills = {
  prometheus_unconfigured:
    "`INTAKE_OPS_PROMETHEUS_URL` API'ye bir Prometheus adresi verdiğinde burada görünür.",
  prometheus_misconfigured:
    "`INTAKE_OPS_PROMETHEUS_URL` düz bir http(s) adresi olduğunda burada görünür.",
  prometheus_unreachable: "Prometheus API'ye yeniden yanıt verdiğinde burada görünür.",
  prometheus_query_error: "Prometheus bu sorguyu yeniden kabul ettiğinde burada görünür.",
  prometheus_bad_response: "Prometheus beklenen biçimde yanıt verdiğinde burada görünür.",
  no_series: "Servis bu ölçümü dışa verdiğinde ve Prometheus onu topladığında burada görünür.",
  label_not_id_shaped:
    "Serinin etiketleri konsolun gösterebileceği kimlikler olduğunda burada görünür.",
  unexpected_label:
    "Serinin etiketleri konsolun gösterebileceği kimlikler olduğunda burada görünür.",
  collector_source_failing: "Operasyon toplayıcısı bu kaynağı yeniden okuduğunda burada görünür.",
  registry_unreadable: "API model kayıt dosyasını yeniden okuyabildiğinde burada görünür.",
  probe_results_unconfigured:
    "`INTAKE_PROBE_RESULTS_PATH` yoklama çalıştırıcısının sonuç dosyasını gösterdiğinde, sonraki taramadan sonra burada görünür.",
  probe_results_missing:
    "Yoklama çalıştırıcısı bu dosyaya ilk taramasını yazdığında burada görünür.",
  probe_results_unreadable: "Yoklama sonuç dosyası yeniden okunabildiğinde burada görünür.",
  no_result: "Sonraki tarama bu yoklamaya ulaştığında burada görünür.",
  sweep_stale: "Yoklama çalıştırıcısı yeni bir taramayı bitirdiğinde burada görünür.",
  slo_files_unreadable: "API SLO dosyalarını yeniden okuyabildiğinde burada görünür.",
  sli_out_of_range: "SLI yeniden 0 ile 1 arasında okunduğunda burada görünür.",
  sli_outside_console_grammar:
    "SLI, konsolun okuyabildiği bir oran olarak yazıldığında burada görünür.",
  api_unreachable: "API'nin sağlık uçları yeniden yanıt verdiğinde burada görünür.",
  readiness_malformed: "`/readyz` beklenen biçimde yanıt verdiğinde burada görünür.",
  release_freeze_unconfigured:
    "`INTAKE_RELEASE_FREEZE_REDIS_URL`, deploy.sh'in de okuduğu dondurma deposunu gösterdiğinde burada görünür.",
  release_freeze_misconfigured:
    "`INTAKE_RELEASE_FREEZE_REDIS_URL` bir redis adresi olduğunda burada görünür.",
  release_freeze_unreachable: "Dondurma deposu yeniden yanıt verdiğinde burada görünür.",
  release_freeze_malformed: "Platform ekibi dondurma kaydını düzelttiğinde burada görünür.",
  voice_control_unconfigured:
    "`INTAKE_VOICE_CONTROL_REDIS_URL`, ses çalışma zamanının okuduğu depoyu gösterdiğinde burada görünür.",
  voice_control_unreachable: "Ses denetim deposu yeniden yanıt verdiğinde burada görünür.",
  voice_control_malformed: "Platform ekibi ses denetim kaydını düzelttiğinde burada görünür.",
  model_lanes_unconfigured:
    "`INTAKE_MODEL_LANES_REDIS_URL` model hattı deposunu gösterdiğinde burada görünür.",
  model_lanes_unreachable: "Model hattı deposu yeniden yanıt verdiğinde burada görünür.",
  model_lanes_malformed: "Platform ekibi model hattı kaydını düzelttiğinde burada görünür.",
  environment_not_id_shaped: "Ortam adı bir kimlik olduğunda burada görünür.",
};

export type FillReason = keyof typeof trFills;

const enFills: Record<FillReason, string> = {
  prometheus_unconfigured:
    "Shows here once `INTAKE_OPS_PROMETHEUS_URL` gives the API a Prometheus address.",
  prometheus_misconfigured:
    "Shows here once `INTAKE_OPS_PROMETHEUS_URL` is a plain http(s) address.",
  prometheus_unreachable: "Shows here when Prometheus answers the API again.",
  prometheus_query_error: "Shows here when Prometheus accepts this query again.",
  prometheus_bad_response: "Shows here when Prometheus answers in its expected shape.",
  no_series: "Shows here once the service exports this metric and Prometheus collects it.",
  label_not_id_shaped: "Shows here once the series' labels are ids the console may show.",
  unexpected_label: "Shows here once the series' labels are ids the console may show.",
  collector_source_failing: "Shows here when the ops collector reads this source again.",
  registry_unreadable: "Shows here when the API can read the model registry file again.",
  probe_results_unconfigured:
    "Shows here after the next sweep, once `INTAKE_PROBE_RESULTS_PATH` names the probe runner's results file.",
  probe_results_missing: "Shows here once the probe runner writes its first sweep to that file.",
  probe_results_unreadable: "Shows here when the probe results file can be read again.",
  no_result: "Shows here when the next sweep reaches this probe.",
  sweep_stale: "Shows here when the probe runner completes a new sweep.",
  slo_files_unreadable: "Shows here when the API can read the SLO files again.",
  sli_out_of_range: "Shows here when the SLI reads between 0 and 1 again.",
  sli_outside_console_grammar: "Shows here once the SLI is written as a ratio the console reads.",
  api_unreachable: "Shows here when the API's health endpoints answer again.",
  readiness_malformed: "Shows here when `/readyz` answers in its expected shape.",
  release_freeze_unconfigured:
    "Shows here once `INTAKE_RELEASE_FREEZE_REDIS_URL` names the freeze store deploy.sh also reads.",
  release_freeze_misconfigured:
    "Shows here once `INTAKE_RELEASE_FREEZE_REDIS_URL` is a redis address.",
  release_freeze_unreachable: "Shows here when the freeze store answers again.",
  release_freeze_malformed: "Shows here once the platform team repairs the freeze record.",
  voice_control_unconfigured:
    "Shows here once `INTAKE_VOICE_CONTROL_REDIS_URL` names the store the voice runtime reads.",
  voice_control_unreachable: "Shows here when the voice control store answers again.",
  voice_control_malformed: "Shows here once the platform team repairs the voice control record.",
  model_lanes_unconfigured:
    "Shows here once `INTAKE_MODEL_LANES_REDIS_URL` names the model-lane store.",
  model_lanes_unreachable: "Shows here when the model-lane store answers again.",
  model_lanes_malformed: "Shows here once the platform team repairs the model-lane record.",
  environment_not_id_shaped: "Shows here once the environment name is an id.",
};

export const FILLS: Record<Lang, Readonly<Record<FillReason, string>>> = {
  tr: trFills,
  en: enFills,
};

/** An empty table's title, and what puts a row there. */
export interface EmptyCopy {
  title: string;
  why: string;
}

const trEmpties = {
  probes: {
    title: "Son taramada yoklama yok",
    why: "Yoklama çalıştırıcısı kayıttaki bir bileşeni taradığında satırlar burada görünür.",
  },
  components: {
    title: "Bildirilen bileşen yok",
    why: "Kayıt bir bileşen tanımlayıp yoklama taraması onu okuduğunda satırlar burada görünür.",
  },
  gpuHosts: {
    title: "Bildirilen model sunucusu yok",
    why: "Bir GPU sunucusu sağlık ölçümünü Prometheus'a verdiğinde satırlar burada görünür.",
  },
  vendors: {
    title: "Bildirilen sağlayıcı devre kesicisi yok",
    why: "Bir sağlayıcı bağdaştırıcısı devre kesici durumunu dışa verdiğinde satırlar burada görünür.",
  },
  readiness: {
    title: "Bildirilen hazırlık kontrolü yok",
    why: "`/readyz` kontrollerini listelediğinde satırlar burada görünür.",
  },
  models: {
    title: "Kayıtta bileşen yok",
    why: "`observability/registry.yaml` PHI yolundaki bir model ya da servisi tanımladığında satırlar burada görünür.",
  },
  modelUsage: {
    title: "Bu pencerede istek karşılayan model hattı yok",
    why: "Bir hat istek karşılayıp sayaçlarını dışa verdiğinde satırlar burada görünür.",
  },
  workflows: {
    title: "Bildirilen iş akışı çalıştırması yok",
    why: "Operasyon toplayıcısı izlenen dal için bir GitHub Actions çalıştırmasını okuduğunda satırlar burada görünür.",
  },
  runs: {
    title: "İzlenen dalda çalıştırma yok",
    why: "Bir iş akışı izlenen dalda çalıştığında satırlar burada görünür.",
  },
  refs: {
    title: "Denetlenen referans yok",
    why: "Zorunlu bir kapı bir dal ya da etiket için sonuç bildirdiğinde satırlar burada görünür.",
  },
  deployments: {
    title: "Bildirilen dağıtım yok",
    why: "Bu API'de `/version` yanıt verdiğinde burada bir satır görünür.",
  },
  sessions: {
    title: "Bu pencerede oturum yok",
    why: "Ses çalışma zamanı bir oturum başlatıp yolunu dışa verdiğinde satırlar burada görünür.",
  },
  turns: {
    title: "Bu pencerede ölçülen tur yok",
    why: "Bir profil bir turu tamamladığında satırlar burada görünür.",
  },
  speech: {
    title: "Bu pencerede konuşma çağrısı yok",
    why: "ASR ya da TTS çağrıldığında satırlar burada görünür.",
  },
  failovers: {
    title: "Bu pencerede yedeğe geçiş yok",
    why: "Bir profil başka bir profile geçtiğinde burada bir satır görünür.",
  },
  breakers: {
    title: "Bildirilen devre kesici yok",
    why: "Bir konuşma bağdaştırıcısı devre kesici durumunu dışa verdiğinde satırlar burada görünür.",
  },
  tenants: {
    title: "Ses ayarı olan kiracı yok",
    why: "Bir kiracının durdurma anahtarı, varsayılan profili ya da kanaryası ayarlandığında satırlar burada görünür.",
  },
  pending: {
    title: "Bekleyen istek yok",
    why: "İstenen bir ayar değişikliği, ikinci bir yönetici onaylayana dek burada bekler.",
  },
  laneCalls: {
    title: "Bu pencerede hat çağrısı yok",
    why: "Bir hat çağrı karşılayıp Prometheus onu kaydettiğinde satırlar burada görünür.",
  },
  safetyQueue: {
    title: "Kuyrukta kayıt yok",
    why: "Bir KIRMIZI tetiklendiğinde, yerinde bildirim gönderildiğinde ya da KIRMIZI bir ziyaret ertelenip iptal edildiğinde satırlar burada görünür.",
  },
  holders: {
    title: "Rolü olan hesap yok",
    why: "Dizindeki bir hesaba konsol rolü verildiğinde satırlar burada görünür.",
  },
};

export type EmptyKind = keyof typeof trEmpties;

const enEmpties: Record<EmptyKind, EmptyCopy> = {
  probes: {
    title: "No probe in the last sweep",
    why: "Rows show here once the probe runner sweeps a component from the registry.",
  },
  components: {
    title: "No component reported",
    why: "Rows show here once the registry declares a component and the probe sweep reads it.",
  },
  gpuHosts: {
    title: "No model host reported",
    why: "Rows show here once a GPU host exports its health to Prometheus.",
  },
  vendors: {
    title: "No vendor circuit breaker reported",
    why: "Rows show here once a vendor adapter exports its circuit breaker state.",
  },
  readiness: {
    title: "No readiness check reported",
    why: "Rows show here once `/readyz` lists its checks.",
  },
  models: {
    title: "No component in the registry",
    why: "Rows show here once `observability/registry.yaml` declares a model or service on the PHI path.",
  },
  modelUsage: {
    title: "No model lane served a request in this window",
    why: "Rows show here once a lane serves a request and exports its counters.",
  },
  workflows: {
    title: "No workflow run reported",
    why: "Rows show here once the ops collector reads a GitHub Actions run for the watched branch.",
  },
  runs: {
    title: "No run on the watched branch",
    why: "Rows show here once a workflow runs on the watched branch.",
  },
  refs: {
    title: "No ref checked",
    why: "Rows show here once a required gate reports a result for a branch or a tag.",
  },
  deployments: {
    title: "No deployment reported",
    why: "A row shows here once `/version` answers on this API.",
  },
  sessions: {
    title: "No session in this window",
    why: "Rows show here once the voice runtime starts a session and exports its route.",
  },
  turns: {
    title: "No turn measured in this window",
    why: "Rows show here once a profile completes a turn.",
  },
  speech: {
    title: "No speech call in this window",
    why: "Rows show here once ASR or TTS is called.",
  },
  failovers: {
    title: "No failover in this window",
    why: "A row shows here when a profile falls over to another.",
  },
  breakers: {
    title: "No circuit breaker reported",
    why: "Rows show here once a speech adapter exports its breaker state.",
  },
  tenants: {
    title: "No tenant has a voice setting",
    why: "Rows show here once a tenant's kill switch, default profile or canary is set.",
  },
  pending: {
    title: "No pending request",
    why: "A requested settings change waits here until a second admin approves it.",
  },
  laneCalls: {
    title: "No lane call in this window",
    why: "Rows show here once a lane serves a call and Prometheus records it.",
  },
  safetyQueue: {
    title: "No entry in the queue",
    why: "Rows show here when a RED fires, an on-site notification is sent, or a RED visit is rescheduled or cancelled.",
  },
  holders: {
    title: "No account holds a role",
    why: "Rows show here once an account in the directory is given a console role.",
  },
};

export const EMPTIES: Record<Lang, Readonly<Record<EmptyKind, EmptyCopy>>> = {
  tr: trEmpties,
  en: enEmpties,
};
