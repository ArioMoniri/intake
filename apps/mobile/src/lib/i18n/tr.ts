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
  "app.name": "Önvizit",
  "app.tagline": "Muayeneden önce, anlattıklarınız hekiminize ulaşsın.",
  // [REVIEW] fixed non-diagnosis line, 06 §7 family
  "app.disclaimer": "Önvizit tanı koymaz. Anlattıklarınız hekim değerlendirmesinin yerine geçmez.",

  "tabs.today": "Bugün",
  "tabs.visits": "Vizitlerim",
  "tabs.records": "Kayıtlarım",
  "tabs.wellbeing": "İyilik hâli",
  "tabs.me": "Profilim",

  "welcome.body":
    "Önvizit, muayeneden önce şikâyetlerinizi sesli ya da yazılı olarak toplar ve hekiminize düzenli bir ön not iletir.",
  "welcome.devSignIn": "Deneme hesabıyla girin",
  "welcome.devNote":
    "Bu ekran geliştirme sürümüne özeldir; gerçek giriş telefon doğrulamasıyla yapılır.",

  "welcome.phoneCta": "Telefonla devam edin",

  // INT-131 onboarding — 02 §8.2: the why-line, generic errors, visible
  // resend limits; siz register, ≤ B1.
  "auth.phone.title": "Telefonla giriş",
  "auth.phone.why": "Numaranız yalnızca giriş için kullanılır.",
  "auth.phone.label": "Telefon numaranız",
  "auth.phone.hint": "Başında 05 ile yazın, örneğin 0532 111 44 55.",
  "auth.phone.cta": "Kod isteyin",
  "auth.phone.invalid": "Numarayı kontrol edin; 05 ile başlamalı.",
  "auth.otp.title": "Doğrulama kodu",
  "auth.otp.body": "Telefonunuza gelen altı haneli kodu girin.",
  "auth.otp.verifyCta": "Giriş yapın",
  "auth.otp.resend": "Kodu yeniden isteyin",
  "auth.otp.resendWait": "Yeni kod isteyebilmek için kalan süre:",
  "auth.otp.devPeek": "Kodu getirin (geliştirme)",
  "auth.error.generic": "Bir sorun oldu. Lütfen yeniden deneyin.",
  "auth.error.limited": "Çok sık denediniz. Lütfen biraz bekleyip yeniden deneyin.",
  "auth.error.code": "Kod doğrulanamadı. Kodu kontrol edin ya da yeni kod isteyin.",
  "auth.error.network": "Sunucuya ulaşılamadı. Bağlantınızı kontrol edin.",
  // INT-328: a release build with no configured server — not the patient's
  // connection, so it must not read like auth.error.network.
  "auth.error.unconfigured":
    "Uygulamanın bu sürümü henüz hizmete bağlı değil. Lütfen uygulamayı güncelleyip yeniden deneyin.",
  "auth.error.attestation":
    "Bu cihaz doğrulanamadı. Lütfen uygulamayı güncelleyip yeniden deneyin.",
  // INT-344: why a release build could not prove the device
  "auth.error.attestationUnsupported":
    "Bu cihaz güvenli girişi desteklemiyor. Lütfen başka bir telefondan deneyin.",
  "auth.error.attestationPending":
    "Bu cihazda güvenli giriş henüz açılmadı. Lütfen daha sonra yeniden deneyin.",
  "auth.error.attestationService":
    "Cihaz doğrulama hizmetine şu an ulaşılamıyor. Lütfen biraz sonra yeniden deneyin.",
  "auth.biometric.prompt": "Devam etmek için kimliğinizi doğrulayın.",
  "auth.biometric.locked": "Ekran kilitli",
  "auth.biometric.retry": "Yeniden deneyin",
  "auth.integrity.warnTitle": "Cihaz güvenliği",
  "auth.integrity.warnBody":
    "Bu cihazda güvenlik değişikliği görünüyor. Görüşme sesli değil, yazılı olarak devam eder.",

  "today.nextVisit": "Sıradaki vizit",
  "today.prep": "Vizit hazırlığı",
  "today.prepareCta": "Muayeneye hazırlanın (≈3 dk)",
  "today.continueCta": "Devam edin",
  "today.noVisit": "Planlanmış bir vizitiniz yok.",
  "today.addVisit": "Vizit ekleyin",

  "status.draft": "Taslak",
  "status.sent": "Gönderildi",
  "status.viewed": "Hekim görüntüledi",
  "status.filed": "Dosyaya eklendi",

  "visits.title": "Vizitlerim",
  "visits.upcoming": "Yaklaşan",
  "visits.past": "Geçmiş",
  "visits.empty": "Henüz vizit eklemediniz.",
  "visits.noDate": "Tarih eklenmedi",
  "visits.new.title": "Yeni vizit",
  "visits.new.hint": "Randevu mesajınızı yapıştırın ya da bilgileri elle girin.",
  "visits.new.hospital": "Hastane",
  "visits.new.branch": "Poliklinik",
  "visits.new.branchSearch": "Poliklinik arayın",
  "visits.new.branchChange": "Değiştirin",
  "visits.new.branchMore": "Aramak için yazmaya başlayın.",
  "visits.new.visitType": "Vizit türü",
  "visits.new.date": "Tarih",
  "visits.new.dateHint": "Yıl-ay-gün biçiminde yazın, örneğin 2026-09-15.",
  "visits.new.dateOptional": "Randevu tarihiniz belli değilse boş bırakın.",
  "visits.new.save": "Vizit ekleyin",
  "visits.new.missingFields": "Lütfen hastane, poliklinik ve vizit türünü seçin.",
  "visits.new.badDate": "Tarihi yıl-ay-gün biçiminde yazın.",
  // MHRS randevu mesajı: telefonda okunur, yalnızca yapı saklanır
  "visits.new.smsTitle": "Randevu mesajından ekleyin",
  "visits.new.smsHint": "MHRS randevu mesajınızı buraya yapıştırın. Mesajın kendisi kaydedilmez.",
  "visits.new.smsAction": "Mesajı okuyun",
  "visits.new.smsFilled": "Randevu bilgileriniz dolduruldu. Lütfen kontrol edin.",
  "visits.new.smsUnknownBranch": "Poliklinik adını tanıyamadık. Listeden siz seçin.",
  "visits.new.smsNoDate": "Mesajda tarih bulamadık. Tarihi siz ekleyin.",
  // INT-400: the date reads as two days, or two dates are printed; the field
  // is left empty and the patient writes the date (no reading is guessed)
  "visits.new.smsAmbiguousDate":
    "Mesajdaki tarihten randevunuzun hangi gün olduğunu kesin anlayamadık. Tarihi aşağıya siz yazın.",
  "visits.new.smsUnreadable": "Bu mesajı okuyamadık. Bilgileri elle girebilirsiniz.",
  "visits.new.ocrUnavailable": "Görüntüden okuma henüz açık değil. Mesajı metin olarak yapıştırın.",
  // INT-537 — vizit başlangıcında temel hizmet izni, yerinde sorulur. Yalnızca
  // arayüz metnidir; onay metninin kendisi docs/legal'den, damgasıyla gelir.
  "visits.new.core.kicker": "İzin gerekli",
  "visits.new.core.title": "Vizit eklemek için temel hizmet izni gerekir",
  "visits.new.core.body":
    "Bu izin olmadan ön görüşme yapılamaz. İzin metnini okuyup karar verebilirsiniz. İzni istediğiniz an geri çekebilirsiniz.",
  "visits.new.core.staleBody":
    "Temel hizmet izninin metni güncellendi. Vizit eklemek için yeni metni okuyup yeniden onay vermeniz gerekir.",
  "visits.new.core.pendingBody":
    "Bu izin olmadan ön görüşme yapılamaz. İzin metni henüz hazırlanıyor. Metin yayımlanınca okuyup karar verebilirsiniz.",
  "visits.new.core.cta": "İzin metnini okuyun",
  "visits.new.core.pendingCta": "İzin sayfasına gidin",
  // Vizit türleri — files/09 §1
  "visits.type.first": "İlk başvuru",
  "visits.type.followup": "Kontrol",
  "visits.type.preop": "Ameliyat öncesi",
  "visits.type.report": "Rapor",
  "visits.type.pregnancy_followup": "Gebe takibi",
  "visits.type.chronic_review": "Süregelen hastalık değerlendirmesi",
  "visits.type.post_discharge": "Taburculuk sonrası",
  "visits.type.screening": "Tarama",
  "visits.type.second_opinion": "İkinci görüş",
  "visits.type.teleconsult": "Uzaktan görüşme",
  "visits.detail.noteStatus": "Not durumu",
  "visits.detail.notStarted": "Görüşme henüz başlamadı.",

  // Takvim (calendar) görünümü + Geçmiş (past) listesi (02 §4). Ay/gün adları
  // Intl'den gelir (components/VisitCard.tsx ile aynı kaynak); burada yalnızca
  // ekranın kendi metinleri var.
  "visits.view.label": "Görünüm",
  "visits.view.list": "Liste",
  "visits.view.calendar": "Takvim",
  "visits.pastEmpty": "Geçmiş vizitiniz yok.",
  "visits.calendar.prevMonth": "Önceki ay",
  "visits.calendar.nextMonth": "Sonraki ay",
  "visits.calendar.hasVisits": "vizitiniz var",
  "visits.calendar.noVisitsOnDay": "Bu gün için vizitiniz yok.",
  "visits.calendar.monthEmpty": "Bu ayda vizitiniz yok.",

  "records.title": "Kayıtlarım",
  "records.synthetic": "Örnek veri — sentetik",
  "records.guide.kicker": "Belgeleriniz",
  "records.guide.title": "Raporlarınız tek yerde",
  "records.guide.body":
    "Tahlil sonuçlarınızı ve raporlarınızı vizitten önce buraya ekleyebilirsiniz. Belgeler sizin dosyanızda kalır; hekiminizle paylaşım her zaman sizin onayınızla olur.",
  // INT-229 — real document upload (Kayıtlarım)
  "records.devNote":
    "Deneme hesabı: bu liste örnektir. Belge yükleme, telefonla doğrulanan gerçek hesapta açılır.",
  "records.upload": "Belge yükleyin",
  "records.uploading": "Yükleniyor…",
  "records.state.scanning": "Taranıyor",
  "records.state.ready": "Hazır",
  "records.state.rejected": "Reddedildi",
  "records.doc.pdf": "PDF belge",
  "records.doc.image": "Görsel",
  "records.scanningInfo": "Belge güvenlik taramasında. Hazır olunca açabilirsiniz.",
  "records.err.type": "Bu dosya türü desteklenmiyor. PDF, JPEG veya PNG seçin.",
  "records.err.size": "Dosya çok büyük. En çok 20 MB yükleyebilirsiniz.",
  "records.err.network": "Bağlantı kurulamadı. Lütfen daha sonra tekrar deneyin.",
  "records.err.session": "Oturumunuz sona erdi. Lütfen yeniden giriş yapın.",
  "records.err.consent":
    "Belge izniniz kapalı görünüyor. İzinlerinizi Profilim sayfasından açabilirsiniz.",
  "records.err.coreConsent":
    "Temel hizmet izniniz kapalı görünüyor. İzinlerinizi Profilim sayfasından açabilirsiniz.",
  "records.err.scanUnavailable":
    "Belge taraması şu anda yapılamıyor. Lütfen daha sonra tekrar deneyin.",
  "records.err.rejected": "Belge güvenlik taramasını geçemedi ve açılmayacak.",
  "records.err.generic": "Bir sorun oluştu. Lütfen daha sonra tekrar deneyin.",
  "records.consent.kicker": "İzin gerekli",
  "records.consent.title": "Belgeler için izniniz kapalı",
  "records.consent.body":
    "Belgelerinizi görmek ve yüklemek için belge iznini açmanız gerekir. İzinlerinizi istediğiniz an değiştirebilirsiniz.",
  "records.consent.cta": "İzinlere gidin",
  "records.needVisit.kicker": "Önce vizit",
  "records.needVisit.title": "Belgeler bir vizite eklenir",
  "records.needVisit.body":
    "Belge yüklemek için önce bir vizit ekleyin. Vizitlerim sayfasından veya buradan ekleyebilirsiniz.",
  "records.offline.kicker": "Bağlantı yok",
  "records.offline.title": "Sunucuya ulaşılamıyor",
  "records.offline.body":
    "Belgeleriniz şu anda listelenemiyor. Bağlantı gelince tekrar deneyin; yüklediğiniz belgeler kaybolmaz.",
  "records.retry": "Tekrar deneyin",
  "records.visit.kicker": "Vizit",
  "records.visit.choose": "Belgenin ekleneceği viziti seçin.",

  // INT-138 — camera capture, the reading (extraction) state, confirm cards
  // and the provenance locator. `summary` on a card is the DOCUMENT's own
  // line, so it has no key here: it is document content rendered back for
  // confirmation, never authored clinical copy.
  "records.camera": "Fotoğraf çekin",
  "records.err.camera": "Kamera izni kapalı. Telefon ayarlarından açabilirsiniz.",
  "records.state.reading": "Okunuyor",
  "records.reading.kicker": "Belge okuma",
  "records.reading.title": "Belgeleriniz henüz okunmuyor",
  "records.reading.body":
    "Belgeleriniz güvenle saklanıyor. İçlerindeki bilgiler şimdilik otomatik okunmuyor.",
  "records.reading.refused":
    "Bu belgeden gelen bilgiler gösterilemedi. Belgenizin kendisi kaydınızda duruyor.",
  "records.confirm.kicker": "Onayınız bekleniyor",
  "records.confirm.intro":
    "Aşağıdaki satırlar belgenizden alındı. Yalnızca onayladıklarınız notunuza eklenir.",
  "records.card.yes": "Evet, doğru",
  "records.card.no": "Hayır, doğru değil",
  "records.card.yesHint": "İki kez dokunmak bu satırı onaylar.",
  "records.card.noHint": "İki kez dokunmak bu satırı notunuzun dışında bırakır.",
  "records.card.show": "Belgede gösterin",
  "records.card.hide": "Belgedeki yeri kapatın",
  "records.card.showHint": "İki kez dokunmak satırın belgedeki yerini gösterir.",
  "records.card.unitConflict":
    "Bu satırdaki birim beklenenden farklı. Değer belgede yazdığı gibi bırakıldı.",
  "records.card.confirmed": "Onayladınız",
  "records.card.declined": "Notunuza eklenmeyecek",
  "records.card.notSaved": "Onayınız kaydedilemedi. Lütfen daha sonra tekrar deneyin.",
  "records.prov.page": "Sayfa",
  "records.prov.figure": "Belgedeki yerin şeması",
  "records.prov.top": "Sayfanın üst bölümü",
  "records.prov.middle": "Sayfanın orta bölümü",
  "records.prov.bottom": "Sayfanın alt bölümü",
  "records.prov.open": "Belgeyi açın",

  "wellbeing.title": "İyilik hâli",
  "wellbeing.intro":
    "Kendinizi nasıl hissettiğinizi takip edin; paylaşım her zaman sizin kontrolünüzde.",
  "wellbeing.guide.how.kicker": "Nasıl işleyecek",
  "wellbeing.guide.how.title": "Bu alan sizin için hazırlanıyor",
  "wellbeing.guide.how.body":
    "Hazır olduğunda kendinizi nasıl hissettiğinizi buradan kısa adımlarla kaydedebileceksiniz. Kayıtlar yalnızca sizin profilinizde tutulur.",
  "wellbeing.guide.privacy.kicker": "Gizlilik",
  "wellbeing.guide.privacy.title": "Yazdıklarınız size ait",
  "wellbeing.guide.privacy.body":
    "Bu alandaki kayıtlar izniniz olmadan kimseyle paylaşılmaz. İzinlerinizi Profilim sayfasından istediğiniz an değiştirebilirsiniz.",
  "wellbeing.guide.share.kicker": "Paylaşım",
  "wellbeing.guide.share.title": "Neyin paylaşılacağına siz karar verirsiniz",
  "wellbeing.guide.share.body":
    "Hekiminize bir not gitmeden önce içeriğini her zaman görürsünüz. Bir bölümü paylaşmamayı seçmek gönderimi engellemez.",

  "me.title": "Profilim",
  "me.consents": "İzinleriniz",
  "me.language": "Dil",
  "me.learned": "Hakkımda öğrendikleri",
  "me.learnedEmpty": "Önvizit sizin onayınız olmadan hiçbir bilgiyi kalıcı olarak öğrenmez.",
  "learned.guide.kicker": "Şeffaflık",
  "learned.guide.title": "Hiçbir şey sessizce öğrenilmez",
  "learned.guide.body":
    "Önvizit sizinle ilgili kalıcı bir bilgiyi yalnızca siz onaylarsanız saklar. Saklanan her bilgi bu listede görünür ve dilediğinizde kaldırılabilir.",
  // INT-140 — her bilginin nereden geldiği, nerede tutulduğu, kimin gördüğü
  // ve nasıl silineceği. Yeniden onay ziyaret hazırlığında sorulur.
  "learned.shareLabel": "Hekimle paylaşılsın",
  "learned.origin.record": "Kaydınızda saklanıyor",
  "learned.origin.device": "Yalnızca bu telefonda",
  "learned.value.unreadable": "Kaydedilmiş bir yanıt",
  "learned.forget": "Bu bilgiyi silin",
  "learned.forget.confirm": "Silmeyi onaylayın",
  "learned.reconfirm.footer": "Bu bilgi bir yıldan eski; ziyaret hazırlığında yeniden sorulur.",
  "learned.unsaved": "Bu değişiklik kaydınıza ulaşmadı.",
  // INT-260 — Görünüm: yazı boyutu, tema, ekran hareketi ve ziyaretin nasıl
  // başlayacağı. Ayarlar yalnızca bu cihazda tutulur; sunucuya gitmez.
  "appearance.title": "Görünüm",
  "appearance.preview": "Önizleme",
  "appearance.textSize": "Yazı boyutu",
  "appearance.textSize.phone": "Telefon ayarını kullanın",
  "appearance.size.s": "Küçük",
  "appearance.size.m": "Orta",
  "appearance.size.l": "Büyük",
  "appearance.size.xl": "Daha büyük",
  "appearance.size.xxl": "En büyük",
  "appearance.overrideNote": "Seçtiğiniz boyut telefon ayarınızın yerine kullanılır.",
  "appearance.theme": "Tema",
  "appearance.theme.system": "Sistem",
  "appearance.theme.light": "Açık",
  "appearance.theme.dark": "Koyu",
  "appearance.motion": "Ekran hareketini azaltın",
  "appearance.motionNote": "Telefonunuzda hareket azaltma açıksa bu ayar da açık kalır.",
  "appearance.start": "Ziyarete başlarken",
  "appearance.start.voice": "Konuşarak",
  "appearance.start.typed": "Yazarak",
  "appearance.deviceOnly": "Bu ayarlar yalnızca bu telefonda saklanır.",
  // INT-140 — Verileriniz: kaydınızın kopyası ve silinmesi. Buradaki her
  // satır bir denetimi anlatır; bilgilendirme metinleri docs/legal/ dışından
  // gelmez, bu yüzden hiçbiri burada yazılı değildir (invariant 18).
  "me.data": "Verileriniz",
  "data.entry.sub": "Kaydınızın kopyasını ya da silinmesini isteyebilirsiniz.",
  "data.guide.kicker": "Kontrol sizde",
  "data.guide.title": "Kaydınız sizindir",
  "data.guide.body":
    "Kaydınızın bir kopyasını isteyebilirsiniz. Kaydınızın silinmesini de isteyebilirsiniz.",
  "data.export": "Kaydınızın kopyasını isteyin",
  "data.export.notYet":
    "Kopyanız şimdilik uygulamadan indirilemiyor. İsteğiniz aşağıdaki listeye eklenir.",
  "data.due": "Yanıt için son gün",
  "data.delete": "Kaydınızın silinmesini isteyin",
  "data.delete.confirm": "Silme isteğini onaylayın",
  "data.delete.withdraw": "Silme isteğini geri çekin",
  "data.delete.graceEnds": "Silme günü",
  "data.delete.sharesCancelled": "Açık paylaşımlar kapatıldı.",
  "data.requests": "İstekleriniz",
  "data.kind.export": "Kopya isteği",
  "data.kind.delete": "Silme isteği",
  "data.kind.rectify": "Düzeltme isteği",
  "data.status.received": "Alındı",
  "data.status.scheduled": "Planlandı",
  "data.status.completed": "Tamamlandı",
  "data.status.cancelled": "Geri çekildi",
  "data.status.overdue": "Süresi geçti",
  "data.empty": "Henüz bir isteğiniz yok.",
  "data.unsent": "Bu istek gönderilemedi.",
  "data.deviceOnly": "Görünüm ayarlarınız ve sağlık okumalarınız yalnızca bu telefonda kalır.",
  "me.signOut": "Çıkış yapın",
  "me.syntheticBadge": "Sentetik deneme hesabı",

  "intake.q.complaint": "Sizi bugün hekime getiren nedir?",
  "intake.q.complaint.hint": "Birden fazla seçebilirsiniz.",
  "intake.opt.pain": "Ağrı",
  "intake.opt.fever": "Ateş",
  "intake.opt.cough": "Öksürük",
  "intake.opt.dyspnoea": "Nefes darlığı",
  "intake.opt.fatigue": "Halsizlik",
  "intake.opt.stomach": "Mide şikâyeti",
  "intake.opt.headache": "Baş ağrısı",
  "intake.opt.other": "Diğer",
  "intake.q.duration": "Bu şikâyetiniz ne zamandır var?",
  "intake.opt.today": "Bugün başladı",
  "intake.opt.days": "Birkaç gündür",
  "intake.opt.week": "Bir haftadan uzun süredir",
  "intake.opt.month": "Bir aydan uzun süredir",
  "intake.q.character": "Ağrınızı nasıl tarif edersiniz?",
  "intake.hpi.character": "Ağrının niteliği",
  "intake.opt.pressure": "Baskı, sıkışma gibi",
  "intake.opt.stabbing": "Batma, saplanma gibi",
  "intake.opt.burning": "Yanma gibi",
  "intake.opt.dull": "Künt, belli belirsiz",
  "intake.q.trigger": "Şikâyetiniz ne zaman artıyor?",
  "intake.hpi.trigger": "Artıran durum",
  "intake.opt.exertion": "Hareket ya da eforla",
  "intake.opt.rest": "Dinlenirken de oluyor",
  "intake.opt.meals": "Yemekle ilişkili",
  "intake.opt.noPattern": "Belirli bir düzeni yok",
  "intake.q.associated": "Şikâyetinize eşlik eden başka bir şey var mı?",
  "intake.hpi.associated": "Eşlik edenler",
  "intake.opt.sweating": "Terleme",
  "intake.opt.nausea": "Bulantı",
  "intake.opt.palpitations": "Çarpıntı",
  "intake.opt.none": "Yok",
  "intake.q.onset": "Nasıl başladı?",
  "intake.hpi.onset": "Başlangıç",
  "intake.opt.sudden": "Aniden başladı",
  "intake.opt.gradual": "Yavaş yavaş gelişti",
  "intake.q.severity": "Şiddetini nasıl tarif edersiniz?",
  "intake.hpi.severity": "Şiddet",
  "intake.opt.mild": "Hafif",
  "intake.opt.moderate": "Orta",
  "intake.opt.severe": "Şiddetli",
  "intake.q.side": "Hangi tarafta?",
  "intake.hpi.side": "Taraf",
  "intake.opt.right": "Sağ",
  "intake.opt.left": "Sol",
  "intake.opt.both": "İki taraf",
  "intake.opt.lightSensitivity": "Işığa hassasiyet",
  "intake.opt.soundSensitivity": "Sese hassasiyet",
  "intake.opt.visionChange": "Görmede değişiklik",
  "intake.opt.numbness": "Uyuşma, karıncalanma",
  "intake.opt.soreThroat": "Boğaz ağrısı",
  "intake.opt.congestion": "Burun tıkanıklığı",
  "intake.opt.hearingLoss": "İşitmede azalma",
  "intake.opt.tinnitus": "Çınlama",
  // Kardiyoloji / İç Hastalıkları
  "intake.q.radiation": "Ağrı ya da baskı hissi başka bir yere yayılıyor mu?",
  "intake.hpi.radiation": "Yayılım",
  "intake.opt.radArm": "Kola yayılıyor",
  "intake.opt.radJawNeck": "Çeneye ya da boyna yayılıyor",
  "intake.opt.radBack": "Sırta yayılıyor",
  "intake.opt.radNone": "Yayılmıyor",
  "intake.opt.dizziness": "Baş dönmesi",
  "intake.opt.ankleSwelling": "Ayak bileklerinde şişlik",
  // Nöroloji
  "intake.opt.throbbing": "Zonklama şeklinde",
  "intake.opt.electric": "Elektrik çarpması gibi",
  "intake.opt.withMovement": "Hareketle artıyor",
  "intake.opt.withLightNoise": "Işık ya da gürültüyle artıyor",
  "intake.opt.withSleepless": "Uykusuz kalınca artıyor",
  "intake.q.course": "Şikâyetiniz zaman içinde nasıl değişiyor?",
  "intake.hpi.course": "Seyir",
  "intake.opt.inAttacks": "Ataklar hâlinde geliyor",
  "intake.opt.constant": "Sürekli var",
  "intake.opt.varies": "Gün içinde artıp azalıyor",
  "intake.opt.balance": "Dengede güçlük",
  // Kulak Burun Boğaz
  "intake.opt.withSwallow": "Yutkununca artıyor",
  "intake.opt.withColdAir": "Soğuk havada artıyor",
  "intake.opt.atNight": "Gece artıyor",
  "intake.opt.hoarseness": "Ses kısıklığı",
  // Ortopedi
  "intake.q.mechanism": "Şikâyetiniz nasıl ortaya çıktı?",
  "intake.hpi.mechanism": "Ortaya çıkışı",
  "intake.opt.afterFall": "Bir düşme ya da darbe sonrası",
  "intake.opt.afterStrain": "Ağır kaldırma ya da zorlanma sonrası",
  "intake.opt.noEvent": "Kendiliğinden, yavaş yavaş",
  "intake.q.region": "Şikâyetiniz en çok hangi bölgede?",
  "intake.hpi.region": "Bölge",
  "intake.opt.knee": "Diz",
  "intake.opt.hip": "Kalça",
  "intake.opt.shoulder": "Omuz",
  "intake.opt.lowBack": "Bel",
  "intake.opt.neckRegion": "Boyun",
  "intake.opt.handWrist": "El ya da el bileği",
  "intake.opt.footAnkle": "Ayak ya da ayak bileği",
  "intake.opt.restEases": "Dinlenince azalıyor",
  "intake.opt.morningStiff": "Sabahları tutukluk oluyor",
  "intake.opt.nightPain": "Gece uykudan uyandırıyor",
  "intake.opt.swelling": "Şişlik",
  "intake.opt.redness": "Kızarıklık",
  "intake.opt.limitedMotion": "Hareketlerde kısıtlılık",
  // Dermatoloji
  "intake.q.skinWhere": "Cilt şikâyetiniz vücudunuzun neresinde?",
  "intake.q.skinLook": "Şikâyetli bölgede neler oluyor?",
  "intake.hpi.appearance": "Görünüm ve his",
  "intake.opt.face": "Yüz",
  "intake.opt.scalp": "Saçlı deri",
  "intake.opt.trunk": "Gövde",
  "intake.opt.arms": "Kollar",
  "intake.opt.legs": "Bacaklar",
  "intake.opt.handsFeet": "Eller ya da ayaklar",
  "intake.opt.widespread": "Yaygın, birden çok bölgede",
  "intake.opt.itchy": "Kaşıntı",
  "intake.opt.painful": "Ağrı ya da hassasiyet",
  "intake.opt.flaking": "Pullanma",
  "intake.opt.blisters": "İçi su dolu kabarcıklar",
  "intake.opt.raised": "Kabarıklık",
  "intake.opt.withSun": "Güneşe çıkınca artıyor",
  "intake.opt.withSweat": "Terleyince artıyor",
  "intake.opt.afterProduct": "Yeni bir ürün ya da ilaç sonrası başladı",
  "intake.opt.spreading": "Yayılıyor",
  "intake.opt.same": "Aynı kalıyor",
  "intake.opt.improving": "Azalıyor",
  "intake.opt.comesGoes": "Gelip gidiyor",
  "intake.opt.jointPain": "Eklem ağrısı",
  "intake.opt.nailChange": "Tırnaklarda değişiklik",
  // Göğüs Hastalıkları
  "intake.q.breathCharacter": "Öksürük ya da nefes şikâyetinizi nasıl tarif edersiniz?",
  "intake.hpi.quality": "Nitelik",
  "intake.opt.dryCough": "Kuru öksürük",
  "intake.opt.phlegmCough": "Balgamlı öksürük",
  "intake.opt.wheeze": "Hırıltı ya da ıslık sesi",
  "intake.opt.painfulBreath": "Nefes alırken batma",
  "intake.opt.whenLying": "Yatar pozisyonda artıyor",
  "intake.q.timeOfDay": "Şikâyetiniz günün hangi vaktinde daha belirgin?",
  "intake.hpi.timing": "Zamanlama",
  "intake.opt.inMorning": "Sabahları daha belirgin",
  "intake.opt.allDay": "Gün boyu benzer",
  "intake.opt.nightSweats": "Gece terlemesi",
  "intake.opt.phlegmColor": "Balgam renginde değişiklik",
  "intake.opt.weightLoss": "Son dönemde istemeden kilo verme",
  // Kadın Hastalıkları ve Doğum
  "intake.q.cycleRelation": "Şikâyetinizin âdet döneminizle ilişkisi var mı?",
  "intake.hpi.cycle": "Âdet ile ilişkisi",
  "intake.opt.duringPeriod": "Âdet sırasında artıyor",
  "intake.opt.beforePeriod": "Âdetten önceki günlerde artıyor",
  "intake.opt.noCycleRelation": "Âdetle ilişkisi yok",
  "intake.opt.noPeriod": "Âdet görmüyorum",
  "intake.opt.cycleChange": "Âdet düzeninde değişiklik",
  "intake.opt.bleedingChange": "Âdet dışı kanama",
  "intake.opt.dischargeChange": "Akıntıda değişiklik",
  "intake.opt.urineBurning": "İdrar yaparken yanma",
  // Üroloji
  "intake.q.urination": "İdrar yaparken bir değişiklik fark ediyor musunuz?",
  "intake.hpi.urination": "İdrar şikâyetleri",
  "intake.opt.frequentUrination": "Sık idrara çıkma",
  "intake.opt.nightUrination": "Gece idrara kalkma",
  "intake.opt.weakStream": "İdrarı başlatmada güçlük ya da zayıf akış",
  "intake.opt.leakage": "İdrar kaçırma",
  "intake.opt.flankPain": "Yan tarafta ya da belde ağrı",
  "intake.opt.urineColor": "İdrar renginde değişiklik",
  // Göz Hastalıkları
  "intake.q.eyeFeel": "Gözünüzde nasıl bir rahatsızlık var?",
  "intake.opt.gritty": "Batma, kum kaçmış hissi",
  "intake.opt.burningFeel": "Yanma hissi",
  "intake.opt.watering": "Sulanma",
  "intake.q.vision": "Görmenizde bir değişiklik oldu mu?",
  "intake.hpi.vision": "Görme",
  "intake.opt.blurry": "Bulanık görme",
  "intake.opt.doubleVision": "Çift görme",
  "intake.opt.floaters": "Uçuşan nokta ya da çizgiler",
  "intake.opt.halos": "Işıkların çevresinde halkalar",
  "intake.opt.eyeDischarge": "Çapaklanma",
  // Gastroenteroloji
  "intake.q.abdomenWhere": "Şikâyetiniz karnınızın neresinde?",
  "intake.opt.upperAbdomen": "Karnın üst kısmında",
  "intake.opt.lowerAbdomen": "Karnın alt kısmında",
  "intake.opt.abdomenRight": "Sağ tarafta",
  "intake.opt.abdomenLeft": "Sol tarafta",
  "intake.opt.aroundNavel": "Göbek çevresinde",
  "intake.opt.wholeAbdomen": "Tüm karında",
  "intake.opt.cramping": "Kramp şeklinde",
  "intake.opt.bloatingFeel": "Şişkinlik, dolgunluk hissi",
  "intake.q.mealRelation": "Şikâyetinizin yemekle ilişkisi var mı?",
  "intake.hpi.mealRelation": "Yemekle ilişkisi",
  "intake.opt.afterMeal": "Yemekten sonra artıyor",
  "intake.opt.whenHungry": "Aç kalınca artıyor",
  "intake.opt.easedByMeal": "Yemek yiyince azalıyor",
  "intake.q.bowel": "Tuvalet alışkanlığınızda değişiklik var mı?",
  "intake.hpi.bowel": "Bağırsak alışkanlığı",
  "intake.opt.constipation": "Kabızlık",
  "intake.opt.diarrhea": "İshal",
  "intake.opt.alternatingBowel": "Bazen kabızlık bazen ishal",
  "intake.opt.vomiting": "Kusma",
  "intake.opt.heartburn": "Göğse doğru yanma ya da ekşime",
  "intake.opt.appetiteLoss": "İştahta azalma",
  "intake.q.extra": "Eklemek istediğiniz bir şey var mı?",
  "intake.q.extra.hint": "İsterseniz boş bırakabilirsiniz.",
  // INT-239 — answer-gated follow-ups. Each asks for a further detail of
  // something the patient already named; none names a condition, a treatment
  // or a danger, and none asks for a number.
  "intake.q.radiationSide": "Yayılma hangi tarafta?",
  "intake.hpi.radiationSide": "Yayılım tarafı",
  "intake.q.breathTiming": "Nefes darlığınız ne zaman oluyor?",
  "intake.hpi.breathTiming": "Nefes darlığının zamanı",
  "intake.q.breathLying": "Uzanınca rahatlamak için ne yapıyorsunuz?",
  "intake.hpi.breathLying": "Uzanınca yapılan",
  "intake.opt.raisePillow": "Yastığı yükseltiyorum",
  "intake.opt.sitUp": "Oturuyorum",
  "intake.opt.nothingSpecial": "Özel bir şey yapmıyorum",
  "intake.opt.notSure": "Emin değilim",
  "intake.q.feverPattern": "Ateşiniz en çok ne zaman yükseliyor?",
  "intake.hpi.feverPattern": "Ateşin zamanı",
  "intake.q.palpitation": "Çarpıntınızı nasıl tarif edersiniz?",
  "intake.hpi.palpitation": "Çarpıntının niteliği",
  "intake.opt.fastRegular": "Hızlı ve düzenli",
  "intake.opt.irregularBeat": "Düzensiz",
  "intake.opt.skippedBeats": "Arada atlıyor gibi",
  "intake.q.headWhere": "Baş ağrınız başınızın neresinde?",
  "intake.opt.oneSide": "Tek tarafta",
  "intake.opt.bothSides": "İki tarafta",
  "intake.opt.foreheadEye": "Alın ve göz çevresinde",
  "intake.opt.fromNeck": "Enseden başlıyor",
  "intake.q.headSameSide": "Ağrı her seferinde aynı tarafta mı oluyor?",
  "intake.hpi.headSameSide": "Taraf tutarlılığı",
  "intake.opt.alwaysSameSide": "Hep aynı tarafta",
  "intake.opt.sideChanges": "Taraf değişiyor",
  "intake.q.numbWhere": "Uyuşma en çok nerede oluyor?",
  "intake.hpi.numbWhere": "Uyuşmanın yeri",
  "intake.opt.severalPlaces": "Birden çok yerde",
  "intake.q.painWhere": "Ağrınız en çok nerede?",
  "intake.opt.inEar": "Kulakta",
  "intake.opt.inThroat": "Boğazda",
  "intake.opt.faceForehead": "Yüzde ve alında",
  "intake.opt.inJaw": "Çenede",
  "intake.q.swallow": "Yutkunurken ne oluyor?",
  "intake.hpi.swallow": "Yutkunma",
  "intake.opt.painIncreases": "Ağrı artıyor",
  "intake.opt.stuckFeeling": "Takılma hissi oluyor",
  "intake.opt.voiceChange": "Sesim değişiyor",
  "intake.opt.noChange": "Bir değişiklik olmuyor",
  "intake.q.hearSide": "İşitmedeki azalma hangi kulakta?",
  "intake.hpi.hearSide": "İşitme tarafı",
  "intake.q.fallHow": "Nasıl düştünüz ya da darbe aldınız?",
  "intake.hpi.fallHow": "Düşme biçimi",
  "intake.opt.slipped": "Kayarak ya da takılarak",
  "intake.opt.onStairs": "Merdivende",
  "intake.opt.fromHeight": "Yüksek bir yerden",
  "intake.opt.duringSport": "Spor yaparken",
  "intake.q.spineSpread": "Ağrı kolunuza ya da bacağınıza yayılıyor mu?",
  "intake.hpi.spineSpread": "Kol ya da bacağa yayılım",
  "intake.opt.radLeg": "Bacağa yayılıyor",
  "intake.q.spreadFeel": "Yayıldığı yerde başka bir his var mı?",
  "intake.hpi.spreadFeel": "Yayılım hissi",
  "intake.opt.tingling": "Karıncalanma",
  "intake.opt.numbFeeling": "Uyuşma",
  "intake.opt.bothOfThem": "İkisi de",
  "intake.q.itchWhen": "Kaşıntı ne zaman artıyor?",
  "intake.hpi.itchWhen": "Kaşıntının zamanı",
  "intake.opt.inHeat": "Sıcakta artıyor",
  "intake.q.itchSleep": "Kaşıntı uykunuzu bölüyor mu?",
  "intake.hpi.itchSleep": "Uykuya etkisi",
  "intake.opt.yes": "Evet",
  "intake.opt.sometimes": "Bazen",
  "intake.opt.no": "Hayır",
  "intake.q.feverSkinOrder": "Ateş ile cilt şikâyetinizden hangisi önce başladı?",
  "intake.hpi.feverSkinOrder": "Ateş ile sıra",
  "intake.opt.feverFirst": "Önce ateş",
  "intake.opt.skinFirst": "Önce cilt şikâyeti",
  "intake.opt.sameTime": "Aynı zamanda",
  "intake.opt.dontRemember": "Hatırlamıyorum",
  "intake.opt.inLowerBack": "Belde",
  "intake.opt.inGroin": "Kasıkta",
  "intake.q.flankSide": "Yan ya da bel ağrısı hangi tarafta?",
  "intake.hpi.flankSide": "Yan ağrısının tarafı",
  "intake.q.eyePainMove": "Ağrı gözünüzü hareket ettirince değişiyor mu?",
  "intake.hpi.eyePainMove": "Hareketle değişim",
  "intake.q.eyeHeadache": "Baş ağrınız ile göz şikâyetiniz birlikte mi oluyor?",
  "intake.hpi.eyeHeadache": "Baş ağrısıyla ilişkisi",
  "intake.opt.together": "Birlikte oluyor",
  "intake.opt.headacheFirst": "Önce baş ağrısı",
  "intake.opt.eyeFirst": "Önce göz şikâyeti",
  "intake.opt.separately": "Ayrı ayrı oluyor",
  "intake.q.bowelRelief": "Tuvalete çıkınca şikâyetiniz değişiyor mu?",
  "intake.hpi.bowelRelief": "Tuvalet sonrası",
  "intake.opt.itEases": "Azalıyor",
  "intake.opt.itIncreases": "Artıyor",
  // The flow length follows the answers, so the progress row counts what is
  // answered and says plainly that more questions may follow (INT-239).
  "intake.progress.answered": "soru yanıtlandı",
  "intake.progress.grows": "Yanıtlarınıza göre birkaç soru daha gelebilir.",
  "voice.speakToAdd": "Konuşarak ekleyin",
  "voice.listening": "Dinliyor… durdurmak için dokunun",
  "voice.processing": "Yazıya dökülüyor…",
  "voice.unreachable": "Ses sunucusuna şu an ulaşılamıyor.",
  "voice.permission": "Mikrofon izni gerekli.",

  // INT-103 — canlı sesli görüşme istemcisi (LiveKit). Mikrofon izni metni
  // mağaza kurallarına göre: önce nedenini söyleyen bir satır, sonra sistem
  // izni. Kayıt saklanmadığı için hiçbir metin "kayıt" demez (invariant 3).
  //
  // INT-253: `voice.mic.*` ve `voice.session.*` INT-103'ün kabulüne bağlıdır
  // (apps/mobile/e2e/voice.spec.ts) ama hiçbir ekran bunları göstermiyor —
  // oturum makinesi connecting/reconnecting/backgrounded/interrupted
  // aşamalarına gerçekten giriyor, hasta hiçbirini görmüyor. Kayıt
  // tests/release/test_i18n_complete.py · UNWIRED_ACCEPTANCE_KEYS.
  "voice.mic.why":
    "Sesli görüşme için mikrofon izni gerekir. Sesiniz yalnızca görüşme sırasında işlenir; kaydı saklanmaz.",
  "voice.mic.cta": "Mikrofona izin verin",
  "voice.mic.settingsHint": "İzni daha sonra telefonunuzun ayarlarından da verebilirsiniz.",
  "voice.transport.ok": "Sesli görüşme bu cihazda kullanılabilir.",
  "voice.transport.needsDevBuild":
    "Sesli görüşme bu uygulama sürümünde açılamıyor. Tam sürümü kullanın ya da yazarak devam edin.",
  "voice.transport.unsupported":
    "Sesli görüşme bu cihazda desteklenmiyor. Yazarak devam edebilirsiniz.",
  "voice.transport.micDenied":
    "Mikrofon izni verilmedi. İzni telefonunuzun ayarlarından verebilirsiniz.",
  "voice.session.connecting": "Bağlanılıyor…",
  "voice.session.reconnecting": "Bağlantı yeniden kuruluyor…",
  "voice.session.paused":
    "Görüşme duraklatıldı. Uygulamaya döndüğünüzde kaldığınız yerden devam edersiniz.",
  "voice.session.interrupted":
    "Görüşme duraklatıldı. Telefon görüşmeniz bittiğinde devam edebilirsiniz.",
  "voice.session.weakLink": "Bağlantınız zayıf. Sesiniz kesilirse yazarak devam edebilirsiniz.",
  "voice.session.ended": "Sesli görüşme sonlandı. Yazarak devam edebilirsiniz.",

  "voiceFirst.checking": "Ses özelliği hazırlanıyor…",
  "voiceFirst.listening": "Sizi dinliyoruz.",
  "voiceFirst.stop": "Bitirdim",
  "voiceFirst.preparing": "Yanıt önerileri hazırlanıyor…",
  "voiceFirst.typeInstead": "Yazarak devam edin",
  "voiceFirst.saidLabel": "Söylediğiniz:",
  "voiceFirst.suggested": "Önerilen yanıt",
  "voiceFirst.failed": "Ses özelliği şu an kullanılamadı. Yazarak devam edebilirsiniz.",
  "dialogue.kicker": "Karşılıklı konuşma",
  "dialogue.entryTitle": "Sizinle konuşarak ilerleyelim",
  "dialogue.entryBody":
    "Soruları sesli soracağız, siz de konuşarak yanıtlayın. İstediğiniz an yazarak da devam edebilirsiniz.",
  "dialogue.preparing": "Soru hazırlanıyor…",
  "dialogue.speakingHint": "Araya girmek için dokunun",
  "dialogue.listeningHint": "Bitirince dokunun",
  "dialogue.optionsIntro": "Seçenekler:",
  "dialogue.and": "ve",
  "dialogue.or": "veya",
  "dialogue.confirmIntro": "Sizi şöyle anladık:",
  "dialogue.confirmAsk": "Doğruysa onaylayın; isterseniz düzeltmeyi söyleyin.",
  "dialogue.confirmTextGeneric": "Söyledikleriniz ekrana yazıldı. Kontrol edip onaylayın.",
  "dialogue.confirm": "Onaylayın",
  "dialogue.speakCorrection": "Düzeltmeyi söyleyin",
  "dialogue.typeThisStep": "Yazarak yanıtlayın",
  "dialogue.transcribing": "Yazıya dökülüyor…",
  // INT-293. Said once, in front of a question the agent is asking a second
  // time because the patient's words mapped to no answer — here or at the
  // extract lane. It names what happened without blaming the patient and
  // without claiming the words were wrong; the question itself follows
  // verbatim in its own bubble (invariant 10). The warmth is the -alım mood,
  // not the pronoun: the register stays `siz` throughout.
  "dialogue.notUnderstood": "Söylediğinizi tam anlayamadım. Aynı soruyu bir kez daha soralım.",
  // INT-261. Shown once when the agent's voice fails mid-conversation. It
  // names what stopped (the reading aloud), leaves no doubt that the rest
  // continues, and tells the patient what to do — instructional prose, so
  // `-iniz`. Never "hata", never an apology for something the patient did.
  "dialogue.voiceMuted":
    "Sesli okuma şu an çalışmıyor. Soruları ekrandan okuyabilir, konuşarak ya da yazarak yanıtlayabilirsiniz.",
  "dialogue.noteForming": "Not oluşuyor",
  "dialogue.sectionsLabel": "bölüm",
  "dialogue.sectionsTitle": "Not bölümleri",
  "dialogue.sectionEmpty": "Henüz yanıtlanmadı",
  "dialogue.sheetHint": "Öneriler siz onayladıktan sonra nota eklenir.",
  "dialogue.close": "Kapatın",
  "dialogue.send": "Gönderin",
  "intake.next": "Devam edin",
  "intake.finish": "Özeti görün",

  // INT-321 — the mode is asked ONCE, up front (02 §2), not as a switch on
  // every question. Two calm doors; warmth is in the verb mood (-elim/-alım),
  // never in the pronoun. The old per-question row ("Hastanedeyim" switch +
  // "Sıranız geldi" chip) is gone; the checkpoint survives as "Bitirdim".
  "intake.mode.q": "Nasıl ilerleyelim?",
  "intake.mode.hospital": "Hastanedeyim",
  "intake.mode.hospitalSub": "Ayrıntılı soralım. Sıra size gelirse dilediğinizde bitirebilirsiniz.",
  "intake.mode.brief": "Kısa tutalım",
  "intake.mode.briefSub": "Yalnızca en gerekli birkaç soru.",
  // The clinic-interruptible checkpoint (02 §34): first-person, plain.
  "intake.finishNow": "Bitirdim",
  // Environment self-check (02 §33) — asked only in the ayrıntılı flow.
  "intake.privacy.q": "Yanınızda başkası var mı?",
  "intake.privacy.hint": "Bazı sorular özeldir. Ortam uygun değilse onları sonraya bırakırız.",
  "intake.privacy.alone": "Hayır, yalnızım",
  "intake.privacy.notAlone": "Evet, yanımda biri var",
  "intake.privacy.deferredInfo":
    "Özel sorular şimdi sorulmayacak. Uygun bir ortamda devam edebilirsiniz.",

  "review.title": "Hekiminize gidecek not",
  "review.intro": "Bölümleri kontrol edin. Neyin paylaşılacağına siz karar verirsiniz.",
  "review.section.cc": "Başvuru nedeni",
  "review.section.hpi": "Şikâyet öyküsü",
  "review.hpi.duration": "Süre",
  "review.hpi.patientNote": "Hasta notu",
  // [REVIEW] provenance line on the clinician-bound note, 06 §7 family
  "review.provenance": "Bu not hasta beyanına dayanır; tanı içermez.",
  "review.section.medications": "İlaçlar — hasta beyanı",
  "review.medsNote": "Profilinizdeki kayıtlı ilaçlar",
  "review.edit": "Düzenleyin",
  "review.shared": "Paylaşılıyor",
  "review.notShared": "Paylaşılmıyor",
  "review.send": "Hekiminize gönderin",
  "review.sentInfo": "Notunuz gönderildi. Hekiminiz görüntülediğinde durumu burada görürsünüz.",
  "review.empty": "Henüz yanıt yok. Önce birkaç soruyu yanıtlayın.",
  // INT-236 — hekime görünen erteleme işareti (02 §33: birebir
  // "eksik: ortam uygun değildi"), koşul işareti ve kesme noktası özeti.
  "review.section.deferred": "Ertelenen bölümler",
  "note.deferred.wellbeing": "İyilik hâli taraması",
  "note.deferred.marker": "eksik: ortam uygun değildi",
  "review.hpi.staleCondition": "koşul değişti",
  "review.eksik.title": "Eksik kalanlar",
  "review.eksik.intro": "Bu sorular henüz yanıtlanmadı:",
  "review.resume": "Kaldığınız yerden devam edin",
  "review.checkpointInfo":
    "Notunuz bu haliyle hazır; dilerseniz sonra kaldığınız yerden devam edebilirsiniz.",

  "visit.prepare": "Muayeneye hazırlanın",
  "visit.reviewNote": "Notu kontrol edin",

  "consent.core": "Temel hizmet",
  "consent.voice": "Sesli görüşme",
  "consent.wellbeing": "İyilik hâli taraması",
  "consent.documents": "Belge yükleme",
  "consent.health": "Sağlık verisi okuma",
  "consent.health.hint":
    "Adım, nabız ve uyku verileriniz yalnızca bu telefonda okunur; hiçbir yere gönderilmez. Bir veri, notunuza ancak siz eklerseniz girer.",
  "consent.on": "Açık",
  "consent.off": "Kapalı",

  // INT-132 — İzinleriniz. Bu anahtarlar yalnızca arayüz metnidir; onay
  // metinlerinin kendisi docs/legal'den, sürüm ve damgasıyla gelir
  // (invariant 18) ve hiçbir zaman bu kataloğa yazılmaz.
  "consent.entry.sub": "Hangi izni ne için verdiğinizi görün ve yönetin.",
  "consent.firstRun.body":
    "Önvizit'te her izin ayrıdır. İzin gerektiren hiçbir seçenek önceden açık gelmez. Şimdi karar vermek zorunda değilsiniz; her izni sırası geldiğinde ya da buradan açabilirsiniz.",
  "consent.firstRun.continue": "Devam edin",
  "consent.group.core": "Hizmet",
  "consent.group.voice": "Sesli görüşme",
  "consent.group.voice.hint":
    "Ses analizi seçenekleri yalnızca sesli görüşmeyle birlikte çalışır. Yazı analizi ses kaydına değil, yazıya bakar; ayrı bir izindir.",
  "consent.group.purposes": "Diğer amaçlar",
  "consent.group.learning": "Öğrenme",
  "consent.group.learning.hint":
    "Bu iki seçenek hizmetin çalışması içindir ve açık gelir; dilediğiniz an kapatabilirsiniz.",
  "consent.lane.affect": "Ses tonundan duygu ipuçları",
  "consent.lane.linguistic": "Yazıdan dil ipuçları",
  "consent.learning.personal": "Sizin için öğrenme",
  "consent.learning.service": "Hizmeti iyileştirme",
  "consent.satisfaction": "Memnuniyet soruları",
  "consent.research": "Araştırma",
  "consent.who.core":
    "Notunuzu siz görürsünüz. Hekiminiz, yalnızca siz paylaşırsanız görür. Acil bir işarette klinik personeli, paylaşım beklemeden kısa bir uyarı görür.",
  "consent.who.voice":
    "Sesiniz yalnızca görüşme sırasında işlenir; kayıt saklanmaz. Veriler Türkiye'deki sunucularda kalır.",
  "consent.who.laneAffect":
    "Ses tonunuzdan çıkan ipuçlarını yalnızca hekiminiz görür; size bir etiket konmaz.",
  "consent.who.laneLinguistic":
    "Yazıya dökülen metinden çıkan ipuçlarını yalnızca hekiminiz görür.",
  "consent.who.wellbeing":
    "Yanıtlarınızı yalnızca siz görürsünüz; hekiminizle paylaşım her seferinde ayrıca sorulur.",
  "consent.who.documents":
    "Yüklediğiniz belgeler sizin dosyanızda kalır; hekiminizle paylaşım sizin onayınızla olur.",
  "consent.who.learningPersonal":
    "Öğrenilen her bilgi 'Hakkımda öğrendikleri' listesinde görünür ve dilediğinizde silinir.",
  "consent.who.learningService":
    "Kimliğinizden ayrılmış toplu veriler kullanılır; size ait tek bir kayıt paylaşılmaz.",
  "consent.who.satisfaction":
    "Yanıtlarınız hizmeti değerlendirmek için kullanılır; hekiminize gitmez.",
  "consent.who.research": "Verileriniz araştırmada yalnızca siz onay verirseniz kullanılır.",
  "consent.basis.explicit":
    "Açık rızanıza bağlıdır. İstediğiniz an geri çekebilirsiniz; geri çekmek hemen geçerli olur.",
  "consent.basis.learningPersonal":
    "Ayarladığınız hizmetin çalışması için kullanılır; bu yüzden açık gelir. Kapatırsanız kişisel öğrenme durur.",
  "consent.basis.learningService":
    "Kimliğinizden ayrılmış toplu verilerle hizmet iyileştirilir; bu yüzden açık gelir. Kapatmak hiçbir özelliği kısıtlamaz.",
  "consent.state.pending": "Metin hazırlanıyor",
  "consent.state.stale": "Yeniden onay gerekli",
  "consent.pending.body":
    "Bu iznin metni hazırlanıyor. Metin yayımlanmadan izin açılamaz; hazır olduğunda burada görünür.",
  "consent.stale.body":
    "Bu iznin metni güncellendi. Devam etmesini isterseniz yeni metni okuyup yeniden onaylayın; onaylayana kadar izin kullanılmaz.",
  "consent.detail.who": "Kim neyi görür",
  "consent.detail.version": "Metin sürümü",
  "consent.detail.binding": "Metin damgası",
  "consent.detail.grant": "Okudum, kabul ediyorum",
  "consent.detail.withdraw": "İzni geri çekin",
  "consent.detail.withdrawNote": "Geri çekmek hemen geçerli olur.",
  "consent.detail.needsVoice": "Bu seçenek yalnızca sesli görüşme izni açıkken açılabilir.",
  "consent.queue.note":
    "Değişiklikleriniz bu cihazda uygulandı; sunucuya bağlantı kurulunca iletilecek.",

  "me.health": "Sağlık verileri",
  "health.guide.devBuild.kicker": "Deneme sürümü",
  "health.guide.devBuild.title": "Bu sürümde kullanılamıyor",
  "health.guide.devBuild.body":
    "Telefonunuzdaki sağlık verilerini okumak için uygulamanın tam sürümü gerekir. Bu deneme sürümü sağlık verilerine erişemez; verileriniz olduğu yerde durur.",
  "health.unsupported": "Bu cihazda sağlık verisi okunamıyor.",
  "health.permissionDenied":
    "Sağlık verilerine erişim izni verilmemiş. İzni telefonunuzun ayarlarından verebilirsiniz.",
  "health.loading": "Sağlık verileri okunuyor…",
  "health.readFailed": "Veriler şu an okunamadı. Daha sonra yeniden deneyin.",
  "health.noData": "Son 7 günde okunacak veri bulunamadı.",
  "health.steps.label": "Adımlar (son 7 gün)",
  "health.rhr.label": "Dinlenme nabzı",
  "health.sleep.label": "Uyku (gecelik ortalama)",
  "health.unit.steps": "adım",
  "health.unit.bpm": "atım/dk",
  "health.unit.hours": "saat",
  "health.attach.cta": "Vizite ekleyin",
  "health.attach.confirm": "Bu özet, vizit notunuzun taslağına eklensin mi?",
  "health.attach.yes": "Evet, ekleyin",
  "health.attach.no": "Vazgeçin",
  "health.attach.done": "Özet, vizit notunuzun taslağına eklendi.",
  "health.attach.noVisit": "Eklemek için önce bir vizit oluşturun.",
  "review.section.health": "Cihaz sağlık verisi",
  // [REVIEW] fixed provenance line on the attached device-health block
  "review.healthProvenance": "Cihaz sağlık verisi — hasta onayıyla eklendi.",
  // ── INT-144 · screen-reader strings ──────────────────────────────────
  // Never rendered visually: these are what VoiceOver and TalkBack speak.
  // Same rules as everything else — B1, `siz`, no clinical interpretation
  // (a name or a hint may only re-say what is already on the screen), and
  // no ALL-CAPS. The `…Hint` keys describe what activation does; they never
  // replace a control's visible words (SC 2.5.3).
  "a11y.error": "Hata",
  "a11y.openHint": "Ayrıntıları açmak için iki kez dokunun.",
  "a11y.backHint": "Önceki ekrana dönmek için iki kez dokunun.",
  "a11y.closeHint": "Kapatmak için iki kez dokunun.",
  "a11y.selectHint": "Seçmek için iki kez dokunun.",
  "a11y.visits.dayHint": "O günün vizitlerini görmek için iki kez dokunun.",
  "a11y.confirmHint": "Onaylamak için iki kez dokunun.",
  "a11y.shareHint": "Bu bölümün paylaşımını açıp kapatmak için iki kez dokunun.",
  "a11y.typedHint": "Konuşmak yerine yazarak devam etmek için iki kez dokunun.",
  "a11y.otp.digit": "Doğrulama kodu hanesi",
  "a11y.consent.rowHint": "İzin metnini ve ayrıntıları açmak için iki kez dokunun.",
  "a11y.consent.switchHint": "Bu izni açıp kapatmak için iki kez dokunun.",
  // INT-140 — ipuçları eylemin SONUCUNU söyler (iOS HIG): ekran okuyucu
  // kullanan hasta, dokunmadan önce ne olacağını bilir.
  "a11y.data.exportHint": "İki kez dokunmak kopya isteğinizi gönderir.",
  "a11y.data.deleteHint": "İki kez dokunmak silme isteğinizi başlatır.",
  "a11y.data.withdrawHint": "İki kez dokunmak silme isteğinizi geri çeker.",
  "a11y.learned.shareHint": "İki kez dokunmak bu bilginin paylaşımını değiştirir.",
  "a11y.learned.forgetHint": "İki kez dokunmak bu bilgiyi kaydınızdan siler.",
  "a11y.ladder.reached": "tamamlandı",
  "a11y.ladder.pending": "henüz tamamlanmadı",
  // The two voices of the conversation. The agent is named with the product
  // name, never a human first name (02 §5: no persona presented as a
  // person); "Siz" keeps the app-wide register.
  "a11y.speaker.agent": "Önvizit",
  "a11y.speaker.patient": "Siz",
  "a11y.dialogue.transcript": "Konuşma dökümü",
  "a11y.dialogue.speaking": "Önvizit konuşuyor",
  "a11y.dialogue.preparing": "Soru hazırlanıyor",
  "a11y.dialogue.transcribing": "Söyledikleriniz yazıya dökülüyor",
  "a11y.dialogue.settling": "Notunuz hazırlanıyor",
  "a11y.dialogue.bargeInHint": "Sözü kesip konuşmaya başlamak için iki kez dokunun.",
  "a11y.dialogue.stopHint": "Konuşmanızı bitirmek için iki kez dokunun.",
  "a11y.dialogue.composerHint": "Konuşmak yerine buraya yazabilirsiniz.",
  "a11y.dialogue.sectionsHint": "Nota işlenen bölümleri görmek için iki kez dokunun.",
  "a11y.dialogue.exitHint": "Konuşmadan çıkıp yazarak devam etmek için iki kez dokunun.",
  // ── INT-141 · Bildirimler ────────────────────────────────────────────
  // The patient's own opt-out and quiet window. Two rules the copy has to
  // carry honestly: a bildirim never says anything about health (the bodies
  // are constants in the server catalogue — nothing about the visit reaches
  // a lock screen), and there is NO default quiet window, because no file
  // names an hour and inventing one would choose it for everybody.
  "me.notifications": "Bildirimler",
  "notifications.title": "Bildirimler",
  "notifications.entry.sub": "Hatırlatmalar ve sessiz saatler",
  "notifications.guide.kicker": "Bildirimler",
  "notifications.guide.title": "Yalnızca hatırlatma",
  "notifications.guide.body":
    "Size yalnızca vizitinizden önce kısa bir hatırlatma göndeririz. Ne zaman sessiz kalacağımızı siz seçersiniz; istediğiniz zaman tamamen kapatabilirsiniz.",
  "notifications.contentFree":
    "Hatırlatmalarda sağlık bilgileriniz, bölüm adı, hekim adı veya belge adı yer almaz. Telefonunuz kilitliyken yalnızca uygulamanın adı görünür.",
  "notifications.transactionalOnly":
    "Yalnızca vizitinizle ilgili hatırlatma göndeririz. Tanıtım iletisi göndermiyoruz.",
  "notifications.switchLabel": "Hatırlatmalar",
  "notifications.on": "Açık",
  "notifications.off": "Kapalı",
  "notifications.optOutHint":
    "Kapattığınızda hiçbir hatırlatma göndermeyiz. İstediğiniz zaman yeniden açabilirsiniz.",
  "notifications.quiet": "Sessiz saatler",
  "notifications.quietHint":
    "Seçtiğiniz aralıkta hatırlatma göndermeyiz. Hazır bir aralık seçili değildir; seçim sizindir.",
  "notifications.quietNone": "Seçilmedi",
  "notifications.pending":
    "Değişikliğiniz henüz kaydedilmedi. Bağlantınızı kontrol edip yeniden deneyin.",
  "a11y.notifications.switchHint": "Hatırlatmaları açıp kapatmak için iki kez dokunun.",
  // INT-260 — Görünüm ekranının okuyucuya söyledikleri.
  "a11y.appearance.entry": "Yazı boyutu, tema ve hareket ayarlarını açar.",
  "a11y.appearance.preview": "Yazı boyutu önizlemesi",
  "a11y.appearance.size": "Yazı boyutunu buradan seçebilirsiniz.",
  "a11y.appearance.phone": "Açıkken yazı boyutu telefonunuzun ayarından gelir.",
  "a11y.appearance.theme": "Uygulamanın açık ya da koyu görünmesini belirler.",
  "a11y.appearance.motion": "Açıkken ekrandaki geçişler ve hareketler durur.",
  "a11y.appearance.start": "Yeni ziyaretin konuşarak mı yazarak mı başlayacağını belirler.",
  "a11y.notifications.quietHint": "Bu sessiz saat aralığını seçmek için iki kez dokunun.",

  // ---------------------------------------------------------------------
  // INT-133 — profiles, companions, guardian flows, proxy acknowledgement
  // (02 §3 attribution values, 06 §6 minors & companions, 13 §13 third
  // party). Register is `siz` throughout; `-in` on the short in-flow
  // choices, `-iniz` on the instructional prose.
  // ---------------------------------------------------------------------
  "me.companion": "Yakınınız adına",
  "companion.title": "Yakınınız adına",
  "companion.entry.sub": "Görüşmeyi kimin yaptığını ve nota nasıl yazıldığını ayarlayın.",
  "companion.guide.kicker": "Kim anlatıyor",
  "companion.guide.title": "Anlatanın kim olduğu nota yazılır",
  "companion.guide.body":
    "Bir yakınınız adına anlatırsanız bunu nota not düşeriz. Hekim, bilgiyi kimin verdiğini görür. Böylece hastanın kendi sözleriyle sizin anlattıklarınız birbirine karışmaz.",
  "companion.role.kicker": "Bu görüşme kimin için",
  "companion.role.self": "Kendim için",
  "companion.role.companion": "Yakınım adına",
  "companion.speaker.kicker": "Soruları kim yanıtlıyor",
  "companion.speaker.companion": "Ben anlatıyorum",
  "companion.speaker.patient": "Hasta kendisi anlatıyor",
  "companion.speaker.footer":
    "Telefon sizde olsa bile hasta kendi anlatıyorsa bunu seçin; nota hastanın kendi sözleri yazılır.",
  "companion.thirdParty.kicker": "Yanınızda biri var mı",
  "companion.thirdParty.label": "Yanımda başka biri var",
  "companion.thirdParty.footer":
    "Yanınızda biri varken bazı sorular sesli sorulmaz. Bu, mahremiyetiniz içindir.",
  "companion.ack.kicker": "Onayınız",
  "companion.ack.label": "Hastanın adına konuştuğumu onaylıyorum",
  "companion.ack.notProof":
    "Bu onay yalnızca kimin anlattığını belirtir. Hasta adına karar verme hakkınız olduğu anlamına gelmez.",
  "companion.effect.kicker": "Bu görüşmede neler değişir",
  "companion.effect.none": "Bir değişiklik yok. Sorular her zamanki gibi sorulur.",
  "companion.effect.proxy": "Notta bilgiyi yakınının verdiği yazar.",
  "companion.effect.assisted":
    "Notta hastanın kendi sözleri yer alır; yanında biri olduğu da yazılır.",
  "companion.effect.textOnly": "Özel konular sesli sorulmaz, yazıyla sorulur.",
  "companion.effect.noSafeguarding": "Bazı çok özel sorular bu görüşmede hiç sorulmaz.",
  "companion.selected": "Seçili",
  "companion.notSelected": "Seçili değil",
  "companion.guardian.kicker": "On sekiz yaşından küçükler",
  "companion.guardian.label": "Veli hesabıyla görüşme",
  "companion.guardian.unavailable": "Henüz açık değil",
  "companion.guardian.body":
    "On sekiz yaşından küçük biri için görüşme, veli hesabından ve velinin izniyle yapılır. Bu akışı henüz açmadık; hukuki çerçevesi netleşene kadar kapalı kalacak.",
  "companion.private.kicker": "On iki-on yedi yaş",
  "companion.private.body":
    "On iki ile on yedi yaş arasındaki bir hastanın özel bölümü hekime iletilir. Velinin bu bölümü görüp göremeyeceğini hastanenin yazılı politikası belirler. Kayıtlı bir politika yoksa veliye gösterilmez.",
  "companion.refusal.guardian":
    "Bu görüşme veli hesabından ve velinin izniyle yapılmalı. Şu an bu akışı açamıyoruz.",
  "companion.refusal.dobUnverified": "Doğum tarihiniz doğrulanmadan devam edemiyoruz.",
  "companion.refusal.jurisdiction": "Şu an yalnızca Türkiye'de hizmet veriyoruz.",
  "companion.refusal.ack": "Devam etmek için hastanın adına konuştuğunuzu onaylayın.",
  "a11y.companion.roleHint": "Bu seçeneği seçmek için iki kez dokunun.",
  "a11y.companion.speakerHint": "Soruları kimin yanıtladığını seçmek için iki kez dokunun.",
  "a11y.companion.ackHint": "Onayı verip geri almak için iki kez dokunun.",
  "a11y.companion.thirdPartyHint": "Yanınızda biri olduğunu belirtmek için iki kez dokunun.",

  // ---------------------------------------------------------------------
  // INT-246 — the `__DEV__` voice-lane banner. These strings never reach a
  // patient: `voiceDiagnostic` returns null unless __DEV__ and the only
  // component that renders them returns null on that null. They live in the
  // catalogue anyway because invariant 5 has no dev exemption — a string
  // outside the catalogue is a string nobody can find or translate later.
  // ---------------------------------------------------------------------
  "devVoice.title": "Geliştirici notu: ses hattı yanıt vermedi",
  "devVoice.body": "Yazılı adımlarla devam ediliyor. Denenen adresler:",
  "devVoice.hint": "Ana makinede kontrol edin: make voice-doctor",
  "devVoice.noCandidates": "Denenecek adres yapılandırılmamış",
  "devVoice.reason.timeout": "zaman aşımı",
  "devVoice.reason.refused": "bağlantı reddedildi",
  "devVoice.reason.status": "yanıt kodu",
  // ---- INT-247: önceki ziyaretlerden taşınan bilgiler ---------------------
  // Patient copy for the confirm / changed / stopped step and the
  // transparency ledger, plus the markers the note carries. The note markers
  // say who said what — never what stopping a medication means.
  "carried.kicker": "Önceki ziyaretten",
  "carried.title": "Bunlar hâlâ geçerli mi?",
  "carried.body":
    "Aşağıdaki bilgiler önceki ziyaretlerinizde kaydedilmişti. Siz yanıtlamadan hiçbiri bu ziyaretin notuna güncel bilgi olarak yazılmaz.",
  "carried.action.confirm": "Devam ediyorum",
  "carried.action.changed": "Değişti",
  "carried.action.stopped": "Bıraktım",
  "carried.action.undo": "Yanıtı geri alın",
  "carried.state.unconfirmed": "Henüz yanıtlamadınız",
  "carried.state.confirmed": "Devam ediyor",
  "carried.state.changed": "Değişti",
  "carried.state.stopped": "Bıraktım",
  "carried.recordedOn": "Kayıt tarihi",
  "carried.source.confirmed_intake_extraction": "Önceki görüşmenizde kendiniz söylemiştiniz",
  "carried.source.clinician_accepted_note": "Hekiminizin onayladığı notta yer alıyor",
  "carried.source.confirmed_imported_record": "Onayladığınız bir belgeden geldi",
  "carried.empty": "Önceki ziyaretlerden taşınan bir bilgi yok.",
  "carried.ledger.body":
    "Burada, önceki ziyaretlerinizden taşınan bilgileri ve her birinin nereden geldiğini görürsünüz. Hangisinin bugün de geçerli olduğunu her ziyaretin gözden geçirme adımında sorarız.",
  "note.fact.previousRecord": "önceki kayıt",
  "note.fact.unconfirmed": "bu ziyarette onaylanmadı",
  "note.fact.confirmed.patient": "hasta bu ziyarette devam ettiğini söyledi",
  "note.fact.confirmed.clinician": "hekim bu ziyarette devam ettiğini kaydetti",
  "note.fact.changed.patient": "hasta değiştiğini söyledi; yeni bilgi alınmadı",
  "note.fact.changed.clinician": "hekim değiştiğini kaydetti; yeni bilgi alınmadı",
  "note.fact.stopped.patient": "hasta bıraktığını söyledi",
  "note.fact.stopped.clinician": "hekim bırakıldığını kaydetti",
  "a11y.carried.hint": "Bu bilginin bugün de geçerli olup olmadığını seçmek için iki kez dokunun.",
  // ---- INT-256: her ön görüşmede sorulan geçmiş bilgileri ------------------
  // 04 §1 satır 5–6 (`meds_allergies`, `pmh_fh_sh`). Soru metinleri
  // packages/protocols/base/intake.yaml içindeki `ask_tr`/`follow_up_tr`
  // ifadelerini izler. Hiçbiri bir şiddet derecesi sormaz, hiçbiri bir
  // yanıttan sonuç çıkarmaz; yanıtlar yalnızca kaydedilir.
  "intake.q.allergyKnown": "Bilinen bir ilaç ya da madde alerjiniz var mı?",
  "intake.q.allergyKind": "Alerjiniz neye karşı?",
  "intake.q.allergyDetail": "Alerjinizin adını kendi sözlerinizle yazabilir misiniz?",
  "intake.q.allergyDetail.hint": "Adını hatırlamıyorsanız nasıl göründüğünü de yazabilirsiniz.",
  "intake.q.allergyReaction": "Alerjiniz olduğunda neler oluyor?",
  "intake.q.medsOther": "Burada görünmeyen bir ilaç kullanıyor musunuz?",
  "intake.q.medsOtherDetail": "İlacın adını kendi sözlerinizle yazabilir misiniz?",
  "intake.q.medsOtherDetail.hint": "Adını bilmiyorsanız kutusunun rengini de yazabilirsiniz.",
  "intake.q.medsOtc": "Reçetesiz ya da bitkisel bir ürün kullanıyor musunuz?",
  "intake.q.medsOtcDetail": "Bu ürünlerin adını yazabilir misiniz?",
  "intake.q.medsOtcDetail.hint": "Vitamin, bitki çayı ve takviyeler de bu gruba girer.",
  "intake.q.pmhKnown": "Doktorunuzun size söylediği bir hastalık var mı?",
  "intake.q.pmhConditions": "Bunlardan hangileri sizde var?",
  "intake.q.pmhOtherDetail": "Bu hastalığın adını kendi sözlerinizle yazabilir misiniz?",
  "intake.q.pmhSurgery": "Daha önce ameliyat oldunuz mu?",
  "intake.q.pmhSurgeryDetail": "Hangi ameliyatı olduğunuzu yazabilir misiniz?",
  "intake.q.pmhSurgeryDetail.hint": "Yılını hatırlıyorsanız onu da yazabilirsiniz.",
  "intake.q.pmhRecentChange": "Son görüşmenizden bu yana yeni bir gelişme oldu mu?",
  "intake.q.pmhRecentDetail": "Ne olduğunu kendi sözlerinizle yazabilir misiniz?",
  "intake.q.pmhRecentDetail.hint": "Yeni bir tanı ya da hastane yatışı olabilir.",
  "intake.q.fhKnown": "Ailenizde bilinen bir hastalık var mı?",
  "intake.q.fhWho": "Ailenizde kimlerde var?",
  "intake.q.fhDetail": "Ailenizdeki hastalığın adını yazabilir misiniz?",
  "intake.opt.allergyMedicine": "İlaç",
  "intake.opt.allergyFood": "Besin",
  "intake.opt.allergySting": "Arı sokması",
  "intake.opt.allergyLatex": "Lateks",
  "intake.opt.allergyPollenDust": "Polen ya da toz",
  "intake.opt.reactionRash": "Döküntü ya da kaşıntı",
  "intake.opt.reactionSwelling": "Şişme",
  "intake.opt.pmhDiabetes": "Şeker hastalığı",
  "intake.opt.pmhBloodPressure": "Yüksek tansiyon",
  "intake.opt.pmhAsthmaCopd": "Astım ya da KOAH",
  "intake.opt.pmhKidney": "Böbrek hastalığı",
  "intake.opt.pmhThyroid": "Tiroit hastalığı",
  "intake.opt.fhMother": "Anne",
  "intake.opt.fhFather": "Baba",
  "intake.opt.fhChild": "Çocuk",
  "intake.opt.fhGrandparent": "Büyükanne ya da büyükbaba",
  // Not satırı etiketleri: yanıtın hekim notundaki kısa başlığı.
  "intake.note.allergyKnown": "Bilinen alerji",
  "intake.note.allergyKind": "Alerji türü",
  "intake.note.allergyDetail": "Alerji ayrıntısı",
  "intake.note.allergyReaction": "Alerji tepkisi",
  "intake.note.medsOther": "Listede olmayan ilaç",
  "intake.note.medsOtherDetail": "İlaç ayrıntısı",
  "intake.note.medsOtc": "Reçetesiz ya da bitkisel ürün",
  "intake.note.medsOtcDetail": "Ürün ayrıntısı",
  "intake.note.pmhKnown": "Bilinen hastalık",
  "intake.note.pmhConditions": "Takip edilen hastalıklar",
  "intake.note.pmhOtherDetail": "Diğer hastalık",
  "intake.note.pmhSurgery": "Geçirilmiş ameliyat",
  "intake.note.pmhSurgeryDetail": "Ameliyat ayrıntısı",
  "intake.note.pmhRecentChange": "Son görüşmeden bu yana",
  "intake.note.pmhRecentDetail": "Yeni gelişme",
  "intake.note.fhKnown": "Ailede bilinen hastalık",
  "intake.note.fhWho": "Yakınlık derecesi",
  "intake.note.fhDetail": "Ailedeki hastalık",
  "review.section.pmh": "Geçmiş hastalıklar",
  "review.section.allergies": "Alerjiler",
  "review.section.familySocial": "Ailede görülen hastalıklar",
  "note.deferred.familyHistory": "Aile öyküsü",
  // Taşınan alerji için ayrı sözcükler: bir alerji "bırakılmaz", olduğu ya
  // da olmadığı söylenir. Aynı üç sonuç, alerjinin dilinde (INT-247 sözlüğü).
  "carried.action.allergy.confirm": "Hâlâ var",
  "carried.action.allergy.changed": "Farklı oldu",
  "carried.action.allergy.stopped": "Bende yok",
  "carried.state.allergy.confirmed": "Hasta doğruladı",
  "carried.state.allergy.changed": "Farklı olduğu söylendi",
  "carried.state.allergy.stopped": "Böyle bir alerji yok",
  "note.fact.allergy.confirmed.patient": "hasta bu ziyarette doğruladı",
  "note.fact.allergy.confirmed.clinician": "hekim bu ziyarette doğruladı",
  "note.fact.allergy.changed.patient": "hasta farklı olduğunu söyledi; yeni bilgi alınmadı",
  "note.fact.allergy.changed.clinician": "hekim farklı olduğunu kaydetti; yeni bilgi alınmadı",
  "note.fact.allergy.stopped.patient": "hasta böyle bir alerjisi olmadığını söyledi",
  "note.fact.allergy.stopped.clinician": "hekim böyle bir alerji olmadığını kaydetti",
  // ---- INT-282: sahibinin HBYS şemasından gelen taban katman -------------
  // docs/sources/hbys_intake_schema.md — hastanın kendisinin yanıtlayabildiği
  // alanlar. Hiçbir seçenek listesi bir şiddet sırası taşımaz, hiçbir yanıt
  // bir eşik ya da bir yorum üretmez; yalnızca kaydedilir.
  "intake.q.onsetTodayWhen": "Bugün ne zaman başladı?",
  "intake.q.durationCourse": "Başladığından bu yana nasıl gidiyor?",
  "intake.hpi.onsetTodayWhen": "Bugün başlama zamanı",
  "intake.hpi.durationCourse": "Gidişi",
  "intake.opt.startedMorning": "Sabah",
  "intake.opt.startedAfternoon": "Öğleden sonra",
  "intake.opt.startedEvening": "Akşam",
  "intake.opt.startedNight": "Gece",
  "intake.opt.courseSame": "Aynı",
  "intake.opt.courseIncreasing": "Artıyor",
  "intake.opt.courseDecreasing": "Azalıyor",
  "intake.opt.courseComesGoes": "Gelip gidiyor",
  "intake.q.smoking": "Sigara kullanımınızı hangisi en iyi anlatıyor?",
  "intake.q.smokingQuitWhen": "Sigarayı ne zaman bıraktınız?",
  "intake.q.alcohol": "Alkol kullanıyor musunuz?",
  "intake.q.substance": "İlaç dışında herhangi bir madde kullanıyor musunuz?",
  "intake.q.occupation": "Ne iş yapıyorsunuz?",
  "intake.q.occupation.hint": "Çalışmıyorsanız ya da emekliyseniz bunu da yazabilirsiniz.",
  "intake.q.disability": "Engellilik durumunuz var mı?",
  "intake.q.injuryHistory": "Daha önce bir yaralanma geçirdiniz mi?",
  "intake.q.injuryDetail": "Yaralanmayı kendi sözlerinizle yazabilir misiniz?",
  "intake.q.injuryDetail.hint": "Ne olduğunu ve ne zaman olduğunu yazabilirsiniz.",
  "intake.q.bloodGroup": "Kan grubunuz nedir?",
  "intake.q.bloodGroup.hint": "Emin değilseniz bilmiyorum seçeneğini işaretleyiniz.",
  "intake.q.transfusion": "Daha önce kan ya da kan ürünü aldınız mı?",
  "intake.q.fhMotherConditions": "Annenizde bunlardan hangileri var?",
  "intake.q.fhFatherConditions": "Babanızda bunlardan hangileri var?",
  "intake.q.fhBrotherConditions": "Erkek kardeşinizde bunlardan hangileri var?",
  "intake.q.fhSisterConditions": "Kız kardeşinizde bunlardan hangileri var?",
  "intake.q.painPresent": "Şu anda ağrınız var mı?",
  "intake.q.painScore": "Ağrınızı sıfır ile on arasında nasıl puanlarsınız?",
  "intake.q.height": "Boyunuz kaç santimetre?",
  "intake.q.weight": "Kilonuz kaç kilogram?",
  "intake.q.measure.hint": "Yaklaşık bir değer de olur; artı ve eksi ile ayarlayınız.",
  "intake.opt.smokingNever": "Hiç kullanmadım",
  "intake.opt.smokingFormer": "Kullandım, bıraktım",
  "intake.opt.smokingDaily": "Her gün düzenli içiyorum",
  "intake.opt.smokingOccasional": "Ara sıra içiyorum",
  "intake.opt.notStated": "Belirtmek istemiyorum",
  "intake.opt.quitThisYear": "Bu yıl içinde",
  "intake.opt.quitFewYears": "Son birkaç yıl içinde",
  "intake.opt.quitLongAgo": "Daha önce",
  "intake.opt.disabilityNone": "Yok",
  "intake.opt.disabilityPhysical": "Bedensel engel",
  "intake.opt.disabilityIntellectual": "Zihinsel engel",
  "intake.opt.disabilityVision": "Görme engeli",
  "intake.opt.disabilityHearing": "İşitme engeli",
  // Sıfır grubu rakamla değil sözcükle yazılır (invariant 22): hiçbir rakam
  // seslendirilebilecek bir metne girmez.
  "intake.opt.bloodAbPos": "AB Rh pozitif",
  "intake.opt.bloodAbNeg": "AB Rh negatif",
  "intake.opt.bloodAPos": "A Rh pozitif",
  "intake.opt.bloodANeg": "A Rh negatif",
  "intake.opt.bloodBPos": "B Rh pozitif",
  "intake.opt.bloodBNeg": "B Rh negatif",
  "intake.opt.bloodOPos": "Sıfır Rh pozitif",
  "intake.opt.bloodONeg": "Sıfır Rh negatif",
  "intake.opt.bloodUnknown": "Bilmiyorum",
  "intake.opt.fhBrother": "Erkek kardeş",
  "intake.opt.fhSister": "Kız kardeş",
  "intake.opt.fhHt": "Yüksek tansiyon",
  "intake.opt.fhCardiac": "Kalp-damar hastalığı",
  "intake.opt.fhCancer": "Kanser",
  "intake.opt.fhDiabetes": "Şeker hastalığı",
  "intake.opt.fhBlood": "Kan hastalığı",
  "intake.opt.fhNotSure": "Bilmiyorum",
  "intake.opt.pmhHeart": "Kalp-damar hastalığı",
  "intake.opt.pmhCancer": "Kanser",
  "intake.opt.pmhBlood": "Kan hastalığı",
  // Ağrı puanının etiketleri sözcüktür; rakam yalnızca ekrandaki inline
  // gösterimdir (invariant 22).
  "intake.opt.numZero": "Sıfır",
  "intake.opt.numOne": "Bir",
  "intake.opt.numTwo": "İki",
  "intake.opt.numThree": "Üç",
  "intake.opt.numFour": "Dört",
  "intake.opt.numFive": "Beş",
  "intake.opt.numSix": "Altı",
  "intake.opt.numSeven": "Yedi",
  "intake.opt.numEight": "Sekiz",
  "intake.opt.numNine": "Dokuz",
  "intake.opt.numTen": "On",
  "intake.unit.cm": "cm",
  "intake.unit.kg": "kg",
  "intake.note.smoking": "Sigara",
  "intake.note.smokingQuitWhen": "Sigarayı bırakma",
  "intake.note.alcohol": "Alkol",
  "intake.note.substance": "Madde kullanımı",
  "intake.note.occupation": "Meslek",
  "intake.note.disability": "Engellilik durumu",
  "intake.note.injuryHistory": "Yaralanma geçmişi",
  "intake.note.injuryDetail": "Yaralanma ayrıntısı",
  "intake.note.bloodGroup": "Beyan edilen kan grubu",
  "intake.note.transfusion": "Kan ya da kan ürünü alma",
  "intake.note.fhMother": "Annede",
  "intake.note.fhFather": "Babada",
  "intake.note.fhBrother": "Erkek kardeşte",
  "intake.note.fhSister": "Kız kardeşte",
  "intake.note.painPresent": "Ağrı var mı",
  "intake.note.painScore": "Ağrı puanı",
  "intake.note.height": "Boy",
  "intake.note.weight": "Kilo",
  "review.section.measurements": "Ölçümler",
  "a11y.measure.decrease": "Bir azalt",
  "a11y.measure.decreaseMore": "Daha çok azalt",
  "a11y.measure.increase": "Bir artır",
  "a11y.measure.increaseMore": "Daha çok artır",
  "intake.measure.untouched": "Değeri ayarladığınızda kaydedilir.",
  // --- INT-286 · open-ended asking ------------------------------------------
  // What an OPEN question is asked with instead of its option list. The agent
  // speaks the scripted question verbatim and adds this; the typed screen
  // puts the same invitation over the answer field and keeps the options
  // under it as the fallback.
  "dialogue.openInvite": "Kendi sözlerinizle anlatabilirsiniz.",
  "intake.open.hint": "Kendi sözlerinizle yazabilir ya da söyleyebilirsiniz.",
  "intake.open.orChoose": "Ya da aşağıdan seçebilirsiniz.",

  // --- INT-414 · conversational delivery ------------------------------------
  // The words AROUND a question, never inside it: the welcome, lead-ins, topic
  // transitions, acknowledgements and the closing (lib/dialogue/delivery.ts).
  // Rules every line here keeps, and delivery.test.ts plus
  // tests/release/test_delivery_copy.py hold: siz register, B1, warmth from
  // the -elim/-alım mood; no question and no mı/mi/mu/mü, because the question
  // that follows is the turn's one question; no numeral; no diagnosis,
  // treatment, prognosis or reassurance; nothing about where answers go
  // (docs/legal/strings.yaml does not exist) and no "tekrar" command (the dev
  // dialogue has none). For clinician review under HB-C1 — the table is in
  // docs/evidence/INT-414.md; nothing here is signed.
  "dialogue.delivery.welcome.a": "Hoş geldiniz. Muayenenizden önce size bazı sorular soracağım.",
  "dialogue.delivery.welcome.b":
    "Merhaba, hoş geldiniz. Muayeneden önce birlikte bazı sorular üzerinden geçelim.",
  "dialogue.delivery.welcome.c":
    "Hoş geldiniz. Muayenenize hazırlık için size bazı sorular sormak istiyorum.",
  "dialogue.delivery.orientVoice.a":
    "Soruları ekranda da görebilirsiniz. Dilerseniz yazarak da yanıt verebilirsiniz.",
  "dialogue.delivery.orientVoice.b":
    "Ben konuşurken araya girebilirsiniz. Sorular ekranda yazılı olarak da durur.",
  "dialogue.delivery.orientTyped.a": "Soruları kendi hızınızda yanıtlayabilirsiniz.",
  "dialogue.delivery.orientTyped.b": "Acele etmeden, kendi hızınızda ilerleyebilirsiniz.",
  "dialogue.delivery.resume.a": "Kaldığımız yerden devam edelim.",
  "dialogue.delivery.resume.b": "Kaldığımız yerden sürdürelim.",
  "dialogue.delivery.lead.a": "Devam edelim.",
  "dialogue.delivery.lead.b": "Sıradaki soruya geçelim.",
  "dialogue.delivery.lead.c": "Şimdi şunu soralım.",
  "dialogue.delivery.lead.d": "Bir de şunu öğrenmek istiyorum.",
  "dialogue.delivery.thanks.a": "Teşekkürler.",
  "dialogue.delivery.thanks.b": "Teşekkür ederim.",
  "dialogue.delivery.thanks.c": "Not aldım, teşekkürler.",
  "dialogue.delivery.hesitant.a": "Anlıyorum, devam edelim.",
  "dialogue.delivery.hesitant.b": "Peki, bu şekilde not aldım.",
  "dialogue.delivery.revised.a": "Düzeltmeniz için teşekkürler.",
  "dialogue.delivery.revised.b": "Düzelttiğinizi not aldım.",
  // The silence lines are said after a turn with no words, in front of the
  // NEXT question. The skipped one always returns in the manual steps
  // (stream.ts: asked, unanswered, hand-over), so they may say so.
  "dialogue.delivery.silence.a": "Önceki soruya sonra ekrandan dönebilirsiniz.",
  "dialogue.delivery.silence.b": "Önceki soruyu daha sonra ekranda yanıtlayabilirsiniz.",
  "dialogue.delivery.repair.b": "Yanıtınızı tam anlayamadım. Soruyu bir kez daha soralım.",
  "dialogue.delivery.pain.a": "Ağrınızı biraz daha iyi anlamak istiyorum.",
  "dialogue.delivery.pain.b": "Ağrınızla ilgili birkaç ayrıntı soralım.",
  "dialogue.delivery.instrument.a":
    "Sıradaki sorular standart bir ankete ait. Bu yüzden her zaman aynı şekilde sorulur.",
  "dialogue.delivery.instrument.b": "Şimdi herkese aynı biçimde sorulan bir ankete geçelim.",
  "dialogue.delivery.sensitive.a":
    "Sıradaki konu biraz daha özel. Acele etmeden yanıtlayabilirsiniz.",
  "dialogue.delivery.sensitive.b": "Şimdi biraz daha kişisel bir konuya geçelim.",
  "dialogue.delivery.sensitiveLead.a": "Yavaş yavaş devam edelim.",
  "dialogue.delivery.sensitiveLead.b": "Size rahat gelen şekilde yanıtlayabilirsiniz.",
  "dialogue.delivery.topic.allergies.a": "Şimdi alerjilerle ilgili sorulara geçelim.",
  "dialogue.delivery.topic.allergies.b": "Sırada alerjilerle ilgili sorular var.",
  "dialogue.delivery.topic.medications.a": "Şimdi ilaçlarla ilgili sorulara geçelim.",
  "dialogue.delivery.topic.medications.b": "Sırada ilaçlarla ilgili sorular var.",
  "dialogue.delivery.topic.pmh.a": "Şimdi sağlık geçmişinizle ilgili sorulara geçelim.",
  "dialogue.delivery.topic.pmh.b": "Sırada sağlık geçmişinizle ilgili sorular var.",
  "dialogue.delivery.topic.family.a":
    "Şimdi ailenizin sağlık geçmişine geçelim. Acele etmeden yanıtlayabilirsiniz.",
  "dialogue.delivery.topic.family.b": "Sıradaki sorular ailenizin sağlık geçmişiyle ilgili.",
  "dialogue.delivery.topic.social.a": "Şimdi günlük yaşamınızla ilgili sorulara geçelim.",
  "dialogue.delivery.topic.social.b": "Sırada günlük yaşamınızla ilgili sorular var.",
  "dialogue.delivery.topic.measurements.a": "Şimdi birkaç ölçümle ilgili bilgi alalım.",
  "dialogue.delivery.topic.measurements.b": "Sırada ölçümlerle ilgili sorular var.",
  "dialogue.delivery.topic.wrapup.a": "Bitirmeden önce şunu da soralım.",
  "dialogue.delivery.topic.wrapup.b": "Sona yaklaştık.",
  "dialogue.delivery.closing.a": "Sorularım bu kadar. Zaman ayırdığınız için teşekkür ederim.",
  "dialogue.delivery.closing.b": "Soruların sonuna geldik. Zaman ayırdığınız için teşekkürler.",

  // --- INT-137 · Gönder'den önceki paylaşım özeti (02 §5.4: ne, kiminle, ne
  // zamana kadar). Süre bir sayaç değil, bir dayanak: 02 §2 Doctor Link
  // süresini randevuya bağlar, gönderim anına değil — bu yüzden metinde
  // rakam yoktur ve cihaz hiçbir saat hesaplamaz.
  "review.consent.title": "Paylaşım özeti",
  "review.consent.sections": "Paylaşılan bölümler",
  "review.consent.nothing": "Şu anda hiçbir bölüm paylaşılmıyor.",
  "review.consent.recipient": "Kime gidiyor",
  "review.consent.until": "Ne zamana kadar",
  "review.consent.untilValue": "Paylaşım, randevunuzun saatinden üç gün sonra sona erer.",
  // --- INT-137 · gönderimden sonra sorulan memnuniyet sorusu. 06 §2
  // `satisfaction` izni yoksa kart hiç görünmez ve hiçbir şey toplanmaz.
  // Ölçek rakamla değil sözcükle sorulur (invariant 22).
  "csat.title": "Bu görüşme nasıldı?",
  "csat.optional": "Bu soru isteğe bağlıdır. Yanıtlamasanız da notunuz gönderildi.",
  "csat.scoreGroup": "Görüşme değerlendirmesi",
  "csat.score.veryBad": "Çok kötüydü",
  "csat.score.bad": "Kötüydü",
  "csat.score.ok": "İdare eder",
  "csat.score.good": "İyiydi",
  "csat.score.veryGood": "Çok iyiydi",
  "csat.reasonGroup": "Bunun nedeni",
  "csat.reason.tooLong": "Çok uzundu",
  "csat.reason.didntUnderstandMe": "Beni anlamadı",
  "csat.reason.feltRushed": "Acele ettirdi",
  "csat.reason.helpful": "Yardımcı oldu",
  "csat.reason.feltHeard": "Dinlendiğimi hissettim",
  "csat.thanks": "Teşekkür ederiz.",
  // --- INT-136 · validated instruments on the typed surface ----------------
  // What the screen says when an instrument cannot be administered. It names
  // no scale and no score: the item text itself is never in this catalogue
  // (invariant 10 — it comes verbatim from the pack), and today no pack is
  // servable (HB-C1) and two of the four instruments are licence-BLOCKED
  // (HB-L2, HB-L3). Deliberately unalarming: an unauthored screening section
  // costs the patient nothing.
  "intake.instrument.unavailable.title": "Bu bölüm şimdilik kapalı",
  "intake.instrument.unavailable.body":
    "Bu bölümün soruları henüz hazır değil. Hazır olduğunda burada göreceksiniz; şimdilik bu adımı boş bırakabilirsiniz.",
  // --- INT-139 · Paylaşımlarınız: açık paylaşımlar, durdurma ve erişim
  // kaydı. Üç kural bu bloğun biçimini belirler: ekranda hiçbir sayı yoktur
  // (INT-140 yazım kararı — sayılar yalnızca tarih olarak görünür), hiçbir
  // süre ölçüsü geçmez (invariant 20 — ölçüm docs/evidence/ dosyasındadır),
  // ve erişim kaydı kişi adı değil rol gösterir (files/10 §3).
  "shares.title": "Paylaşımlarınız",
  "shares.sub": "Açık paylaşımlar ve erişim kaydı",
  "shares.guide.kicker": "Paylaşım",
  "shares.guide.title": "Notunuza kimin erişimi var",
  "shares.guide.body":
    "Notunuzu paylaştığınız her erişim burada listelenir. Dilediğiniz an durdurabilirsiniz.",
  "shares.active": "Açık paylaşımlar",
  "shares.empty": "Bu not için açık paylaşım yok.",
  "shares.unreachable": "Paylaşımlar şu anda okunamadı. Bu liste eksik olabilir.",
  "shares.until": "Bitiş",
  "shares.state.live": "Açık",
  "shares.state.revoked": "Durduruldu",
  "shares.state.expired": "Süresi doldu",
  "shares.state.usedUp": "Görüntüleme hakkı bitti",
  "shares.revoke": "Erişimi durdurun",
  "shares.revoke.confirm": "Durdurmayı onaylayın",
  "shares.revoke.effect":
    "Durdurduğunuz bir paylaşım, bir sonraki açma denemesinde artık çalışmaz.",
  "shares.revoke.unsent": "Durdurma isteği ulaşmadı. Paylaşım açık kalmış olabilir.",
  "shares.log": "Erişim kaydı",
  "shares.log.empty": "Bu not için henüz erişim kaydı yok.",
  "shares.log.noNames": "Kayıtta kişi adı yer almaz; yalnızca rol görünür.",
  "shares.log.role.self": "Siz",
  "shares.log.role.guardian": "Yasal temsilci",
  "shares.log.role.clinician": "Hekim",
  "shares.log.role.clinicStaff": "Klinik çalışanı",
  "shares.log.role.system": "Sistem",
  "shares.log.role.unknown": "Belirlenemedi",
  "shares.log.category.recordViewed": "Kayıt görüntülendi",
  "shares.log.category.recordShared": "Kayıt paylaşıldı",
  "shares.log.category.recordUpdated": "Kayıt güncellendi",
  "shares.log.category.consentChanged": "İzin değişti",
  "shares.log.category.accountSecurity": "Hesap güvenliği",
  "shares.log.category.dataRequest": "Veri talebi",
  "shares.log.category.preferencesChanged": "Tercih değişti",
  "shares.log.category.staffReview": "Klinik incelemesi",
  "shares.log.category.systemIntegrity": "Sistem kaydı",
  "shares.log.category.other": "Diğer işlem",
  "shares.held": "Bu liste sunucudaki kayıttan gelir; telefonunuzda saklanmaz.",
  // INT-311 — issuing a Doctor Link from the patient's phone. In-app only:
  // the link and the code are shown on this screen and go nowhere (HB-O7).
  "shares.issue.entry": "Yeni bağlantı",
  "shares.issue.sub": "Hekiminize gösterin",
  "shares.issue.title": "Paylaşım bağlantısı",
  "shares.issue.guide.kicker": "Paylaşım",
  "shares.issue.guide.title": "Yalnızca bu ekranda",
  "shares.issue.guide.body":
    "Bu bağlantı yalnızca bu ekranda görünür ve hiçbir yere gönderilmez. Ekranı hekiminize gösterin.",
  "shares.issue.recipient.label": "Kimin için?",
  "shares.issue.recipient.hint": "Hekiminizin adını yazın.",
  "shares.issue.create": "Bağlantı oluşturun",
  "shares.issue.created.title": "Bağlantı hazır",
  "shares.issue.code.label": "Açma kodu",
  "shares.issue.key.label": "Bağlantı anahtarı",
  "shares.issue.show":
    "Bu kodu ve anahtarı muayenede hekiminize gösterin. Hekiminiz notunuzu bunlarla açar.",
  "shares.issue.oneScreen": "Bu bilgiler yalnızca burada görünür; bu telefonda saklanmaz.",
  "shares.issue.back": "Paylaşımlara dönün",
  "shares.issue.error.notShared": "Bu not henüz paylaşılmadı. Önce notu gönderin.",
  "shares.issue.error.dateUnknown": "Bu vizitin tarihi yok. Vizit tarihini ekleyin.",
  "shares.issue.error.recipient": "Bu adı kontrol edin.",
  "shares.issue.error.limited": "Çok fazla deneme oldu. Biraz sonra tekrar deneyin.",
  "shares.issue.error.unavailable": "Paylaşım şu anda açık değil. Sonra tekrar deneyin.",
  "shares.issue.error.unreachable": "Bağlantı kurulamadı. Sonra tekrar deneyin.",
  "a11y.shares.revokeHint": "İki kez dokunmak bu paylaşımı durdurur.",
  "a11y.shares.confirmHint": "İki kez dokunmak durdurma isteğini gönderir.",
  "a11y.shares.issueHint": "Hekiminize gösterebileceğiniz bir bağlantı oluşturur.",

  // INT-143 — kiosk mode. Mostly staff-facing (clinic PIN entry), which may be
  // plainer; the one patient-facing line is the privacy note, in siz, ≤ B1.
  "kiosk.lock.title": "Kiosk modu",
  "kiosk.lock.body": "Personel için: Başlatmak için klinik PIN'ini girin.",
  "kiosk.pin.label": "Klinik PIN'i",
  "kiosk.pin.hint": "Klinik personelinin bildiği PIN'i girin.",
  "kiosk.pin.arm": "Kiosk modunu başlatın",
  "kiosk.pin.disarm": "Kiosk modundan çıkın",
  "kiosk.pin.recover": "Kilidi yeniden kurun",
  "kiosk.pin.submitHint": "Girilen PIN'i doğrular.",
  "kiosk.pin.wrong": "PIN doğru değil. Yeniden deneyin.",
  "kiosk.pin.lockedOut": "Çok fazla deneme oldu. Biraz sonra tekrar deneyin.",
  "kiosk.exit": "Kiosk modundan çıkın",
  "kiosk.exitHint": "Klinik PIN'i ile bu cihazı normal moda döndürür.",
  "kiosk.exit.title": "Kiosk modundan çıkış",
  "kiosk.exit.body": "Personel için: Çıkmak için klinik PIN'ini girin.",
  "kiosk.tamper.title": "Güvenlik uyarısı",
  "kiosk.tamper.banner": "Cihaz kilidi kalktı",
  "kiosk.tamper.body":
    "Bu cihazın kiosk kilidi artık etkin değil. Devam etmeden önce personel cihazı yeniden kilitlemeli, sonra klinik PIN'ini girmeli.",
  "kiosk.privacy.note": "Bu paylaşılan bir cihazdır. Bilgileriniz burada saklanmaz.",
  // INT-363 — the idle warning (WCAG 2.2 SC 2.2.1): patient-facing, siz, ≤ B1,
  // calm. No number: the grace is a constant in lib/kiosk, never copy.
  "kiosk.idle.warning":
    "Hâlâ burada mısınız? Bilgilerinizi korumak için oturum birazdan kapanacak.",
  "kiosk.idle.extend": "Devam edin",
  "kiosk.idle.extendHint": "Oturumu açık tutar.",
  // INT-446 — the controls around a RED. The RED's own words are never here:
  // they come verbatim from the rule's `tr` (invariant 10). Inside RED the
  // bare imperative plural is the register, because ambiguity is the harm.
  "red.call112": "112'yi arayın",
  "red.location.yes": "Evet",
  "red.location.no": "Hayır",
  "red.doNots": "Lütfen yapmayın",
} as const;

export type MessageKey = keyof typeof tr;
