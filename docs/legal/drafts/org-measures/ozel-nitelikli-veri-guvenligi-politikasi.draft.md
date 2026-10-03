> TASLAK — hukuk danışmanı onayı gerektirir / DRAFT — requires counsel sign-off; not in force

# Özel Nitelikli Kişisel Verilerin Güvenliği Politikası ve Prosedürü (taslak)

Kurul Kararı 2018/10, madde 1: *"Özel nitelikli kişisel verilerin güvenliğine yönelik
sistemli, kuralları net bir şekilde belli, yönetilebilir ve sürdürülebilir ayrı bir
politika ve prosedürün belirlenmesi"*. Bu belge o politikanın taslağıdır (INT-364;
`docs/legal/special-category-measures.yaml`, madde 1, açık nokta `policy-adopted`).

Bu taslak, depodaki mühendislik belgelerinin (files/10, `docs/security/`) yerine geçmez;
onların hangi kuralı karşıladığını gösterir. Taslakta geçen hiçbir teknik kontrol burada
yeniden anlatılmaz, yalnızca yeri gösterilir: kontrolün var olup olmadığı ve canlı
sinyali `docs/legal/special-category-measures.yaml` dosyasında izlenir.

## 1. Amaç

Bu politika, INTAKE'in (bundan sonra "Şirket") işlediği özel nitelikli kişisel verilerin
güvenliği için 6698 sayılı Kanunun 6 ncı maddesinin (4) numaralı fıkrası ve 12 nci
maddesi ile Kurul Kararı 2018/10 uyarınca alınacak önlemleri, bu önlemlerden sorumlu
kişileri ve önlemlerin nasıl kayıt altına alınacağını belirler.

## 2. Kapsam

- **Veri:** Kanunun 6 ncı maddesinin (1) numaralı fıkrasında sayılan veriler; Şirket
  bakımından başta sağlık ve cinsel hayata ilişkin veriler.
- **Roller:** Şirketin veri sorumlusu olduğu hasta uygulaması ile veri işleyen olduğu
  hastane kurulumları (files/06 §0.1). Veri işleyen rolünde bu politika, hastane ile
  yapılan sözleşmenin güvenlik ekine ek olarak uygulanır.
- **Kişiler:** çalışanlar, yükleniciler, stajyerler ve Şirket adına hasta verisine
  erişebilen hekimler dâhil, bu verilere erişebilen herkes.
- **Ortamlar:** elektronik ortamlar, fiziksel ortamlar ve aktarımlar.

## 3. Genel ilkeler

Kanunun 4 üncü maddesinin (2) numaralı fıkrasındaki ilkelere uyulur: hukuka ve dürüstlük
kurallarına uygun olma; doğru ve gerektiğinde güncel olma; belirli, açık ve meşru
amaçlar için işlenme; işlendikleri amaçla bağlantılı, sınırlı ve ölçülü olma; gerekli
olan süre kadar muhafaza edilme.

## 4. Roller ve sorumluluklar

| rol | sorumluluk |
|---|---|
| Politika sahibi (Şirketi temsile yetkili kişi) | Politikayı onaylar, kaynak ayırır, açık noktaların kapatılmasını izler. |
| Güvenlik sorumlusu (files/10 §10) | Teknik önlemleri yürütür, erişim gözden geçirmelerini düzenler, ihlal müdahale planını işletir. |
| Hukuk danışmanı | Kurul kararlarının yorumunu ve metinleri onaylar. |
| İrtibat kişisi (VERBİS kaydı varsa) | Kurum ile yazışmaları yürütür. |
| Her yetkili kullanıcı | Bu politikaya, gizlilik taahhütnamesine ve aktarım kurallarına uyar; şüpheli durumu hemen bildirir. |

## 5. Çalışanlara yönelik önlemler (Karar 2018/10, madde 2)

1. **Eğitim (2-a).** Hasta verisine erişim verilmeden önce ve düzenli aralıklarla eğitim
   verilir; ayrıntı `kvkk-egitim-plani.draft.md`. Katılım kaydı tutulur.
2. **Gizlilik taahhüdü (2-b).** Erişim verilmeden önce `gizlilik-taahhutnamesi.draft.md`
   imzalatılır; imzalı nüsha saklanır.
3. **Yetki tanımı (2-c).** Her yetkili kullanıcının rolü, erişebildiği veri ve erişim
   süresi yazılı olarak tanımlanır. Hasta içeriğine personel erişimi yalnızca kayıt altına
   alınan acil erişim (break-glass) yoluyla olur. Teknik karşılığı: 2(c) kontrolleri.
4. **Periyodik yetki kontrolü (2-ç).** Yetkiler en az üç ayda bir gözden geçirilir;
   gözden geçirmeyi yapan ve onaylayan kişi ile tarih kayda geçer
   (`docs/runbooks/access-review.md`). Teknik karşılığı: 2(ç) kontrolleri.
5. **Görev değişikliği ve ayrılış (2-d).** Görevi değişen veya ayrılan kişinin yetkileri
   aynı gün kaldırılır; kendisine tahsis edilen bilgisayar, telefon, anahtar ve benzeri
   envanter tutanakla geri alınır. Teknik karşılığı: 2(d) kontrolleri.

## 6. Elektronik ortam (Karar 2018/10, madde 3)

1. **Şifreli saklama (3-a)** ve **anahtarların ayrı ve güvenli ortamda tutulması (3-b):**
   veriler kriptografik yöntemlerle saklanır; anahtarlar verinin bulunduğu ortamdan ayrı
   tutulur. Üretim anahtarlarının açılış (unseal) paylarının kimde ve nerede tutulduğu
   yazılı olarak kayda geçer (açık nokta, madde 3(b)).
2. **İşlem kayıtları (3-c):** veriler üzerindeki her işlem güvenli biçimde kayda alınır;
   kayıtlarda hasta bilgisi yer almaz, yalnızca kimlik numaraları (CLAUDE.md değişmezi 6).
3. **Güncellemeler ve güvenlik testleri (3-ç, 3-d):** güvenlik güncellemeleri sürekli
   izlenir; bağımsız sızma testi en az yılda bir yaptırılır ve sonucu kayda geçer (açık
   nokta, madde 3(ç) ve 3(d)).
4. **Yazılım yetkilendirmesi (3-d):** verilere erişen her yazılımda kullanıcı
   yetkilendirmesi yapılır.
5. **Uzaktan erişim (3-e):** uzaktan erişimde en az iki kademeli kimlik doğrulama
   kullanılır. Hastanın kendi verisine erişiminde telefon kodu ile cihaza bağlı anahtarın
   bu şartı karşılayıp karşılamadığı hukuk danışmanının kararına bağlıdır (açık nokta
   `patient-factor-reading`).

## 7. Fiziksel ortam (Karar 2018/10, madde 4)

1. Verilerin bulunduğu veri merkezinde elektrik kaçağı, yangın, su baskını ve hırsızlığa
   karşı önlemlerin alındığı, sağlayıcının belgesi ile kayda geçer (4-a).
2. Veri merkezine ve hasta verisinin görüntülendiği her ofise yetkisiz giriş engellenir;
   kanıtı saklanır (4-b).
3. Hasta verisi ortak alanlarda ekranda açık bırakılmaz; ekranlar kullanılmadığında
   kilitlenir.

## 8. Aktarımlar (Karar 2018/10, madde 5)

1. E-posta, taşınabilir bellek ve kağıt ile aktarım `aktarim-kurallari.draft.md`
   kurallarına göre yapılır (5-a, 5-b, 5-ç).
2. Farklı fiziksel ortamlardaki sunucular arası aktarımın karşılıklı kimlik doğrulamalı
   TLS ile yapılmasının "VPN veya sFTP" şartını karşılayıp karşılamadığı hukuk
   danışmanının kararına bağlıdır (açık nokta `tls-versus-vpn-sftp`) (5-c).
3. Yurt dışına aktarım, Kanunun 9 uncu maddesine göre alınmış ve kayda geçmiş bir karar
   olmadan yapılmaz (`../sms-vendor-transfer-memo.draft.md`).

## 9. Kişisel Veri Güvenliği Rehberi (Karar 2018/10, madde 6)

Kurumun Kişisel Veri Güvenliği Rehberi'ndeki teknik ve idari tedbirler de dikkate alınır.
Rehber henüz bu depoda eşlenmemiştir (açık nokta `guide-not-read`); eşleme yapılana kadar
bu madde tamamlanmış sayılmaz.

## 10. Veri ihlali

Kurul Kararı 2019/10 uyarınca:

- İhlal, öğrenildiği andan itibaren gecikmeksizin ve en geç 72 saat içinde Kurula
  bildirilir; ilgili kişilere, belirlenmelerini müteakip makul olan en kısa süre içinde
  bildirim yapılır.
- Şirket veri işleyen olduğunda, ihlali gecikmeye yer vermeksizin veri sorumlusu
  hastaneye bildirir.
- İhlale ilişkin bilgiler, etkileri ve alınan önlemler kayıt altına alınır.
- Bir veri ihlali müdahale planı hazırlanır ve belirli aralıklarla gözden geçirilir
  (`docs/security/incident-runbook.md`; bildirim taslakları `../breach-notices/`).

## 11. Kayıt ve kanıt

Bu politikanın her maddesinin kanıtı (eğitim kayıtları, imzalı taahhütnameler, erişim
gözden geçirmeleri, test raporları, veri merkezi belgeleri) tarihli olarak
`docs/legal/special-category-measures.yaml` dosyasındaki ilgili maddeye bağlanır.

## 12. Gözden geçirme

Politika en az yılda bir ve mevzuatta, Kurul kararlarında veya sistemde önemli bir
değişiklik olduğunda gözden geçirilir.

## 13. Yürürlük ve onay

Politika, politika sahibinin onayı ile yürürlüğe girer.

Onaylayan: …………………… Unvan: …………………… Tarih: …………… İmza: ……………………

Hukuk danışmanı incelemesi: …………………… Tarih: ……………

## Ek — Kurul Kararı 2018/10 eşlemesi

| politika maddesi | 2018/10 önlemi | `special-category-measures.yaml` açık noktası |
|---|---|---|
| tüm belge | 1 | `policy-adopted` |
| 5.1 | 2(a) | `staff-training` |
| 5.2 | 2(b) | `confidentiality-undertakings`, `undertaking-text` |
| 5.3 | 2(c) | 2(c) açık noktaları |
| 5.4 | 2(ç) | 2(ç) açık noktaları |
| 5.5 | 2(d) | 2(d) açık noktaları |
| 6 | 3(a)–3(e) | 3(a)–3(e) açık noktaları, `patient-factor-reading` |
| 7 | 4(a), 4(b) | `hosting-environmental-controls`, `premises-access-control` |
| 8 | 5(a)–5(ç) | `staff-email-practice`, `removable-media-rule`, `tls-versus-vpn-sftp`, `plaintext-lan-feed`, `paper-handling-rule` |
| 9 | 6 | `guide-not-read` |

Kaynak: Kurul Kararı 2018/10, `docs/legal/sources/kvkk-2018-10/karar-2018-10.tr.txt`
(INT-215 tarafından 26.09.2026'da alınmış; önlem satırları
https://www.kvkk.gov.tr/Icerik/4110/2018-10 adresindeki metinle 27.09.2026'da yeniden
karşılaştırılmış ve aynı bulunmuştur). Kurul Kararı 2019/10:
https://www.kvkk.gov.tr/Icerik/5362/Veri-Ihlali-Bildirimi (27.09.2026).
