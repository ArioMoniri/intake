> TASLAK — hukuk danışmanı onayı gerektirir / DRAFT — requires counsel sign-off; not in force

# Veri ihlali — veri işleyenden hastaneye (veri sorumlusuna) bildirim şablonu (taslak)

INT-214 için hazırlanmıştır. Şirketin veri işleyen olduğu hastane kurulumlarında,
Şirket nezdinde yaşanan bir ihlali hastaneye bildirmek içindir. Yayımlanacak metin
değildir; hukuk danışmanı onaylayana ve hastane ile veri işleme sözleşmesi
imzalanana kadar kullanılmaz.

## Neden bu biçimde

- **Süre.** Kurul Kararı 2019/10: veri işleyen, ihlali *"herhangi bir gecikmeye yer
  vermeksizin"* veri sorumlusuna bildirir. files/06 §5'teki sözleşme hükmü taslağı bu
  süreyi 24 saat olarak önerir; bağlayıcı süre, imzalanan sözleşmedeki süredir.
- **Hastanenin 72 saati.** Kurul Kararı 2019/10'a göre veri sorumlusu, ihlali öğrendiği
  tarihten itibaren en geç 72 saat içinde Kurula bildirir. Kurumun Bildirim Formu
  Kılavuzu (bölüm 3.2), *"Veri işleyenin veri sorumlusuna bildirdiği tarih, veri
  sorumlusunun veri ihlalinden haberdar olma tarihini ifade eder"* der. Yani hastanenin
  süresi bu bildirimle başlar; bu nedenle bildirim, hastanenin kendi formunu hemen
  doldurabileceği sırayla, Kurumun formundaki başlıklarla düzenlenmiştir.
- **Aşamalı bildirim.** Kurul Kararı 2019/10, bilgilerin aynı anda sağlanamadığı
  hallerde gecikmeye mahal verilmeksizin aşamalı olarak sağlanmasını kabul eder. İlk
  bildirim bilinenlerle hemen gönderilir; eksikler ek bildirimle tamamlanır.
- **Hasta bilgisi yok.** Bu yazıda hiçbir hastanın adı, kimlik numarası veya sağlık
  bilgisi yer almaz (CLAUDE.md değişmezi 6). Etkilenen kişilerin listesi gerekiyorsa
  yalnızca kimlik numaraları ile, ayrı ve şifreli olarak, aktarım kurallarına göre
  iletilir.
- **Şirketin kendi Kurul bildirimi.** Şirketin veri sorumlusu olduğu hasta uygulamasında
  aynı başlıklar, Şirketin Kurul formunu doldurmak için iç çalışma kağıdı olarak kullanılır.

## Şablon

**Kime:** {{hastane_unvani}} — {{hastane_irtibat_kisisi}}
**Kimden:** {{sirket_unvani}} (veri işleyen) — {{sirket_irtibat_kisisi}}, {{sirket_iletisim_bilgisi}}
**Sözleşme:** {{veri_isleme_sozlesmesi_tarihi_ve_no}}
**Bildirim türü:** {{ilk_bildirim_veya_ek_bildirim}} — Olay kayıt no: {{olay_kayit_no}}
**Bu bildirimin tarihi ve saati:** {{bildirim_tarihi_saati}}

### 1. İhlal hakkında

| başlık | bilgi |
|---|---|
| İhlalin başlama tarihi | {{ihlal_baslangic_tarihi}} |
| İhlalin sona erme tarihi | {{ihlal_bitis_tarihi_veya_devam_ediyor}} |
| Şirketin ihlali tespit ettiği tarih ve saat | {{sirket_tespit_tarihi_saati}} |
| Bu bildirimin hastaneye iletildiği tarih ve saat | {{bildirim_tarihi_saati}} |
| İhlalin kaynağı | {{kaynak}} (ör. siber saldırı, yetkisiz erişim, kayıp veya çalınan cihaz, personel hatası, diğer) |
| Nasıl gerçekleşti | {{nasil_gerceklesti}} |
| Etkisi | {{gizlilik_butunluk_erisilebilirlik}} (verinin gizliliği, bütünlüğü, erişilebilirliği; birden fazlası olabilir) |
| Nasıl ve kim tarafından tespit edildi | {{nasil_ve_kim_tespit_etti}} |

### 2. Etkilenen veriler ve kişiler

| başlık | bilgi |
|---|---|
| Etkilenen kişisel veri kategorileri | {{kisisel_veri_kategorileri}} |
| Etkilenen özel nitelikli kişisel veri kategorileri | {{ozel_nitelikli_veri_kategorileri}} |
| Etkilenen kişi sayısı | {{kisi_sayisi_veya_neden_bilinmedigi}} |
| Etkilenen kayıt sayısı | {{kayit_sayisi_veya_neden_bilinmedigi}} |
| Etkilenen ilgili kişi grupları | {{ilgili_kisi_gruplari}} (ör. hastalar, hasta yakınları, hekimler) |
| İlgili kişiler üzerindeki muhtemel etkiler | {{muhtemel_etkiler}} |

Kayıt sayısı, Kurumun Kılavuzundaki yönteme göre hesaplanır: bir kişinin ihlale uğrayan
her veri türü ayrı bir kayıttır.

### 3. İlgili kişilere bildirim

İlgili kişilere bildirim, veri sorumlusu olarak hastanenin kararıdır. Şirket, hastanenin
talimatı olmadan ilgili kişilere bildirim yapmaz. Şirketin önerdiği metin ektedir
(`ilgili-kisi-bildirimi.draft.md`, Şablon D).

### 4. Olası sonuçlar

Şirketin değerlendirmesi: {{sirketin_olasi_sonuc_degerlendirmesi}}
Bu değerlendirme hastanenin kendi değerlendirmesinin yerine geçmez.

### 5. Önlemler

| başlık | bilgi |
|---|---|
| İhlalden önce alınmış teknik ve idari tedbirler | {{ihlal_oncesi_tedbirler}} |
| İhlalden sonra alınan teknik ve idari tedbirler | {{ihlal_sonrasi_tedbirler}} |
| İlgili çalışanların son bir yıl içinde aldığı KVKK eğitimleri | {{son_bir_yil_egitimleri}} |

### 6. Diğer kurumlara bildirim

| başlık | bilgi |
|---|---|
| Türkiye'deki yargı, kolluk veya diğer kamu kurumlarına bilgi verildi mi / verilecek mi | {{yurt_ici_kurumlar}} |
| Yurt dışındaki kurumlara bilgi verildi mi / verilecek mi | {{yurt_disi_kurumlar}} |

### 7. Şirketin yardım taahhüdü

Şirket, hastanenin Kurula ve ilgili kişilere bildirim yükümlülüğünü yerine
getirebilmesi için: sorulara gecikmeksizin yanıt verir; olayla ilgili kayıtları (hasta
bilgisi içermeden, kimlik numaraları ile) sunar; ek bilgi öğrendikçe ek bildirim yapar;
hastanenin talimatlarına uyar.

### 8. Ekler

{{ekler_listesi}} (ör. olay zaman çizelgesi, tespit kaydı, alınan tedbirlerin kanıtı)

{{sirket_yetkilisi_adi_unvani}} — {{imza}}

## Kaynaklar

Tümü 27.09.2026'da alınmıştır.

- KVKK m.12(2), m.12(5): https://mgm.adalet.gov.tr/Resimler/SayfaDokuman/211020191355056698%20KVKK.pdf
- Kurul Kararı 2019/10: https://www.kvkk.gov.tr/Icerik/5362/Veri-Ihlali-Bildirimi
- Kişisel Veri İhlali Bildirim Formu Kılavuzu (bölüm 3.1–3.6): https://kvkk.gov.tr/SharedFolderServer/CMSFiles/4e601093-24a4-4507-893f-edfa0081695c.pdf

Alınamayan kaynaklar: 7545 sayılı Siber Güvenlik Kanunu ve USOM bildirim biçimi bu
taslak için okunmadı; siber olay bildirimi `docs/security/incident-runbook.md`
yönlendirmesine bırakılmıştır.
