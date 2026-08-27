/**
 * Turkish strings — the source of truth (CLAUDE.md invariant 5: tr first).
 * Register: `siz` everywhere; `-in` for short in-flow buttons, `-iniz` for
 * instructional prose (00 §2 — match e-Nabız/MHRS, never Microsoft's warning).
 * Sentence case only; never ALL-CAPS; % precedes numbers.
 *
 * Patient-facing clinical/legal sentences are marked [REVIEW] — they ship to
 * production only from docs/legal/strings.yaml with clinician/counsel
 * sign-off (invariant 18); here they gate the dev shell.
 */
export const tr = {
  "app.name": "Vizite",
  "app.tagline": "Muayeneden önce, anlattıklarınız hekiminize ulaşsın.",
  // [REVIEW] fixed non-diagnosis line, 06 §7 family
  "app.disclaimer": "Vizite tanı koymaz. Anlattıklarınız hekim değerlendirmesinin yerine geçmez.",

  "tabs.today": "Bugün",
  "tabs.visits": "Vizitlerim",
  "tabs.records": "Kayıtlarım",
  "tabs.wellbeing": "İyilik hâli",
  "tabs.me": "Profilim",

  "welcome.title": "Hoş geldiniz",
  "welcome.body":
    "Vizite, muayeneden önce şikâyetlerinizi sesli ya da yazılı olarak toplar ve hekiminize düzenli bir ön not iletir.",
  "welcome.devSignIn": "Deneme hesabıyla girin",
  "welcome.devNote":
    "Bu ekran geliştirme sürümüne özeldir; gerçek giriş telefon doğrulamasıyla yapılır.",

  "today.nextVisit": "Sıradaki vizit",
  "today.prepareCta": "Muayeneye hazırlan (≈3 dk)",
  "today.continueCta": "Devam et",
  "today.noVisit": "Planlanmış bir vizitiniz yok.",
  "today.addVisit": "Vizit ekle",
  "today.uploadQuick": "Kayıt yükle",

  "status.draft": "Taslak",
  "status.sent": "Gönderildi",
  "status.viewed": "Hekim görüntüledi",
  "status.filed": "Dosyaya eklendi",

  "visits.title": "Vizitlerim",
  "visits.upcoming": "Yaklaşan",
  "visits.past": "Geçmiş",
  "visits.empty": "Henüz vizit eklemediniz.",
  "visits.new.title": "Yeni vizit",
  "visits.new.manual": "Elle ekleyin",
  "visits.new.hint": "Hastane, bölüm ve tarihi girin; MHRS mesajından ekleme yakında.",
  "visits.detail.summary": "Özet",
  "visits.detail.noteStatus": "Not durumu",
  "visits.detail.notStarted": "Görüşme henüz başlamadı.",

  "records.title": "Kayıtlarım",
  "records.empty": "Henüz kayıt yok. Tahlil ve raporlarınızı vizitten önce ekleyebilirsiniz.",
  "records.synthetic": "Örnek veri — sentetik",

  "wellbeing.title": "İyilik hâli",
  "wellbeing.intro":
    "Kendinizi nasıl hissettiğinizi takip edin; paylaşım her zaman sizin kontrolünüzde.",
  "wellbeing.empty": "Henüz bir kayıt yok.",

  "me.title": "Profilim",
  "me.consents": "İzinleriniz",
  "me.language": "Dil",
  "me.learned": "Hakkımda öğrendikleri",
  "me.learnedEmpty": "Vizite sizin onayınız olmadan hiçbir bilgiyi kalıcı olarak öğrenmez.",
  "me.signOut": "Çıkış yapın",
  "me.syntheticBadge": "Sentetik deneme hesabı",

  "consent.core": "Temel hizmet",
  "consent.voice": "Sesli görüşme",
  "consent.wellbeing": "İyilik hâli taraması",
  "consent.documents": "Belge yükleme",
  "consent.on": "Açık",
  "consent.off": "Kapalı",
} as const;

export type MessageKey = keyof typeof tr;
