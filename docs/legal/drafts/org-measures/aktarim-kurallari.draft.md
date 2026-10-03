> TASLAK — hukuk danışmanı onayı gerektirir / DRAFT — requires counsel sign-off; not in force

# E-posta, Taşınabilir Bellek ve Kağıt ile Aktarım Kuralları (taslak)

Kurul Kararı 2018/10, madde 5, özel nitelikli kişisel verilerin aktarımında alınacak
önlemleri sayar. Yazılım, bu verileri e-posta ile göndermez
(`docs/legal/special-category-measures.yaml`, madde 5(a), kontrol
`no-software-email-path`); bu kurallar **insanların** yaptığı aktarımlar içindir
(INT-364; açık noktalar `staff-email-practice`, `removable-media-rule`,
`paper-handling-rule`).

## 0. Temel kural

Hastanın sağlık bilgisi, hastanın uygulamada verdiği paylaşım izni (share) dışında hiçbir
yolla gönderilmez. Aşağıdaki yollar yalnızca bu mümkün olmadığında ve güvenlik
sorumlusunun yazılı onayıyla kullanılır. Her kullanım kayda geçer: kim, ne zaman, hangi
veri kategorisi, kime, hangi onayla.

## 1. E-posta (Karar 2018/10, madde 5(a))

Kararın metni: *"Verilerin e-posta yoluyla aktarılması gerekiyorsa şifreli olarak
kurumsal e-posta adresiyle veya Kayıtlı Elektronik Posta (KEP) hesabı kullanılarak
aktarılması"*.

1. Yalnızca Şirketin kurumsal e-posta hesabı veya Şirketin KEP hesabı kullanılır.
   Kişisel e-posta hesabı, anlık mesajlaşma uygulaması ve bulut paylaşım bağlantısı
   kullanılmaz.
2. Kurumsal e-posta ile gönderimde veri şifrelenir: şifreli e-posta ya da şifreli bir ek
   kullanılır; ekin parolası e-postadan ayrı bir kanalla iletilir.
3. Konu satırına hasta adı, kimlik numarası veya sağlık bilgisi yazılmaz.
4. Alıcı adresi gönderimden önce kontrol edilir. Yanlış kişiye giden bir e-posta veri
   ihlali şüphesidir ve hemen bildirilir.
5. Gerekenden fazla veri gönderilmez.

## 2. Taşınabilir bellek, CD, DVD (Karar 2018/10, madde 5(b))

Kararın metni: *"Taşınabilir Bellek, CD, DVD gibi ortamlar yoluyla aktarılması
gerekiyorsa kriptografik yöntemlerle şifrelenmesi ve kriptografik anahtarın farklı
ortamda tutulması"*.

1. Varsayılan olarak kullanılmaz.
2. Kullanılması gerekirse: güvenlik sorumlusunun yazılı onayı alınır; ortam şifrelenir
   (tam disk veya şifreli kapsayıcı); parola veya anahtar ortamla birlikte değil, farklı
   bir ortamda ve farklı bir kanalla iletilir.
3. Ortam bir envanter kaydına işlenir; teslim alan kişi imza verir.
4. İş bitince veri güvenli biçimde silinir veya ortam imha edilir; bu da kayda geçer.
5. Kaybolan veya çalınan bir ortam veri ihlali şüphesidir ve hemen bildirilir.

## 3. Kağıt (Karar 2018/10, madde 5(ç))

Kararın metni: *"Verilerin kağıt ortamı yoluyla aktarımı gerekiyorsa evrakın çalınması,
kaybolması ya da yetkisiz kişiler tarafından görülmesi gibi risklere karşı gerekli
önlemlerin alınması ve evrakın “gizlilik dereceli belgeler” formatında gönderilmesi
gerekir."*

1. Hasta verisi içeren çıktı, gerekmedikçe alınmaz; alınırsa yalnızca gereken bilgiyi
   içerir.
2. Belge "gizlilik dereceli belge" olarak işaretlenir. İşaretin biçimi hukuk danışmanının
   kararına bağlıdır (README.md). Bu taslağın önerisi: her sayfanın üst ve alt kısmında
   "GİZLİ — KİŞİSEL SAĞLIK VERİSİ İÇERİR" ibaresi.
3. Gönderim çift zarfla yapılır: iç zarf kapalı ve "GİZLİ" işaretli, dış zarfta yalnızca
   alıcı adresi. Elden teslimde tutanak, postada iadeli taahhüt kullanılır.
4. Belge masada, yazıcıda veya ortak alanda bırakılmaz.
5. İhtiyaç kalmayan belge çapraz kesen kağıt imha makinesiyle imha edilir; imha kayda
   geçer.
6. Sağlık hizmeti sunucuları için Kişisel Sağlık Verileri Hakkında Yönetmelik m.5(5),
   basılı materyal üzerinde kısmi kimliksizleştirme veya maskeleme tedbirleri öngörür. Bu
   taslak, Şirket bakımından da aynı yaklaşımı önerir: çıktıda hastanın tam kimliği
   yerine gerekmedikçe kısaltılmış bir tanımlayıcı kullanılır.

## 4. Sunucular arası aktarım (Karar 2018/10, madde 5(c))

Bu bir personel kuralı değildir; teknik karşılığı `special-category-measures.yaml`
dosyasında madde 5(c) altındadır. Karşılıklı kimlik doğrulamalı TLS'in "VPN veya sFTP"
şartını karşılayıp karşılamadığı ve şifresiz yerel ağ beslemesinin hiç kabul edilip
edilemeyeceği hukuk danışmanının kararına bağlıdır (açık noktalar
`tls-versus-vpn-sftp`, `plaintext-lan-feed`).

## 5. Karar 2018/10 eşlemesi

| bölüm | 2018/10 önlemi | açık nokta |
|---|---|---|
| 0, 1 | 5(a) | `staff-email-practice` |
| 0, 2 | 5(b) | `removable-media-rule` |
| 0, 3 | 5(ç) | `paper-handling-rule` |
| 4 | 5(c) | `tls-versus-vpn-sftp`, `plaintext-lan-feed` |

## 6. Kaynaklar

- Kurul Kararı 2018/10: `docs/legal/sources/kvkk-2018-10/karar-2018-10.tr.txt`; önlem
  satırları https://www.kvkk.gov.tr/Icerik/4110/2018-10 ile 27.09.2026'da karşılaştırıldı.
- Kişisel Sağlık Verileri Hakkında Yönetmelik m.5(5), RG 21.06.2019, sayı 30808:
  https://www.resmigazete.gov.tr/eskiler/2019/06/20190621-3.htm (27.09.2026).
- Alınamayan kaynak: "gizlilik dereceli belge" biçimini düzenleyen bir mevzuat metni
  aranmadı ve okunmadı; bu nedenle işaret biçimi yalnızca öneridir.
