> TASLAK — hukuk danışmanı onayı gerektirir / DRAFT — requires counsel sign-off; not in force

<!--
Hazırlayanın notu (yayımlanacak metnin parçası değildir).

- Kaynak: docs/compliance/accessibility-conformance-report.md, değerlendirme tarihi
  27.09.2026. Bu taslak raporun söylemediği hiçbir şeyi söylemez. Rapor değişirse
  taslak da değişmelidir; tests/legal/test_legal_drafts.py, raporun tam
  desteklemediği her kuralın burada adıyla geçtiğini denetler.
- Sahibin doldurması gereken iki alan (geri bildirim adresi ve yanıt süresi) açıkça
  işaretlidir. Beyanın tarihi, son gözden geçirme tarihi ve imzalayan kişi bilerek
  yazılmamıştır; bunlar imza sırasında eklenir (README.md).
- BK numaraları raporun §0 açıklamasına göre türetilmiştir; Bakanlığın yayımladığı
  Kontrol Listesi ile karşılaştırılmadan kullanılmamalıdır.
- 2025/10 sayılı Genelge'nin Resmî Gazete metni görüntü olarak yayımlandığı için
  okunamamıştır; Genelge'ye ilişkin cümle, Bakanlığın kendi duyurusuna dayanır.
-->

# Vizite mobil uygulaması — Erişilebilirlik Beyanı

## 1. Bu beyan neyi kapsar

Bu beyan, Vizite mobil uygulamasının iPhone (iOS) ve Android sürümleri içindir.

Şunlar bu beyanın kapsamında değildir, çünkü henüz değerlendirilmemiştir:

- hekimlerin ve yöneticilerin kullandığı web uygulamaları,
- hastanede kullanılan kiosk modu (şu anda açılamamaktadır),
- acil durumlarda yönlendirme yapacak ekran (henüz uygulamada yoktur).

## 2. Uyum durumu

Vizite mobil uygulaması, Web İçeriği Erişilebilirlik Kılavuzu (WCAG) 2.2'nin A ve AA
düzeylerine **kısmen uyumludur**.

Bu şu anlama gelir: uygulamanın bazı bölümleri bu kurallara henüz uymamaktadır. Bazı
kurallar ise henüz gerçek bir telefonda denenmediği için değerlendirilmemiştir. Her
birini aşağıda ayrı ayrı yazdık.

## 3. Nasıl değerlendirdik

Değerlendirme 27 Eylül 2026'da yapılmıştır. Şu yöntemler kullanılmıştır:

- uygulamanın kaynak kodunu okuyan otomatik testler,
- tarihli ve kayıtlı el ile kod incelemeleri,
- yazı ile arka plan arasındaki renk farkının (kontrastın) hesaplanması.

Şunlar **henüz yapılmamıştır**:

- gerçek bir telefonda ekran okuyucu (VoiceOver, TalkBack) ile deneme,
- harici klavye, Switch Control veya sesle kontrol ile deneme,
- engelli kullanıcılarla deneme.

## 4. Bilinen sorunlar

Aşağıdaki kurallara uygulama henüz tam olarak uymamaktadır.

- **SC 1.4.3 — Kontrast (Asgari): kısmen uyumlu.** Bazı küçük açıklama yazılarının
  rengi, açık temada ve koyu temadaki yükseltilmiş yüzeylerde yeterince koyu değildir.
  Ölçülen renk farkı açık temada 3,11 : 1 ile 3,64 : 1 arasında, koyu temadaki
  yükseltilmiş yüzeyde 4,03 : 1'dir; gereken en az 4,5 : 1'dir. Açık temadaki
  "Dosyaya eklendi" etiketi de 4,35 : 1'de kalmaktadır.
- **SC 1.4.11 — Metin Dışı Kontrast: kısmen uyumlu.** Açık temada, seçilmemiş seçenek
  düğmelerinin kenar çizgisi çok açık renktedir (1,17 : 1 ile 1,25 : 1 arası; gereken
  3 : 1). Seçili düğmeler ve koyu temadaki düğmeler ayırt edilebilmektedir.
- **SC 3.1.1 — Sayfanın Dili (Kontrol Listesi BK24): kısmen uyumlu.** Android'de
  TalkBack, metni telefonun dilinde okur. Uygulamanın dili telefonun dilinden farklıysa
  Türkçe metin yabancı bir sesle okunabilir. iPhone'da her satır kendi dilini bildirir.
- **SC 3.1.2 — Bölümlerin Dili: kısmen uyumlu.** Uygulama İngilizce kullanıldığında
  Türkçe bölüm adları çevrilmeden gösterilir ve İngilizce sesle okunur.
- **EN 301 549 11.7 — Kullanıcı tercihleri: kısmen uyumlu.** Telefonun "kontrastı
  artır" ve "kalın metin" ayarları uygulamaya yansımaz. Renk teması, yazı boyutu ve
  hareketi azaltma ayarları yansır.
- **EN 301 549 12.1.1 — Erişilebilirlik özelliklerinin belgelenmesi: uyumlu değil.**
  Uygulamanın erişilebilirlik özelliklerini ve nasıl kullanıldıklarını anlatan bir
  kullanım belgesi henüz yoktur.

## 5. Henüz değerlendirilmeyen kurallar

Aşağıdaki kurallar ancak gerçek bir telefonda; ekran okuyucu, harici klavye ve en büyük
yazı boyutu ile denenerek değerlendirilebilir. Bu denemeler henüz yapılmamıştır. Bu
nedenle bu kurallara uyduğumuzu da uymadığımızı da söylemiyoruz.

- **SC 1.3.2 — Anlamlı Sıra (BK6):** ekran okuyucunun ekrandaki içeriği doğru sırayla
  okuyup okumadığı.
- **SC 1.4.10 — Yeniden Akış:** en büyük yazı boyutunda ve telefon yan çevrildiğinde
  içeriğin sığıp sığmadığı.
- **SC 2.1.1 — Klavye (BK10):** her düğmeye harici klavye veya Switch Control ile
  ulaşılıp ulaşılamadığı.
- **SC 2.1.2 — Klavye Tuzağı Olmaması (BK11):** klavye ile girilen bir bölümden
  çıkılabilip çıkılamadığı.
- **SC 2.4.2 — Sayfa Başlığı (BK17):** bir ekrana gelindiğinde başlığının okunup
  okunmadığı.
- **SC 2.4.3 — Odak Sırası (BK18):** odağın ekranda mantıklı bir sırayla ilerleyip
  ilerlemediği.
- **SC 2.4.7 — Görünür Odak:** klavye ile gezinirken odaklanılan düğmenin görünüp
  görünmediği.
- **SC 2.4.11 — Odağın Gizlenmemesi (Asgari):** odaklanılan bir düğmenin ekranın
  altındaki çubuğun arkasında kalıp kalmadığı.
- **SC 3.2.1 — Odaklanma (BK25):** bir düğmeye odaklanınca ekranın kendiliğinden değişip
  değişmediği.
- **SC 3.2.2 — Giriş (BK26):** doğrulama kodu yazılırken odağın bir sonraki kutuya
  geçmesinin ekran okuyucu kullanan biri için anlaşılır olup olmadığı.
- **EN 301 549 11.5.2.9, EN 301 549 11.5.2.13, EN 301 549 11.5.2.14,
  EN 301 549 11.5.2.15, EN 301 549 11.5.2.16 ve EN 301 549 11.5.2.17:** uygulamanın
  ekran okuyucuya hangi bilgileri, nasıl aktardığı.

Bu denemeler yapıldığında sonuçlar bu beyana işlenecektir.

## 6. Uygulamadaki erişilebilirlik ayarları

Bu özellikler uygulamanın kaynak kodunda tanımlıdır ve otomatik testlerle
denetlenmektedir. Gerçek bir telefonda henüz denenmemiştir.

- **Yazı boyutu.** Uygulama, telefonunuzun yazı boyutu ayarını izler. Yazıyı ayrıca
  Profilim › Görünüm bölümünden büyütebilirsiniz. Yazı en fazla iki katına kadar
  büyür.
- **Açık ve koyu tema.** Uygulama, telefonunuzun renk temasını izler. Temayı Profilim ›
  Görünüm bölümünden de değiştirebilirsiniz.
- **Hareket.** Telefonunuzda hareketi azaltmayı açtıysanız uygulama da hareketi azaltır.
  Profilim › Görünüm bölümündeki hareket anahtarı ile hareketi ayrıca azaltabilirsiniz.
- **Sesli yerine yazılı yanıt.** İlk sorudan önce, soruları sesli değil yazılı
  yanıtlamayı seçebilirsiniz.
- **Konuşan asistan.** Asistanın sorusu ekranda yazılı olarak da görünür. Konuşmayı
  durdurmak için konuşma balonuna dokunabilirsiniz.
- **Doğrulama kodu.** SMS ile gelen kodu kopyalayıp yapıştırabilir veya telefonunuzun
  önerdiği kodu seçebilirsiniz. Altı kutu birlikte dolar; kodu tek tek yazmanız
  gerekmez.

## 7. Geri bildirim

Uygulamada bir erişilebilirlik sorunu yaşarsanız bize yazınız. Sorunun hangi ekranda
olduğunu ve hangi yardımcı teknolojiyi (örneğin ekran okuyucu) kullandığınızı yazmanız
sorunu çözmemizi kolaylaştırır. Bu yazıda sağlık bilgilerinizi paylaşmanız gerekmez.

- **Geri bildirim adresi:** [sahibi tarafından doldurulacak]
- **Yanıt süresi:** [sahibi tarafından doldurulacak]

## 8. Yasal çerçeve

5378 sayılı Engelliler Hakkında Kanunun 7 nci maddesi şöyle der: "Bilgilendirme
hizmetleri ile bilgi ve iletişim teknolojisinin engelliler için erişilebilir olması
sağlanır."

Web siteleri ve mobil uygulamaların erişilebilirliği, 2025/10 sayılı Cumhurbaşkanlığı
Genelgesi ile düzenlenmiştir. Genelge ile Aile ve Sosyal Hizmetler Bakanlığı bünyesinde,
erişilebilirliği izlemek üzere Web Siteleri ve Mobil Uygulamaların Erişilebilirliği
İzleme Komisyonu kurulmuştur.
