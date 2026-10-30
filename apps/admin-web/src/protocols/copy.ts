/**
 * INT-565 — the Protocols page's words, `tr` the source of truth (invariant
 * 5); `en` mirrors it key for key and the type makes a missing key a compile
 * error. Operator copy: nominal, no verdict beside a figure (invariant 20).
 */
import type { Lang } from "../ops/copy";
import type { RefusalReason, UnavailableReason } from "../ops/load";
import { FILLS, type EmptyCopy } from "../ui/fills";
import type { ResolutionStatus } from "./module";

const tr = {
  title: "Protokoller",
  generatedAt: "Oluşturulma",
  unknown: "Bilinmiyor",
  fills: FILLS.tr,
  reasons: {} as Record<string, string>,
  bands: { coverage: "Kapsam", review: "Öneri incelemesi", clips: "Ses klipleri" },
  tiles: {
    summary: "Branş kapsamı",
    matrix: "Branş × olgunluk",
    review: "İnceleme kuyruğu",
    vocabulary: "Öneri sözlüğü",
    clips: "Klip kapsamı (residency_tr)",
  },
  total: "Branş",
  packs: "Paket",
  statuses: {
    DIRECT: "Doğrudan",
    CLUSTER: "Küme paketi",
    MISSING: "Paket yok",
    EXCLUDED: "Kapsam dışı",
  } satisfies Record<ResolutionStatus, string>,
  branch: "Branş",
  cluster: "Küme",
  status: "Durum",
  maturity: "Olgunluk",
  served: "sunuluyor",
  draft: "taslak, sunulmuyor",
  excluded: "ön görüşme paketi yok",
  noPack: "paket yok",
  coverageNote:
    "Bir branş yalnızca L1 ya da üstü bir pakete bağlandığında kapsanmış sayılır. L0 taslak adıyla gösterilir, kapsam sayılmaz.",
  proposal: "Öneri",
  target: "Hedef",
  pack: "Paket",
  evidence: "Kanıt",
  decision: "Karar",
  approvable: "onaylanabilir",
  rejectable: "reddedilebilir",
  complete: "tam",
  allowedTargets: "İzin verilen hedefler",
  unmetChecks: "Henüz üretilmeyen kanıt denetimleri",
  reviewNote:
    "Öğrenme hattı yalnızca öneri açar; değişikliği bir klinisyen kod sahibi onaylar. Konsol kararı dört gözle kaydeder, protokolü kendisi değiştirmez.",
  voice: "Ses",
  role: "Görev",
  required: "Gerekli",
  cached: "Hazır",
  missing: "Eksik",
  clipsNote:
    "Klipler yalnızca sunulan (L1 ve üstü) paketler için önceden üretilir. typed profilinde klip yoktur.",
  empties: {
    review: {
      title: "Kuyrukta öneri yok",
      why: "Öğrenme hattı kanıtı tam bir öneri açtığında burada görünür.",
    },
    matrix: {
      title: "Taksonomide branş yok",
      why: "Branş taksonomisi yüklendiğinde satırlar burada görünür.",
    },
    clips: {
      title: "Ses yok",
      why: "residency_tr profiline bir ses eklendiğinde burada görünür.",
    },
  } satisfies Record<"review" | "matrix" | "clips", EmptyCopy>,
  refusals: {
    no_credentials: "Oturum bilgisi yok; konsola giriş yapın.",
    token_refused: "Oturum doğrulanamadı; yeniden giriş yapın.",
    role_not_permitted: "Bu rol protokol modülünü göremez.",
    source_ip_refused: "Bu ağ adresinden erişilemez.",
    console_unconfigured: "Yönetici konsolu yapılandırılmamış.",
  } satisfies Record<RefusalReason, string>,
  unavailable: {
    api_base_unconfigured: "API adresi yapılandırılmamış.",
    api_unreachable: "API'ye ulaşılamıyor.",
    payload_refused:
      "API'nin yanıtı gösterilmedi: L0 bir paketi kapsam sayıyor, yazarına kendi önerisini onaylatıyor ya da typed profilinde klip gösteriyordu.",
  } satisfies Record<UnavailableReason, string>,
};

export type ProtocolsCopy = typeof tr;

const en: ProtocolsCopy = {
  title: "Protocols",
  generatedAt: "Generated",
  unknown: "Unknown",
  fills: FILLS.en,
  reasons: {},
  bands: { coverage: "Coverage", review: "Proposal review", clips: "Voice clips" },
  tiles: {
    summary: "Branch coverage",
    matrix: "Branch × maturity",
    review: "Review queue",
    vocabulary: "Proposal vocabulary",
    clips: "Clip coverage (residency_tr)",
  },
  total: "Branches",
  packs: "Packs",
  statuses: {
    DIRECT: "Direct",
    CLUSTER: "Cluster pack",
    MISSING: "No pack",
    EXCLUDED: "Excluded",
  },
  branch: "Branch",
  cluster: "Cluster",
  status: "Status",
  maturity: "Maturity",
  served: "served",
  draft: "draft, not served",
  excluded: "no intake pack",
  noPack: "no pack",
  coverageNote:
    "A branch counts as covered only when it resolves to an L1 or higher pack. An L0 draft is named and never counted.",
  proposal: "Proposal",
  target: "Target",
  pack: "Pack",
  evidence: "Evidence",
  decision: "Decision",
  approvable: "approvable",
  rejectable: "rejectable",
  complete: "complete",
  allowedTargets: "Allowed targets",
  unmetChecks: "Evidence checks not yet produced",
  reviewNote:
    "The learning pipeline only opens proposals; a clinician code owner approves the change. The console records the decision under four eyes and never changes a protocol itself.",
  voice: "Voice",
  role: "Role",
  required: "Required",
  cached: "Cached",
  missing: "Missing",
  clipsNote:
    "Clips are pre-synthesised only for served (L1 and higher) packs. The typed profile carries no clips.",
  empties: {
    review: {
      title: "No proposal in the queue",
      why: "Shows here once the learning pipeline opens a proposal with complete evidence.",
    },
    matrix: {
      title: "No branch in the taxonomy",
      why: "Rows show here once the branch taxonomy loads.",
    },
    clips: {
      title: "No voice",
      why: "Shows here once a voice is added under the residency_tr profile.",
    },
  },
  refusals: {
    no_credentials: "No session credentials; sign in to the console.",
    token_refused: "The session could not be verified; sign in again.",
    role_not_permitted: "This role cannot see the protocols module.",
    source_ip_refused: "Not reachable from this network address.",
    console_unconfigured: "The admin console is not configured.",
  },
  unavailable: {
    api_base_unconfigured: "The API address is not configured.",
    api_unreachable: "The API is unreachable.",
    payload_refused:
      "The API's answer was not shown: it counted an L0 pack as coverage, let an author approve their own proposal, or showed clips under the typed profile.",
  },
};

export const COPY: Record<Lang, ProtocolsCopy> = { tr, en };
