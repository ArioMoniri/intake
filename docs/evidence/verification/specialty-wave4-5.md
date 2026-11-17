# Verification of the wave 4–5 specialty packs + kardiyoloji — awaiting-clinical-review

Reviewer: clinical-reviewer subagent, 2026-09-26. Every clinical item here is `awaiting-clinical-review`; passing this review is not a physician signature. No clinical value was authored by the reviewer.

## BLUF

- 179 slots reviewed (168 across the 13 generated packs, 11 in kardiyoloji). 73 REVISE: diyabet 7, endodonti 11, endokrinoloji 6, enfeksiyon 11, evde_saglik 7, fizyoterapi 7, gastroenteroloji_cerrahisi 7, goz 2, ic 2, kadin 4, KBB 2, ortopedi 2, uroloji 3, kardiyoloji 2. 26 of the 73 are the two fixed slots the generator writes into every pack.
- Three proposals parsed to 0 questions because their questions sit under `## 4.` while `## 3.` is the openEHR table.
- Breaches: 42 asks put more than one question in a turn (invariant 2); all generated packs say `maturity: L1` while HB-C1 is open, which makes them servable (invariant 13); the kadın LMP answer is free text (invariant 22); one endodonti ask contains an unsourced time threshold.
- Clean: nothing extends `base.life_threat`; no RED rules, no instruments, no digits, no `sen` forms.

## A. Findings

| where | finding | severity |
|---|---|---|
| every generated pack; gen_specialty_packs.py | `maturity: L1` with no physician sign-off; `taxonomy.py` treats any non-L0 pack as servable. HB-C1 (open) blocks promotion past L0. Headers name "Dr. A. Moniri" as physician of record; HB-C1 names Dr Efe Onganer. | BLOCKER |
| generator → every pack `sikayet_suresi` | ask and follow-up merged into one ask with two question marks (13 breaches) | HIGH |
| generator → every pack `basvuru_nedeni` | required slot without `follow_up_tr` (validator MISSING_FOLLOW_UP_TR; protocol tests only validate goldens) | HIGH |
| all packs `sorular` | 42 multi-question asks; 12 evade the PolicyGuard counter (`;`, "… mı ya da … mu?", when+how) | HIGH |
| 17 sentences | over the 15-word B1 limit | MEDIUM |
| generator | opaque `soru_N` string slots: no semantic id, no boolean/date type; `lmp_date`, `pregnancy_status`, `immunosuppression`, `anticoagulant_use` left unbound | HIGH |
| generator | `ask_if` conditions dropped (ortopedi soru_2–5, uroloji soru_2/8/9, kardiyoloji `efor_bayginlik`, diyabet soru_7 order) | MEDIUM |
| generator | slots carry neither `openehr_path` nor `openehr_deferred_reason` → compile refuses OPENEHR_BINDING_UNDECLARED (fails closed) | MEDIUM |
| endodonti soru_2 | "örneğin yarım dakika ya da daha uzun" — duration not in the source (AAE says only "lingering thermal pain") | HIGH |
| endodonti soru_7 | airway question narrowed to floor-of-mouth/neck swelling; RCEM says "any of" breathing difficulty or dysphagia | HIGH |
| kadın soru_1 | LMP captured as free string; must be `type: date` bound to `lmp_date` | HIGH |
| enfeksiyon soru_2 | "kaç gündür" asks for a number in a string slot | MEDIUM |
| enfeksiyon.md S1 | cites NICE NG51 (retired) → NG253/NG254/NG255 | MEDIUM |
| fizyoterapi soru_7 | CES item cites NG59 (excludes CES); use GIRFT March 2026 as ortopedi.md S1 does | MEDIUM |
| fizyoterapi soru_4, soru_6 | rely on S2 "UNVERIFIED VERBATIM" — hold | MEDIUM |
| gastroenteroloji_cerrahisi soru_2, soru_9a | proposal records NO SOURCE FOUND — hold | MEDIUM |
| diyabet soru_10 | refers back to low-sugar symptoms but cites a high-sugar quote; 16 words | MEDIUM |
| enfeksiyon soru_10; evde_saglik soru_1 | duplicate base slots (`immunosuppression`, `identity_check`/`subject_role`) | MEDIUM |
| endodonti soru_11 | "uyuşturucu" reads as narcotic → "diş uyuşturma iğnesi" | MEDIUM |
| evde_saglik | mixes self-address and third person; needs self/proxy variants keyed on base `subject_role` | LOW |
| generator `extract_questions` | takes the first `## 3.` whatever it contains; silent 0 | MEDIUM |
| compile/resolve.py | only `ask_one_tr` gets a compile-time one-question check; slot `ask_tr`/`follow_up_tr` get no one-question or B1-length check | MEDIUM |
| stub rule | well-formed: pending-value literal, `draft_needs_source`, never compiled | PASS |
| all packs | `extends` only `cluster.*`; nothing extends/removes `base.life_threat`; no instruments; no digits; no `sen` | PASS |

## B. Replacement texts

Fixed slots (all generated packs):
- **C1 `sikayet_suresi`**: ask "Bu şikâyetiniz ne zamandır var?" · follow-up "Gün ya da hafta olarak yaklaşık söyleyebilir misiniz?"
- **F1** follow-up for `basvuru_nedeni` asks ending "anlatır mısınız?": "Sizi hekime getiren en önemli şikâyetiniz nedir?"
- **F2** follow-up for asks ending "nedir?": "Bugünkü randevunuzun sebebini kısaca anlatır mısınız?"

Numbering: soru_N is proposal Q(N+1). "(a)/(b)" = split into two items; "if (a)" = `ask_if` on (a) being true.

### diyabet_poliklinigi
- Q1 → "Bugünkü görüşmede sizi en çok rahatsız eden konu nedir?"
- soru_1 → "Şikâyetiniz başladığından bu yana nasıl değişti?"
- soru_5 → "Son zamanlarda kendinizi alışılmadık şekilde halsiz ya da yorgun hissediyor musunuz?"
- soru_8 → "Çok susama ya da sık idrara çıkmayla birlikte bulantı, kusma veya karın ağrısı oluyor mu?" (optional extra item: "Son günlerde her zamankinden derin ve hızlı nefes aldığınızı fark ettiniz mi?")
- soru_9 → "Size daha önce şeker hastalığı (diyabet) tanısı konuldu mu?" (boolean) + duration item if yes: "Şeker hastalığı nedeniyle ne zamandır takip ediliyorsunuz?"
- soru_10 → "Şeker hastalığı için düzenli kullandığınız bir ilaç ya da insülin var mı?"
- soru_7 assumes known diabetes: ask after soru_9, gated on it.

### endodonti
- Q1 → "Bugünkü randevunuzda sizi hekime getiren asıl şikâyetiniz nedir?"
- soru_1 → "Bu şikâyetiniz başladığından bu yana nasıl değişti?"
- soru_2 → (a) "Sıcak ya da soğuk bir şey yiyip içtiğinizde dişiniz ağrıyor mu?" (b, if a) "Bu ağrı, yiyecek ya da içecek ağzınızdan gittikten sonra da sürüyor mu?" — unsourced "yarım dakika" dropped
- soru_3 → "Dişiniz hiçbir neden yokken kendiliğinden ağrıyor mu?"
- soru_5 → (a) "Dişinizin yanındaki diş etinde şişlik ya da sivilce gibi bir kabarcık var mı?" (b) "Ağzınıza kötü tadı olan bir akıntı geldiğini fark ettiniz mi?"
- soru_6 → (a) "Yüzünüzde ya da çenenizde şişlik var mı?" (b, if a) "Bu şişlikle birlikte ateşiniz de var mı?"
- soru_7 → "Nefes almakta ya da yutkunmakta zorlanıyor musunuz?"
- soru_8 → "Son zamanlarda ağzınızı açmakta zorlanıyor musunuz?"
- soru_10 → (a) "Şu anda düzenli kullandığınız ilaçlar var mı?" (b) "Bu diş için son günlerde antibiyotik kullanmaya başladınız mı?"
- soru_11 → "Herhangi bir ilaca, diş uyuşturma iğnesine ya da lateks eldivene alerjiniz var mı?"

### endokrinoloji_ve_metabolizma
- Q1 → "Bugünkü görüşmede sizi en çok rahatsız eden konu nedir?"
- soru_1 → "Şikâyetiniz başladığından bu yana nasıl değişti?"
- soru_6 → "Son zamanlarda kendinizi alışılmadık şekilde yorgun ya da halsiz hissediyor musunuz?"
- soru_8 → (a) "Böbrek üstü bezi yetmezliği ya da başka bir nedenle düzenli kortizon ilacı kullanıyor musunuz?" (b, if a) "Şu anda kusmanız ya da belirgin bir halsizliğiniz var mı?"
- soru_9 → "Aç kaldığınızda titreme, soğuk terleme, çarpıntı ya da kafa karışıklığı oluyor mu?" (fasting framing is a clinician decision)

### enfeksiyon_hastaliklari
- soru_1 → remove (duplicates `sikayet_suresi`)
- soru_2 → (a) "Son günlerde ateşiniz oldu mu?" (b, duration, if a) "Ateşiniz ne zamandır sürüyor?"
- soru_4 → "Son günlerde sizde kafa karışıklığı ya da aşırı uyku hâli oldu mu?"
- soru_5 → (a) "Son günlerde şiddetli bir baş ağrınız oldu mu?" (b) "Boynunuzu öne eğmekte zorlandığınız ya da ense sertliği hissettiğiniz oldu mu?"
- soru_6 → "Cildinizde, üzerine bastırınca solmayan kırmızı ya da mor bir döküntü fark ettiniz mi?"
- soru_7 → (a) "Şu anda ishaliniz var mı?" (b) "Dışkınızda gözle görülür kan fark ettiniz mi?"
- soru_9 → (a) "Son zamanlarda yurt dışına ya da başka bir şehre seyahat ettiniz mi?" (b) "Benzer şikâyeti olan biriyle yakın zamanda temasınız oldu mu?"
- soru_10 → "Size daha önce konulmuş uzun süreli bir hastalık tanısı var mı?" (immunosuppression left to the base slot, HB-C6)
- soru_11 → (a) "Şu anda düzenli kullandığınız ilaçlar var mı?" (b) "Son bir ay içinde antibiyotik kullandınız mı?"
- re-cite NG51 → NG253

### evde_saglik
- Q1 → "Bugünkü evde sağlık görüşmesinde en çok hangi konuda desteğe ihtiyacınız var?"
- soru_1 → remove (base `identity_check` covers it)
- soru_4 → "Hastanın uzun süre üzerinde yattığı ya da oturduğu yerlerde ciltte renk değişikliği var mı?"
- soru_5 → "Hastanın topuk, kalça ya da kuyruk sokumu gibi yerlerinde açık yara var mı?"
- soru_7 → (a) "Hasta son bir yıl içinde hiç düştü mü?" (b, if a) "Bu düşmelerin hangi durumlarda olduğunu anlatır mısınız?"
- soru_9 → "Hastanın evde bakımı yapılan bir yarası ya da yanığı var mı?"

### fizyoterapi
- Q1 → "Sizi bugün fizik tedaviye getiren en önemli şikâyetiniz nedir?"
- soru_1 → "Ağrınızı ya da rahatsızlığınızı en çok vücudunuzun hangi bölgesinde hissediyorsunuz?"
- soru_3 → "Son zamanlarda şikâyetinizde bir değişiklik ya da yeni bir belirti oldu mu?"
- soru_4 → "Sırt ya da bel ağrınız sizi geceleri uykudan uyandırıyor mu?" (hold until the NG234 verbatim is snapshotted)
- soru_7 → (a) "Son günlerde idrar yapmakta yeni bir zorluk ya da idrar kaçırma oldu mu?" (b) "Bacaklarınızın arasında ya da makat çevresinde yeni bir uyuşma fark ettiniz mi?" — source GIRFT March 2026
- soru_10 → (a) "Daha önce kas, kemik ya da eklemlerinizle ilgili bir tanı aldınız mı?" (b) "Daha önce kas, kemik ya da eklemlerinizden ameliyat oldunuz mu?"

### gastroenteroloji_cerrahisi
- soru_1 → remove (duplicate)
- soru_2 → (a) "Karnınızda şiddetli ya da geçmeyen bir ağrı var mı?" (b, if a) "Karnınıza dokunulunca ağrınız artıyor mu?" — unsourced: hold
- soru_9 → (a) "Son günlerde gaz ya da dışkı çıkaramadığınız oldu mu?" (unsourced: hold) (b) "Geçmeyen kusmanız var mı?" (S2)
- soru_10 → (a) "Daha önce mide, bağırsak ya da karaciğerinizle ilgili bir tanı aldınız mı?" (b) "Daha önce karnınızdan ameliyat oldunuz mu?"
- soru_11 → (a) "Şu anda düzenli kullandığınız ilaçlar var mı?" (b) "Ağrı kesici ya da kan sulandırıcı bir ilaç kullanıyor musunuz?"
- soru_4 re-cite to S2

### goz_hastaliklari · ic_hastaliklari · kulak_burun_bogaz_hastaliklari
- Only C1 + F1/F2. All other items PASS.

### kadin_hastaliklari_ve_dogum
- soru_1 → wording unchanged; `type: date`, bound to `lmp_date`
- soru_3 → (a) "Adet döneminiz dışında vajinal kanamanız oldu mu?" (b) "Hamileyseniz, bu hamilelikte hiç vajinal kanamanız oldu mu?"
- soru_2 → bind to `pregnancy_status`; gate the "Hamileyseniz," items on it

### ortopedi_ve_travmatoloji
- soru_2 … soru_5 → ask only if soru_1 is yes

### uroloji
- soru_9 → "Testis ağrınızla birlikte bulantı ya da kusma oldu mu?" — ask only if soru_8 is yes
- soru_2 → ask only if soru_1 is yes

## C. kardiyoloji (hand-authored pack)

- kardiyoloji.md Q1 → "Bugünkü görüşmede sizi en çok rahatsız eden konu nedir?"; Q3 → "Göğüs ağrınız olduğunda genellikle ne kadar sürüyor?"
- yaml `gogus_agrisi_suresi` follow-up → "Yaklaşık kaç dakika sürdüğünü söyleyebilir misiniz?" (the current either/or leaves a gap and primes the unsigned cut-off)
- yaml `efor_bayginlik` → ask only if `bayginlik` is yes
- The same two-question Q1 text also sits in diyabet_poliklinigi.md, endokrinoloji_ve_metabolizma.md, endodonti.md, evde_saglik.md and fizyoterapi.md.
- Source gaps (not authored): recurrence within an hour; syncope lying down; palpitations then syncope; family history of sudden death (export-blocked).

## D. The three unparsed proposals

beyin_ve_sinir_cerrahisi.md, el_cerrahisi.md, fiziksel_tip_ve_rehabilitasyon.md: questions are under `## 4. Candidate B1 Turkish pre-visit questions`; `## 3.` is the openEHR table. Q-item and quote shapes are correct. Fix: find the section by its title (generator) or renumber the headings. Before generating, fix: beyin Q2 (when+how; duplicates `sikayet_suresi`), Q6, Q9, Q11 (two questions each); el Q2 (when+how), Q5, Q6 (two each), Q7 (two, 19 words), Q8 (17 words), Q11 (23 words); fiziksel Q2 (two question marks), Q5 (comma-joined pair), Q6 (three questions), Q11 (two).

## E. Checklist

Instruments: none. Monotonicity: no removal or relaxation; nothing extends `base.life_threat`. RED axes: no RED rules. Sourcing: only the draft stub exists. Patient copy: `siz` throughout; jargon to explain: "cilt bütünlüğü", "kas–iskelet sistemi", "hidrokortizon", "uyuşturucu". Goldens: no rules, so no per-rule near-miss controls; the change process (`make safety`, CODEOWNER review) still applies.
