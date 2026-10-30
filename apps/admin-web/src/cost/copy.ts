/**
 * INT-565 — the Cost page's words, `tr` the source of truth (invariant 5);
 * `en` mirrors it key for key. A missing price is worded as missing, never as
 * zero; a total with a missing part is withheld, never summed (INT-190).
 */
import type { Lang } from "../ops/copy";
import type { RefusalReason, UnavailableReason } from "../ops/load";
import { FILLS, type EmptyCopy } from "../ui/fills";

const tr = {
  title: "Maliyet",
  unknown: "Bilinmiyor",
  fills: FILLS.tr,
  reasons: {} as Record<string, string>,
  yes: "evet",
  no: "hayır",
  bands: { prices: "Fiyatlar", sessions: "Oturum başına maliyet", budgets: "Bütçeler" },
  tiles: {
    config: "Fiyat dosyası",
    components: "Bileşenler",
    window: { day: "Son gün", month: "Son ay" } as Record<string, string>,
    budgets: "Bütçeler ve uyarılar",
  },
  path: "Dosya",
  digest: "Özet (sha256, ilk 128 bit)",
  blocker: "Açık engel",
  currency: "Para birimi",
  usageSource: "Kullanım kaynağı bağlı",
  component: "Bileşen",
  vendor: "Sağlayıcı",
  unit: "Birim",
  attribution: "Dağıtım",
  price: "Fiyat",
  profile: "Profil",
  quantity: "Miktar",
  cost: "Maliyet",
  sessions: "Oturum",
  total: "Profil toplamı",
  budget: "Bütçe",
  scope: "Kapsam",
  period: "Dönem",
  limit: "Sınır",
  spend: "Harcama",
  status: "Durum",
  priceNotConfigured: "fiyat girilmemiş",
  vendorNotConfigured: "sağlayıcı seçilmemiş",
  budgetNotConfigured: "bütçe girilmemiş",
  allVendors: "tüm sağlayıcılar",
  withheld: "eksik parça var; toplam gösterilmez",
  statuses: {
    within: "bütçe içinde",
    exceeded: "bütçe aşıldı",
    not_evaluable: "harcama bilinmediği için değerlendirilemez",
    not_configured: "bütçe girilmemiş",
  } as Record<string, string>,
  configNote:
    "Fiyatlar ve bütçeler yalnızca sahibin doldurduğu dosyadan gelir; boş bir fiyat sıfır sayılmaz.",
  empties: {
    components: {
      title: "Bileşen yok",
      why: "Fiyat dosyasına bir bileşen eklendiğinde burada görünür.",
    },
    perSession: {
      title: "Satır yok",
      why: "Bir bileşen bir profile bağlandığında burada görünür.",
    },
    totals: {
      title: "Toplam yok",
      why: "Bir profilin bileşenleri olduğunda burada görünür.",
    },
    budgets: {
      title: "Bütçe yok",
      why: "Fiyat dosyasına bir bütçe eklendiğinde burada görünür.",
    },
  } satisfies Record<"components" | "perSession" | "totals" | "budgets", EmptyCopy>,
  refusals: {
    no_credentials: "Oturum bilgisi yok; konsola giriş yapın.",
    token_refused: "Oturum doğrulanamadı; yeniden giriş yapın.",
    role_not_permitted: "Bu rol maliyet modülünü göremez.",
    source_ip_refused: "Bu ağ adresinden erişilemez.",
    console_unconfigured: "Yönetici konsolu yapılandırılmamış.",
  } satisfies Record<RefusalReason, string>,
  unavailable: {
    api_base_unconfigured: "API adresi yapılandırılmamış.",
    api_unreachable: "API'ye ulaşılamıyor.",
    payload_refused:
      "API'nin yanıtı gösterilmedi: fiyatı ya da gözlenmiş kullanımı olmayan bir rakam, eksik parçalı bir toplam ya da dayanaksız bir bütçe kararı taşıyordu.",
  } satisfies Record<UnavailableReason, string>,
};

export type CostCopy = typeof tr;

const en: CostCopy = {
  title: "Cost",
  unknown: "Unknown",
  fills: FILLS.en,
  reasons: {},
  yes: "yes",
  no: "no",
  bands: { prices: "Prices", sessions: "Cost per session", budgets: "Budgets" },
  tiles: {
    config: "Price file",
    components: "Components",
    window: { day: "Last day", month: "Last month" },
    budgets: "Budgets and alerts",
  },
  path: "File",
  digest: "Digest (sha256, first 128 bits)",
  blocker: "Open blocker",
  currency: "Currency",
  usageSource: "Usage source wired",
  component: "Component",
  vendor: "Vendor",
  unit: "Unit",
  attribution: "Attribution",
  price: "Price",
  profile: "Profile",
  quantity: "Quantity",
  cost: "Cost",
  sessions: "Sessions",
  total: "Profile total",
  budget: "Budget",
  scope: "Scope",
  period: "Period",
  limit: "Limit",
  spend: "Spend",
  status: "Status",
  priceNotConfigured: "price not configured",
  vendorNotConfigured: "vendor not chosen",
  budgetNotConfigured: "budget not configured",
  allVendors: "all vendors",
  withheld: "a part is missing; no total shown",
  statuses: {
    within: "within budget",
    exceeded: "budget exceeded",
    not_evaluable: "not evaluable: the spend is not known",
    not_configured: "budget not configured",
  },
  configNote:
    "Prices and budgets come only from the owner-filled file; an empty price is never counted as zero.",
  empties: {
    components: {
      title: "No component",
      why: "Shows here once a component is added to the price file.",
    },
    perSession: {
      title: "No row",
      why: "Shows here once a component is attached to a profile.",
    },
    totals: {
      title: "No total",
      why: "Shows here once a profile has components.",
    },
    budgets: {
      title: "No budget",
      why: "Shows here once a budget is added to the price file.",
    },
  },
  refusals: {
    no_credentials: "No session credentials; sign in to the console.",
    token_refused: "The session could not be verified; sign in again.",
    role_not_permitted: "This role cannot see the cost module.",
    source_ip_refused: "Not reachable from this network address.",
    console_unconfigured: "The admin console is not configured.",
  },
  unavailable: {
    api_base_unconfigured: "The API address is not configured.",
    api_unreachable: "The API is unreachable.",
    payload_refused:
      "The API's answer was not shown: it carried a figure with no price or no observed usage, a total with a missing part, or an unsound budget verdict.",
  },
};

export const COPY: Record<Lang, CostCopy> = { tr, en };
