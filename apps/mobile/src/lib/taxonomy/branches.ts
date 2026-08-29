/**
 * INT-134 — the branch taxonomy on the device.
 *
 * `SEED_BRANCHES`/`SEED_CLUSTERS` are a projection of
 * packages/protocols/taxonomy/branches.yaml (files/09 §1 source of truth),
 * generated from that file and pinned to it field-for-field by
 * branches.test.ts — so the bundled offline list and the served feed cannot
 * drift. The seed is the LAST resort of the picker (server feed → cached
 * last-good → seed): a patient offline on a new phone still gets every
 * branch, and the picker is never empty.
 *
 * tr labels are the taxonomy's own `name_tr`, verbatim (invariant 5); this
 * module holds no copy of its own.
 */

/** Visit types, orthogonal to branch (files/09 §1), in that file's order. */
export const ALL_VISIT_TYPE_IDS = [
  "first",
  "followup",
  "preop",
  "report",
  "pregnancy_followup",
  "chronic_review",
  "post_discharge",
  "screening",
  "second_opinion",
  "teleconsult",
] as const;

export type VisitTypeId = (typeof ALL_VISIT_TYPE_IDS)[number];

export interface Branch {
  id: string;
  nameTr: string;
  cluster: string;
  visitTypes: readonly VisitTypeId[];
}

export interface Cluster {
  id: string;
  /** The cluster pack every member branch falls back to; null = no intake. */
  pack: string | null;
  /** False only for `excluded` — Acil Tıp books no pre-visit intake. */
  intake: boolean;
}

/**
 * The ten highest-volume branches (02 §3 P2 list) shown first in the picker:
 * İç Hastalıkları, Çocuk, Üroloji, Göz, KBB, Ortopedi, Kardiyoloji, Nöroloji,
 * Kadın Doğum, Dermatoloji — that list's order, not a re-ranking of it.
 */
export const COMMON_BRANCH_IDS = [
  "ic_hastaliklari",
  "cocuk_sagligi_ve_hastaliklari",
  "uroloji",
  "goz_hastaliklari",
  "kulak_burun_bogaz_hastaliklari",
  "ortopedi_ve_travmatoloji",
  "kardiyoloji",
  "noroloji",
  "kadin_hastaliklari_ve_dogum",
  "deri_ve_zuhrevi_hastaliklari",
] as const;

/** files/09 §1 "Clusters (9)", ids verbatim. */
export const SEED_CLUSTERS: readonly Cluster[] = [
  { id: "medical", pack: "cluster.medical", intake: true },
  { id: "surgical", pack: "cluster.surgical", intake: true },
  { id: "sensory", pack: "cluster.sensory", intake: true },
  { id: "womens_health", pack: "cluster.womens_health", intake: true },
  { id: "child_health", pack: "cluster.child_health", intake: true },
  { id: "mental_health", pack: "cluster.mental_health", intake: true },
  { id: "dental", pack: "cluster.dental", intake: true },
  { id: "allied_and_reports", pack: "cluster.allied_and_reports", intake: true },
  { id: "excluded", pack: null, intake: false },
];

/** Every bookable branch, in branches.yaml order (files/09 §1). */
export const SEED_BRANCHES: readonly Branch[] = [
  { id: "ic_hastaliklari", nameTr: "İç Hastalıkları", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "endokrinoloji_ve_metabolizma", nameTr: "Endokrinoloji ve Metabolizma", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "gastroenteroloji", nameTr: "Gastroenteroloji", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "nefroloji", nameTr: "Nefroloji", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "romatoloji", nameTr: "Romatoloji", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "hematoloji", nameTr: "Hematoloji", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "tibbi_onkoloji", nameTr: "Tıbbi Onkoloji", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "geriatri", nameTr: "Geriatri", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "immunoloji_ve_alerji", nameTr: "İmmünoloji ve Alerji", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "gogus_hastaliklari", nameTr: "Göğüs Hastalıkları", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "kardiyoloji", nameTr: "Kardiyoloji", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "noroloji", nameTr: "Nöroloji", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "enfeksiyon_hastaliklari", nameTr: "Enfeksiyon Hastalıkları", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "deri_ve_zuhrevi_hastaliklari", nameTr: "Deri ve Zührevi Hastalıkları", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "fiziksel_tip_ve_rehabilitasyon", nameTr: "Fiziksel Tıp ve Rehabilitasyon", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "aile_hekimligi", nameTr: "Aile Hekimliği", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "tibbi_genetik", nameTr: "Tıbbi Genetik", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "nukleer_tip", nameTr: "Nükleer Tıp", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "radyasyon_onkolojisi", nameTr: "Radyasyon Onkolojisi", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "algoloji", nameTr: "Algoloji", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "klinik_norofizyoloji", nameTr: "Klinik Nörofizyoloji", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "spor_hekimligi", nameTr: "Spor Hekimliği", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "sualti_ve_hiperbarik_tip", nameTr: "Sualtı ve Hiperbarik Tıp", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "hava_ve_uzay_hekimligi", nameTr: "Hava ve Uzay Hekimliği", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "tibbi_ekoloji_ve_hidroklimatoloji", nameTr: "Tıbbi Ekoloji ve Hidroklimatoloji", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "is_ve_meslek_hastaliklari", nameTr: "İş ve Meslek Hastalıkları", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "halk_sagligi", nameTr: "Halk Sağlığı", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "getat", nameTr: "GETAT", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "diyabet_poliklinigi", nameTr: "Diyabet polikliniği", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "obezite_poliklinigi", nameTr: "Obezite polikliniği", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "sigara_birakma_poliklinigi", nameTr: "Sigara Bırakma polikliniği", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "uyku_poliklinigi", nameTr: "Uyku polikliniği", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "yasli_sagligi_poliklinigi", nameTr: "Yaşlı Sağlığı polikliniği", cluster: "medical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "genel_cerrahi", nameTr: "Genel Cerrahi", cluster: "surgical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "gastroenteroloji_cerrahisi", nameTr: "Gastroenteroloji Cerrahisi", cluster: "surgical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "cerrahi_onkoloji", nameTr: "Cerrahi Onkoloji", cluster: "surgical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "beyin_ve_sinir_cerrahisi", nameTr: "Beyin ve Sinir Cerrahisi", cluster: "surgical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "kalp_ve_damar_cerrahisi", nameTr: "Kalp ve Damar Cerrahisi", cluster: "surgical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "gogus_cerrahisi", nameTr: "Göğüs Cerrahisi", cluster: "surgical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "ortopedi_ve_travmatoloji", nameTr: "Ortopedi ve Travmatoloji", cluster: "surgical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "el_cerrahisi", nameTr: "El Cerrahisi", cluster: "surgical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "uroloji", nameTr: "Üroloji", cluster: "surgical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "plastik_rekonstruktif_ve_estetik_cerrahi", nameTr: "Plastik, Rekonstrüktif ve Estetik Cerrahi", cluster: "surgical", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "anesteziyoloji", nameTr: "Anesteziyoloji", cluster: "surgical", visitTypes: ["preop"] },
  { id: "goz_hastaliklari", nameTr: "Göz Hastalıkları", cluster: "sensory", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "kulak_burun_bogaz_hastaliklari", nameTr: "Kulak Burun Boğaz Hastalıkları", cluster: "sensory", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "odyoloji", nameTr: "Odyoloji", cluster: "sensory", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "kadin_hastaliklari_ve_dogum", nameTr: "Kadın Hastalıkları ve Doğum", cluster: "womens_health", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "perinatoloji", nameTr: "Perinatoloji", cluster: "womens_health", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "jinekolojik_onkoloji", nameTr: "Jinekolojik Onkoloji", cluster: "womens_health", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "ureme_endokrinolojisi_ve_infertilite", nameTr: "Üreme Endokrinolojisi ve İnfertilite", cluster: "womens_health", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "gebe_poliklinigi", nameTr: "Gebe polikliniği", cluster: "womens_health", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "cocuk_sagligi_ve_hastaliklari", nameTr: "Çocuk Sağlığı ve Hastalıkları", cluster: "child_health", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "cocuk_kardiyolojisi", nameTr: "Çocuk Kardiyolojisi", cluster: "child_health", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "cocuk_norolojisi", nameTr: "Çocuk Nörolojisi", cluster: "child_health", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "cocuk_endokrinolojisi", nameTr: "Çocuk Endokrinolojisi", cluster: "child_health", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "cocuk_gastroenterolojisi", nameTr: "Çocuk Gastroenterolojisi", cluster: "child_health", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "cocuk_hematolojisi_ve_onkolojisi", nameTr: "Çocuk Hematolojisi ve Onkolojisi", cluster: "child_health", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "cocuk_enfeksiyon_hastaliklari", nameTr: "Çocuk Enfeksiyon Hastalıkları", cluster: "child_health", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "cocuk_immunolojisi_ve_alerjisi", nameTr: "Çocuk İmmünolojisi ve Alerjisi", cluster: "child_health", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "cocuk_nefrolojisi", nameTr: "Çocuk Nefrolojisi", cluster: "child_health", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "cocuk_romatolojisi", nameTr: "Çocuk Romatolojisi", cluster: "child_health", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "cocuk_gogus_hastaliklari", nameTr: "Çocuk Göğüs Hastalıkları", cluster: "child_health", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "cocuk_metabolizma_hastaliklari", nameTr: "Çocuk Metabolizma Hastalıkları", cluster: "child_health", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "cocuk_genetik_hastaliklari", nameTr: "Çocuk Genetik Hastalıkları", cluster: "child_health", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "neonatoloji", nameTr: "Neonatoloji", cluster: "child_health", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "gelisimsel_pediatri", nameTr: "Gelişimsel Pediatri", cluster: "child_health", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "sosyal_pediatri", nameTr: "Sosyal Pediatri", cluster: "child_health", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "cocuk_cerrahisi", nameTr: "Çocuk Cerrahisi", cluster: "child_health", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "cocuk_urolojisi", nameTr: "Çocuk Ürolojisi", cluster: "child_health", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "ruh_sagligi_ve_hastaliklari", nameTr: "Ruh Sağlığı ve Hastalıkları", cluster: "mental_health", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "cocuk_ve_ergen_ruh_sagligi", nameTr: "Çocuk ve Ergen Ruh Sağlığı", cluster: "mental_health", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "amatem", nameTr: "AMATEM", cluster: "mental_health", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "cematem", nameTr: "ÇEMATEM", cluster: "mental_health", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "klinik_psikoloji_poliklinigi", nameTr: "Klinik Psikoloji polikliniği", cluster: "mental_health", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "agiz_dis_ve_cene_cerrahisi", nameTr: "Ağız, Diş ve Çene Cerrahisi", cluster: "dental", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "dis_hekimligi", nameTr: "Diş Hekimliği", cluster: "dental", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "ortodonti", nameTr: "Ortodonti", cluster: "dental", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "periodontoloji", nameTr: "Periodontoloji", cluster: "dental", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "endodonti", nameTr: "Endodonti", cluster: "dental", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "pedodonti", nameTr: "Pedodonti", cluster: "dental", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "protetik", nameTr: "Protetik", cluster: "dental", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "restoratif", nameTr: "Restoratif", cluster: "dental", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "agiz_dis_cene_radyolojisi", nameTr: "Ağız-Diş-Çene Radyolojisi", cluster: "dental", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "saglik_kurulu", nameTr: "Sağlık Kurulu", cluster: "allied_and_reports", visitTypes: ["report"] },
  { id: "beslenme_ve_diyet", nameTr: "Beslenme ve Diyet", cluster: "allied_and_reports", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "fizyoterapi", nameTr: "Fizyoterapi", cluster: "allied_and_reports", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "hemsirelik_egitim_poliklinikleri", nameTr: "Hemşirelik/eğitim poliklinikleri", cluster: "allied_and_reports", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "asi", nameTr: "Aşı", cluster: "allied_and_reports", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "evde_saglik", nameTr: "Evde Sağlık", cluster: "allied_and_reports", visitTypes: ALL_VISIT_TYPE_IDS },
  { id: "adli_tip", nameTr: "Adli Tıp", cluster: "allied_and_reports", visitTypes: ["report"] },
  { id: "acil_tip", nameTr: "Acil Tıp", cluster: "excluded", visitTypes: [] },
];

// --- picker helpers ---------------------------------------------------------------------

/**
 * Turkish-aware fold for search: dotted/dotless i, ş, ğ, ü, ö, ç and the
 * circumflex vowels all collapse, so a patient typing ASCII on a hurried
 * keyboard finds "Göğüs Hastalıkları" and one typing Turkish finds it too.
 * Explicit table rather than toLocaleLowerCase("tr") — the fold must not
 * depend on the runtime's ICU data being complete.
 */
const TR_FOLD: Record<string, string> = {
  ı: "i",
  İ: "i",
  I: "i",
  ş: "s",
  Ş: "s",
  ğ: "g",
  Ğ: "g",
  ü: "u",
  Ü: "u",
  ö: "o",
  Ö: "o",
  ç: "c",
  Ç: "c",
  â: "a",
  Â: "a",
  î: "i",
  Î: "i",
  û: "u",
  Û: "u",
};

export function foldTr(value: string): string {
  let folded = "";
  for (const character of value) {
    folded += TR_FOLD[character] ?? character.toLowerCase();
  }
  return folded;
}

export function branchById(branches: readonly Branch[], id: string): Branch | undefined {
  return branches.find((branch) => branch.id === id);
}

/** Only branches whose cluster books intake — Acil Tıp is RED routing only. */
export function intakeBranches(
  branches: readonly Branch[],
  clusters: readonly Cluster[],
): Branch[] {
  const bookable = new Set(clusters.filter((c) => c.intake).map((c) => c.id));
  return branches.filter((branch) => bookable.has(branch.cluster));
}

/** Common branches first (02 §3 order), then everything else by tr name. */
export function orderBranches(branches: readonly Branch[]): Branch[] {
  const rank = new Map<string, number>(COMMON_BRANCH_IDS.map((id, index) => [id, index]));
  const common: Branch[] = [];
  const rest: Branch[] = [];
  for (const branch of branches) {
    if (rank.has(branch.id)) {
      common.push(branch);
    } else {
      rest.push(branch);
    }
  }
  common.sort((a, b) => (rank.get(a.id) ?? 0) - (rank.get(b.id) ?? 0));
  rest.sort((a, b) => a.nameTr.localeCompare(b.nameTr, "tr"));
  return [...common, ...rest];
}

/** Folded substring match over the tr name, in the picker's own order. */
export function searchBranches(branches: readonly Branch[], query: string): Branch[] {
  const needle = foldTr(query.trim());
  if (needle.length === 0) {
    return orderBranches(branches);
  }
  return orderBranches(branches.filter((branch) => foldTr(branch.nameTr).includes(needle)));
}

/**
 * What the picker renders: the ordered head while browsing (the cap keeps a
 * 90-row list from burying the common ten), every match while searching.
 */
export function visibleBranches(
  branches: readonly Branch[],
  query: string,
  limit: number,
): Branch[] {
  if (query.trim().length === 0) {
    return orderBranches(branches).slice(0, limit);
  }
  return searchBranches(branches, query);
}
