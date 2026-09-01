# HBYS intake field schema — owner-supplied source

Provenance: supplied by the repository owner on 2026-09-02. It is a Turkish
hospital information system's own intake field set — the field ids (`346_LS`,
`1353_LM`, `td382`, …) are that system's, not ours.

Committed VERBATIM and never edited, so any mapping built against it can be
checked against what was actually supplied. Two uses:

1. **Base-layer question source** — the universal, non-department things a
   Turkish intake asks. INT-282 records the split between what a PATIENT can
   answer and what only a clinician or a lab can supply; a large part of this
   file is the latter and must never become a patient question.
2. **Mapping target** — these ids are what a connector would write to, so they
   belong with the connector work (INT-163) rather than being re-derived later.

NOTHING here is a clinical threshold or authority for one. The option lists are
that vendor's vocabulary, not a validated instrument.

---

const FIXED_SCHEMA = [
    // ── Genel ──
    { id: 'complaintdefination', label: 'Yakınma', section: 'Genel', type: 'textarea' },
    { id: 'calcDate', label: 'Yakınma Başlangıç Zamanı', section: 'Genel', type: 'number' },
    { id: 'chkTime', label: 'Zaman Birimi (Gün/Hafta/Ay/Yıl)', section: 'Genel', type: 'radio', options: [{ text: 'Gün', value: 'G' }, { text: 'Hafta', value: 'W' }, { text: 'Ay', value: 'M' }, { text: 'Yıl', value: 'Y' }] },
    { id: '9900_TC', label: 'Öykü', section: 'Genel', type: 'textarea' },
    { id: '327_TC', label: 'Özgeçmiş Notu', section: 'Genel', type: 'text' },

    // ── Alerji ──
    { id: '346_LS', label: 'Alerjisi var mı?', section: 'Alerji', type: 'radio', options: [{ text: 'Var', value: '1' }, { text: 'Yok', value: '2' }] },
    { id: '1353_LM', label: 'Alerji Türleri', section: 'Alerji', type: 'checkbox', options: [{ text: 'İlaç', value: '9' }, { text: 'Yiyecek', value: '8' }, { text: 'Polen', value: '1' }, { text: 'Mold', value: '2' }, { text: 'Pet Dander', value: '3' }, { text: 'Toz', value: '4' }, { text: 'İnsekt', value: '5' }, { text: 'Mücevherat', value: '6' }, { text: 'Kozmetik', value: '7' }, { text: 'Metal', value: '10' }, { text: 'Latex', value: '11' }, { text: 'Diğer', value: '999' }] },
    { id: '346_TC', label: 'Alerji Notu', section: 'Alerji', type: 'text' },

    // ── Kronik Hastalıklar ──
    { id: '442Kronik', label: 'Hipertansiyon', section: 'Kronik', type: 'checkbox' },
    { id: '443Kronik', label: 'Kalp-damar hastalıkları', section: 'Kronik', type: 'checkbox' },
    { id: '444Kronik', label: 'Kanser', section: 'Kronik', type: 'checkbox' },
    { id: '445Kronik', label: 'Diabetes Mellitus', section: 'Kronik', type: 'checkbox' },
    { id: '446Kronik', label: 'Kan Hastalıkları', section: 'Kronik', type: 'checkbox' },
    { id: '447Kronik', label: 'Kronik Böbrek Hastalığı', section: 'Kronik', type: 'checkbox' },
    { id: '20110Kronik', label: 'Kronik Diğer', section: 'Kronik', type: 'checkbox' },
    { id: '20110_CC_D', label: 'Kronik Diğer Notu', section: 'Kronik', type: 'text' },

    // ── Sosyal (Sigara, Alkol, Madde) ──
    { id: '361_LS', label: 'Sigara Kullanımı', section: 'Sosyal', type: 'radio', options: [{ text: 'Hiç kullanmamış', value: '1' }, { text: 'Eski kullanıcı / bıraktı', value: '2' }, { text: 'Hergün düzenli içiyor', value: '3' }, { text: 'Ara sıra içiyor', value: '4' }, { text: 'Belirtilmedi', value: '5' }] },
    { id: '361_TC', label: 'Sigara Notu', section: 'Sosyal', type: 'text' },
    { id: '363_LS', label: 'Alkol Kullanımı', section: 'Sosyal', type: 'radio', options: [{ text: 'Hayır', value: '1' }, { text: 'Evet', value: '2' }, { text: 'Belirtilmedi', value: '9' }] },
    { id: '363_TC', label: 'Alkol Notu', section: 'Sosyal', type: 'text' },
    { id: '476_LS', label: 'Madde Kullanımı', section: 'Sosyal', type: 'radio', options: [{ text: 'Hayır', value: '1' }, { text: 'Evet', value: '2' }, { text: 'Belirtilmedi', value: '3' }] },
    { id: '476_TC', label: 'Madde Notu', section: 'Sosyal', type: 'text' },
    { id: '353_TC', label: 'Sosyal Durum Notu', section: 'Sosyal', type: 'text' },

    // ── Geçmiş (Ameliyat, Yaralanma) ──
    { id: '323_LS', label: 'Ameliyat Geçmişi', section: 'Geçmiş', type: 'radio', options: [{ text: 'Var', value: '0' }, { text: 'Yok', value: '1' }, { text: 'Belirtilmedi', value: '2' }] },
    { id: '323_TC', label: 'Geçmiş Ameliyat Notu', section: 'Geçmiş', type: 'text' },
    { id: '1351_LS', label: 'Yaralanma Geçmişi', section: 'Geçmiş', type: 'radio', options: [{ text: 'Var', value: '0' }, { text: 'Yok', value: '1' }, { text: 'Belirtilmedi', value: '2' }] },
    { id: '1351_TC', label: 'Yaralanma Notu', section: 'Geçmiş', type: 'text' },

    // ── İlaçlar ──
    { id: '1355_TC', label: 'Sürekli kullandığı ilaçlar', section: 'İlaçlar', type: 'text' },

    // ── Kan ──
    { id: 'spnbloodgroup', label: 'Kan Grubu (Lab)', section: 'Kan', type: 'text', readonly: true },
    { id: '8997_LS', label: 'Beyan edilen kan grubu', section: 'Kan', type: 'radio', options: [{ text: 'AB Rh Pozitif', value: '1' }, { text: 'AB Rh Negatif', value: '2' }, { text: 'A Rh Pozitif', value: '3' }, { text: 'A Rh Negatif', value: '4' }, { text: 'B Rh Pozitif', value: '5' }, { text: 'B Rh Negatif', value: '6' }, { text: '0 Rh Pozitif', value: '7' }, { text: '0 Rh Negatif', value: '8' }, { text: 'Bilinmiyor', value: '9' }] },
    { id: '324_CC', label: 'Kan ve Kan Transfüzyonu', section: 'Kan', type: 'radio', options: [{ text: 'Evet', value: '1' }, { text: 'Hayır', value: '0' }] },

    // ── Engellilik ──
    { id: '1352_LS', label: 'Engellilik Durumu', section: 'Kişisel', type: 'radio', options: [{ text: 'Yok', value: '1' }, { text: 'Bedensel engelli', value: '2' }, { text: 'Zihinsel engelli', value: '3' }, { text: 'Görme engelli', value: '4' }, { text: 'İşitme engelli', value: '5' }, { text: 'Diğer', value: '8' }, { text: 'Belirtilmedi', value: '9' }] },

    // ── Soygeçmiş ──
    { id: '352_TC', label: 'Soygeçmiş Notu', section: 'Soygeçmiş', type: 'text' },
    { id: 'td382', label: 'Soygeçmiş Anne Hipertansiyon (HT)', section: 'Soygeçmiş', type: 'checkbox' },
    { id: 'td386', label: 'Soygeçmiş Anne Kalp Hastalığı (KAH)', section: 'Soygeçmiş', type: 'checkbox' },
    { id: 'td390', label: 'Soygeçmiş Anne Kanser (Ca)', section: 'Soygeçmiş', type: 'checkbox' },
    { id: 'td394', label: 'Soygeçmiş Anne Diyabet (DM)', section: 'Soygeçmiş', type: 'checkbox' },
    { id: 'td398', label: 'Soygeçmiş Anne Kan Hastalığı', section: 'Soygeçmiş', type: 'checkbox' },
    { id: '402_TC', label: 'Soygeçmiş Anne Diğer Notlar', section: 'Soygeçmiş', type: 'text' },
    { id: 'td383', label: 'Soygeçmiş Baba Hipertansiyon (HT)', section: 'Soygeçmiş', type: 'checkbox' },
    { id: 'td387', label: 'Soygeçmiş Baba Kalp Hastalığı (KAH)', section: 'Soygeçmiş', type: 'checkbox' },
    { id: 'td391', label: 'Soygeçmiş Baba Kanser (Ca)', section: 'Soygeçmiş', type: 'checkbox' },
    { id: 'td395', label: 'Soygeçmiş Baba Diyabet (DM)', section: 'Soygeçmiş', type: 'checkbox' },
    { id: 'td399', label: 'Soygeçmiş Baba Kan Hastalığı', section: 'Soygeçmiş', type: 'checkbox' },
    { id: '403_TC', label: 'Soygeçmiş Baba Diğer Notlar', section: 'Soygeçmiş', type: 'text' },
    { id: 'td384', label: 'Soygeçmiş Erkek Kardeş Hipertansiyon (HT)', section: 'Soygeçmiş', type: 'checkbox' },
    { id: 'td388', label: 'Soygeçmiş Erkek Kardeş Kalp Hastalığı (KAH)', section: 'Soygeçmiş', type: 'checkbox' },
    { id: 'td392', label: 'Soygeçmiş Erkek Kardeş Kanser (Ca)', section: 'Soygeçmiş', type: 'checkbox' },
    { id: 'td396', label: 'Soygeçmiş Erkek Kardeş Diyabet (DM)', section: 'Soygeçmiş', type: 'checkbox' },
    { id: 'td400', label: 'Soygeçmiş Erkek Kardeş Kan Hastalığı', section: 'Soygeçmiş', type: 'checkbox' },
    { id: '404_TC', label: 'Soygeçmiş Erkek Kardeş Diğer Notlar', section: 'Soygeçmiş', type: 'text' },
    { id: 'td385', label: 'Soygeçmiş Kız Kardeş Hipertansiyon (HT)', section: 'Soygeçmiş', type: 'checkbox' },
    { id: 'td389', label: 'Soygeçmiş Kız Kardeş Kalp Hastalığı (KAH)', section: 'Soygeçmiş', type: 'checkbox' },
    { id: 'td393', label: 'Soygeçmiş Kız Kardeş Kanser (Ca)', section: 'Soygeçmiş', type: 'checkbox' },
    { id: 'td397', label: 'Soygeçmiş Kız Kardeş Diyabet (DM)', section: 'Soygeçmiş', type: 'checkbox' },
    { id: 'td401', label: 'Soygeçmiş Kız Kardeş Kan Hastalığı', section: 'Soygeçmiş', type: 'checkbox' },
    { id: '405_TC', label: 'Soygeçmiş Kız Kardeş Diğer Notlar', section: 'Soygeçmiş', type: 'text' },

    // ── Kişisel ──
    { id: '449_TC', label: 'Meslek', section: 'Kişisel', type: 'text' },

    // ── Fiziksel / Vital ──
    { id: '281008_LS', label: 'Düşme riski var mı?', section: 'Fiziksel', type: 'radio', options: [{ text: 'Evet', value: '1' }, { text: 'Hayır', value: '2' }] },
    { id: '49_TC', label: 'Solunum sayısı', section: 'Fiziksel', type: 'text' },
    { id: '174_TC', label: 'Nabız/dk.', section: 'Fiziksel', type: 'text' },
    { id: '4328_LS', label: 'Nabız Ritim', section: 'Fiziksel', type: 'radio', options: [{ text: 'Ritmik', value: '1' }, { text: 'Aritmik', value: '2' }] },
    { id: '173_TC', label: 'KB-S(mmHg)', section: 'Fiziksel', type: 'text' },
    { id: '354_TC', label: 'KB-D(mmHg)', section: 'Fiziksel', type: 'text' },

    // ── Ağrı ──
    { id: '633_LS', label: 'Ağrısı var mı?', section: 'Ağrı', type: 'radio', options: [{ text: 'Evet', value: '1' }, { text: 'Hayır', value: '2' }] },
    { id: '4229_LS', label: 'Ağrı Skoru', section: 'Ağrı', type: 'radio', options: [{ text: '0', value: '0' }, { text: '1', value: '1' }, { text: '2', value: '2' }, { text: '3', value: '3' }, { text: '4', value: '4' }, { text: '5', value: '5' }, { text: '6', value: '6' }, { text: '7', value: '7' }, { text: '8', value: '8' }, { text: '9', value: '9' }, { text: '10', value: '10' }] },
    { id: '4232_LS', label: 'Sıklık (Ağrı)', section: 'Ağrı', type: 'radio', options: [{ text: 'Aralıklı', value: '1' }, { text: 'Sürekli', value: '2' }] },
    { id: '4231_LM', label: 'Yer (Ağrı)', section: 'Ağrı', type: 'checkbox', options: [{ text: 'Ameliyat yeri', value: '1' }, { text: 'Baş', value: '2' }, { text: 'Boyun', value: '3' }, { text: 'Sırt', value: '4' }, { text: 'Göğüs', value: '5' }, { text: 'Bel', value: '6' }, { text: 'Karın', value: '7' }, { text: 'Sağ Kol', value: '8' }, { text: 'Sol Kol', value: '9' }, { text: 'Sağ Bacak', value: '10' }, { text: 'Sol Bacak', value: '11' }, { text: 'Tüm Vücut', value: '12' }, { text: 'Diğer', value: '999' }] },
    { id: '4233_LM', label: 'Nitelik (Ağrı)', section: 'Ağrı', type: 'checkbox', options: [{ text: 'Künt', value: '1' }, { text: 'Yanıcı', value: '2' }, { text: 'Batıcı', value: '3' }, { text: 'Derin', value: '4' }, { text: 'Keskin', value: '5' }, { text: 'Yayılan', value: '6' }, { text: 'Hassasiyet', value: '7' }, { text: 'Dolgunluk', value: '8' }, { text: 'Zonklayıcı', value: '9' }, { text: 'Saplanıcı', value: '10' }, { text: 'Sıkıştırıcı', value: '11' }, { text: 'Diğer', value: '999' }] },

    // ── Boy / Kilo / Diyabet ──
    { id: '51_TC', label: 'Boy (cm)', section: 'Fiziksel', type: 'text' },
    { id: '209_TC', label: 'Kilo', section: 'Fiziksel', type: 'text' },
    { id: '6000040_LS', label: 'Kilo Birimi', section: 'Fiziksel', type: 'radio', options: [{ text: 'kg', value: '1' }, { text: 'gr', value: '2' }] },
    { id: '6000110_LS', label: 'Diyabeti var mı?', section: 'Fiziksel', type: 'radio', options: [{ text: 'Evet', value: '2' }, { text: 'Hayır', value: '1' }] },

    // ── Muayene / Tedavi ──
    { id: '337_TC', label: 'Muayene Notu', section: 'Muayene', type: 'textarea' },
    { id: '349_TC', label: 'Tedavi Notu', section: 'Tedavi', type: 'textarea' }
];