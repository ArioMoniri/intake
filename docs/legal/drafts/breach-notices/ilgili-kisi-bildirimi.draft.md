> TASLAK — hukuk danışmanı onayı gerektirir / DRAFT — requires counsel sign-off; not in force

# Veri ihlali — ilgili kişiye bildirim şablonları (taslak)

INT-214 için hazırlanmıştır. Şablonlar, Kurul Kararı 2019/271'in ilgili kişiye yapılacak
bildirimde aradığı asgari unsurları ve Kurul Kararı 2019/10'un bildirim yolunu izler.
Yayımlanacak metin değildir; hukuk danışmanı onaylayana kadar hiçbir olayda kullanılmaz.

## Kullanım kuralları

1. **Asgari içerik (2019/271).** Bildirim *"açık ve sade bir dille"* yapılır ve en az
   şunları içerir: ihlalin ne zaman gerçekleştiği; kişisel veri kategorileri bazında,
   kişisel veri ile özel nitelikli kişisel veri ayrılarak, hangi verilerin etkilendiği;
   olası sonuçları; olumsuz etkileri azaltmak için alınan veya alınması önerilen
   tedbirler; bilgi alınabilecek irtibat kişisinin adı ve iletişim bilgileri ya da web
   sayfasının tam adresi, çağrı merkezi gibi iletişim yolları. Aşağıdaki şablonların her
   biri bu beş başlığı taşır.
2. **Zaman ve yol (2019/10).** Bildirim, etkilenen kişiler belirlendikten sonra makul
   olan en kısa sürede yapılır: kişinin iletişim adresine ulaşılabiliyorsa doğrudan
   (Şablon A), ulaşılamıyorsa Şirketin web sitesinde yayımlanarak (Şablon B).
3. **Kim bildirir.** Şirketin veri sorumlusu olduğu hasta uygulamasında Şirket bildirir.
   Hastane kurulumlarında veri sorumlusu hastanedir; Şirket metni hazırlar ve hastaneye
   sunar, hastane kendi adına gönderir (Şablon D).
4. **Alanlar.** `{{...}}` ile gösterilen her alan olaya göre doldurulur. Bilinmeyen bir
   bilgi tahminle doldurulmaz; "henüz bilinmiyor" yazılır ve öğrenildiğinde ek bildirim
   yapılır.
5. **Başka kişinin verisi yazılmaz.** Bildirimde başka bir hastanın bilgisi, kişinin
   kendi sağlık yanıtlarının içeriği veya olayın teknik ayrıntısı yer almaz. Etkilenen
   bilgi, türüyle anlatılır ("sağlık yanıtlarınız" gibi).
6. **Dil.** B1 düzeyinde, "siz" diliyle, kısa cümlelerle yazılır. Korkutucu ifade
   kullanılmaz; olmayan bir tehlike küçümsenmez de.
7. **Kanıt.** Her bildirimin kime, ne zaman ve hangi yolla gönderildiği kaydedilir. Bu
   kayıt Kurula sunulur: Kurul Kararı 2025/2451'e göre Kurumun internet sitesindeki ihlal
   ilanı en fazla 60 gün sürer ve ilgili kişilere bildirim yapıldığı tevsik edilirse daha
   önce kaldırılır.

## Şablon A — Doğrudan bildirim (uygulama içi mesaj veya e-posta)

**Konu:** Kişisel verilerinizle ilgili bir güvenlik olayı

Sayın {{ad_soyad}},

Kişisel verilerinizi etkileyen bir güvenlik olayı yaşandı. Bu mesajda ne olduğunu, hangi
bilgilerinizin etkilendiğini ve neler yapabileceğinizi anlatıyoruz.

**Ne oldu, ne zaman oldu?**
{{ihlal_baslangic_tarihi}} ile {{ihlal_bitis_tarihi}} arasında {{olayin_sade_anlatimi}}.
Bu olayı {{tespit_tarihi}} tarihinde fark ettik.

**Hangi bilgileriniz etkilendi?**

- Kimlik ve iletişim bilgileriniz: {{etkilenen_kisisel_veri_kategorileri}}
- Sağlığınızla ilgili bilgiler gibi, kanunun özel olarak koruduğu bilgileriniz:
  {{etkilenen_ozel_nitelikli_veri_kategorileri}}

**Bunun sonucu ne olabilir?**
{{olasi_sonuclar}}

**Biz ne yaptık?**
{{alinan_tedbirler}}

**Siz ne yapabilirsiniz?**
{{onerilen_tedbirler}}

**Bilgi almak için**
Bu olayla ilgili sorularınızı {{irtibat_kisisi_adi}} ile {{irtibat_iletisim_bilgisi}}
üzerinden paylaşabilirsiniz. Güncel bilgiler şu sayfadadır: {{bilgi_sayfasinin_tam_adresi}}

Kişisel verilerinizle ilgili haklarınızı 6698 sayılı Kanunun 11 inci maddesine göre
kullanabilirsiniz. Başvuru yolu: {{basvuru_yolu}}

{{veri_sorumlusu_unvani}}
{{bildirim_tarihi}}

## Şablon B — Web sitesinde yayım (iletişim adresine ulaşılamayan kişiler için)

**Kişisel verileri etkileyen bir güvenlik olayı hakkında bilgilendirme**

{{veri_sorumlusu_unvani}} olarak, {{etkilenen_kisi_grubunun_tanimi}} kişisel verilerini
etkileyen bir güvenlik olayı yaşandığını bildiririz. Bu kişilerin bir bölümüne doğrudan
ulaşamadığımız için bu duyuruyu yayımlıyoruz.

**Ne oldu, ne zaman oldu?**
{{ihlal_baslangic_tarihi}} ile {{ihlal_bitis_tarihi}} arasında {{olayin_sade_anlatimi}}.
Olayı {{tespit_tarihi}} tarihinde fark ettik.

**Hangi bilgiler etkilendi?**

- Kimlik ve iletişim bilgileri: {{etkilenen_kisisel_veri_kategorileri}}
- Sağlıkla ilgili bilgiler gibi, kanunun özel olarak koruduğu bilgiler:
  {{etkilenen_ozel_nitelikli_veri_kategorileri}}

**Bunun sonucu ne olabilir?**
{{olasi_sonuclar}}

**Biz ne yaptık?**
{{alinan_tedbirler}}

**Ne yapabilirsiniz?**
{{onerilen_tedbirler}}

**Bilgi almak için**
{{irtibat_kisisi_adi}} — {{irtibat_iletisim_bilgisi}} — {{bilgi_sayfasinin_tam_adresi}}

Bu duyuru {{yayim_tarihi}} tarihinde yayımlanmıştır.

## Şablon C — Kısa haber (SMS veya anlık bildirim)

Kısa haber, Şablon A'nın yerine geçmez; yalnızca kişiyi Şablon A'ya yönlendirir. Kilit
ekranında görünebileceği için hiçbir sağlık bilgisi, uygulama içeriği veya olay ayrıntısı
taşımaz.

> Hesabınızla ilgili önemli bir güvenlik bildirimi var. Ayrıntılar: {{bilgi_sayfasinin_tam_adresi}}

## Şablon D — Hastane kurulumu (veri sorumlusu hastane)

Şablon A'nın metni kullanılır; şu farklarla:

- İmza ve `{{veri_sorumlusu_unvani}}` hastanenindir; bildirimi hastane gönderir.
- "Biz ne yaptık?" bölümü iki kısımdır: hastanenin aldığı tedbirler ve hastanenin hizmet
  aldığı yazılım sağlayıcısının (Şirket) aldığı tedbirler.
- İrtibat kişisi hastanenin belirlediği kişidir.

## Önerilen hazır cümleler (yalnızca olaya uyuyorsa kullanılır)

- `{{olasi_sonuclar}}`, iletişim bilgileri etkilendiğinde: "Bilgileriniz izinsiz
  kişilerin eline geçmiş olabilir. Bu bilgiler sizi dolandırmak amacıyla aranmanız veya
  mesaj almanız için kullanılabilir."
- `{{onerilen_tedbirler}}`: "Size gelen doğrulama kodunu kimseyle paylaşmayınız. Sizi
  arayıp sağlık bilgilerinizi veya kodunuzu soran kişilere bilgi vermeyiniz. Bu olayla
  ilgili şüpheli bir arama veya mesaj alırsanız bize bildiriniz."

## Kaynaklar

Tümü 27.09.2026'da alınmıştır.

- KVKK m.11, m.12(5): https://mgm.adalet.gov.tr/Resimler/SayfaDokuman/211020191355056698%20KVKK.pdf
- Kurul Kararı 2019/10: https://www.kvkk.gov.tr/Icerik/5362/Veri-Ihlali-Bildirimi
- Kurul Kararı 2019/271: https://www.kvkk.gov.tr/Icerik/5547/2019-271
- Kurul Kararı 2025/2451 (Kurum duyurusu): https://www.kvkk.gov.tr/Icerik/8595/kamuoyu-duyurusu
