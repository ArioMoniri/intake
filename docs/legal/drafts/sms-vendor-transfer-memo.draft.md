> TASLAK — hukuk danışmanı onayı gerektirir / DRAFT — requires counsel sign-off; not in force

# SMS one-time codes through a US vendor: the KVKK Art. 9 options (draft memo)

Prepared 2026-09-27 by a drafting agent for Turkish counsel (KVKK) and the owner,
for **INT-358** (GitHub #576). It lays out the routes the amended law allows and what
each one costs. It is not legal advice. It picks no vendor and signs nothing: the
owner decides and counsel confirms. Every legal quotation below was read from the
source named beside it on the retrieval date stated in §9.

## 1 · The question

INT-329 built an SMS adapter for the sign-in one-time code, pointed at Twilio's
Messages API in the United States. Before any real phone number leaves Türkiye, the
owner must record the vendor, its DPA and the KVKK Art. 9 mechanism, with a decision
id (INT-358 acceptance). This memo sets out the mechanisms and an in-country
alternative, and ends with a checklist the owner signs.

## 2 · What the software sends today (repository facts)

| fact | where it is stated |
|---|---|
| Each sign-in sends one HTTPS request to `api.twilio.com`, carrying `To` (the patient's phone number in E.164 form), `From` (a sender number or Messaging Service id) and `Body` | `services/api/src/intake_api/otp_twilio.py` |
| The body is fixed: "Doğrulama kodunuz: {code}. Bu kodu kimseyle paylaşmayınız." It names no app, clinic or health matter | `otp_twilio.py`, `SMS_TEMPLATE` |
| The call is declared `EgressPurpose.SMS_OTP_DELIVERY` with `DataClass.PHI`, the strictest class, because a phone number used to sign up for a clinical intake says the person is a patient | `otp_twilio.py` module docstring |
| The shipped egress allow-list has no row for this purpose, so the tier answers 503 outside dev and no number leaves | `otp_twilio.py`; INT-358 status |
| Credentials come only from OpenBao (`secret/api/twilio`), written by the operator | `otp_twilio.py`; INT-358 acceptance |
| The vendor's own response echoes the number and the body; the adapter logs neither | `otp_twilio.py` |

So the personal data crossing the border is: the phone number, the one-time code,
the fixed message text, the sender identity, and the vendor's delivery metadata
(message id, status, timestamps) that the vendor keeps on its side.

## 3 · The law, as retrieved

**It is a transfer abroad.** The transfer regulation (RG 10.07.2024, sayı 32598)
m.4(1)(e) defines it as personal data *"yurt dışındaki bir veri sorumlusu veya veri
işleyene iletilmesi ya da başka bir suretle erişilebilir hâle getirilmesi"*. Posting
the number to a US API is that.

**Two conditions, both needed.** KVKK m.9, as replaced by Law 7499 MADDE 34 (in force
01.06.2024 under MADDE 40), and regulation m.6(1) require (i) one of the grounds in
m.5 or m.6 for the processing itself, and (ii) one of three routes:

1. **Adequacy decision** (m.9(1)–(3); regulation m.8–9). The drafter found none for
   the United States on kvkk.gov.tr on 2026-09-27. That is a negative search result,
   not a certificate; counsel confirms.
2. **Appropriate safeguards** (m.9(4); regulation m.10), available only *"ilgili
   kişinin aktarımın yapılacağı ülkede de haklarını kullanma ve etkili kanun yollarına
   başvurma imkânının bulunması kaydıyla"*: an agreement between public bodies, binding
   corporate rules, **the Board's standard contract**, or a written undertaking with
   the Board's permission.
3. **Occasional transfers** (m.9(6); regulation m.16), available only *"arızi olmak
   kaydıyla"*. Regulation m.16(1): *"Düzenli olmayan, tek veya birkaç sefer
   gerçekleşen, süreklilik arz etmeyen ve olağan faaliyet akışı içinde bulunmayan
   aktarımlar arızi niteliktedir."*

**The standard contract, in the regulation's words** (m.14): it must be used
*"üzerinde herhangi bir değişiklik yapılmaksızın"*; if concluded in a foreign language
too, *"Türkçe metin esas alınır"*; it must be signed by the parties or persons
authorised to represent them; and *"imzaların tamamlanmasından itibaren beş iş günü
içinde fiziki olarak veya kayıtlı elektronik posta (KEP) adresi ya da Kurul
tarafından belirlenen diğer yöntemlerle Kuruma bildirilir"*. The notice carries proof
of the signatories' authority and a notarised translation of every foreign-language
document (m.14(6)). A change of party or content, or termination, is notified the same
way (m.14(8)). The Board added an online route, the *Standart Sözleşme Bildirim
Modülü* (decision 2024/1793, announced by the Kurum).

**The sanction for a missed notice.** KVKK m.18(1)(d), added by Law 7499 MADDE 35:
*"9 uncu maddenin beşinci fıkrasında öngörülen bildirim yükümlülüğünü yerine
getirmeyenler hakkında 50.000 Türk lirasından 1.000.000 Türk lirasına kadar"*, and it
applies to controllers and processors alike. These are the figures as enacted;
counsel confirms the amounts in force today.

**The Kurum's list of defects it finds in notified contracts** (public notice, see
§9): both parties sign the Turkish text (in a two-column contract, the Turkish
column); signatures meet the Türk Borçlar Kanunu rules; both parties date their
signatures; addresses, contact points and signatory names are stated; foreign
official documents carry an apostille; no back-dated "yürürlük tarihi"; and only the
optional or alternative clauses may be changed.

## 4 · Step one: the ground for the processing itself

This comes before Art. 9 and does not depend on the vendor.

- **Proposal:** KVKK m.5(2)(c), *"Bir sözleşmenin kurulması veya ifasıyla doğrudan
  doğruya ilgili olması kaydıyla, sözleşmenin taraflarına ait kişisel verilerin
  işlenmesinin gerekli olması"*: the code is how the patient signs in to the service
  they asked for.
- **Counsel decision:** is a phone number sent to sign in to a health intake app
  health data under m.6(1), given the context the adapter itself assumes
  (`DataClass.PHI`)? If yes, m.5(2)(c) is not available and the ground is m.6(3)(a)
  açık rıza, which cannot be a condition of the service; the sign-in path would then
  need a non-SMS alternative.

## 5 · Step two: the Art. 9 route for a US vendor

| route | available for OTP delivery? | why |
|---|---|---|
| adequacy | not today, on the drafter's search | no US decision located (counsel confirms) |
| standard contract | **yes, if the vendor signs the Board's text unchanged** | the only practical safeguard for a vendor contract |
| binding corporate rules | no | only within one corporate group, with Board approval |
| written undertaking | possible but slow | needs the Board's permission before the first transfer (regulation m.15(3)) |
| occasional transfer, including açık rıza | **no** | every sign-in sends a code; that is regular and in the ordinary course, which regulation m.16(1) excludes |

### 5.1 Which standard contract

The Board published four texts (index: kvkk.gov.tr, *Standart Sözleşmeler*).

- **Consumer tenants (INTAKE is controller):** Standard Contract **2**, *veri
  sorumlusundan veri işleyene*.
- **Hospital tenants (INTAKE is processor):** if a hospital's patient signs in
  through the same code path, INTAKE passes the hospital's data to a sub-processor
  abroad, which is Standard Contract **3**, *veri işleyenden veri işleyene*, on the
  hospital's instruction (regulation m.5(1), m.7). Regulation m.7(3) lets the
  processor file the notice without waiting for the controller's instruction.
- **Counsel decision:** one contract or both, and whether hospital DPAs must
  pre-authorise the SMS sub-processor.

### 5.2 What the signed contract must contain

The Board's text is fixed; the parties fill the annexes and pick the optional
clauses. From Standard Contract 2 as retrieved:

- **Ek I — Aktarımın detayları.** The Board's headings, with the drafter's proposed
  content for counsel to accept or change:
  - *Veri aktaranın faaliyetleri:* operating a patient pre-visit intake app and its
    sign-in.
  - *Veri alıcısının faaliyetleri:* delivering one SMS per request to the number given.
  - *İlgili kişi grupları:* people signing in to the app (patients, and guardians
    where the minor rules apply).
  - *Aktarılan kişisel veri kategorileri:* phone number; one-time code; fixed message
    text; sender identity; delivery metadata.
  - *Özel nitelikli kişisel veri kategorileri:* none intended; depends on the §4
    decision.
  - *Aktarımın hukuki sebebi:* the §4 ground.
  - *Aktarım sıklığı:* continuous, one message per sign-in request.
  - *İşleme faaliyetinin niteliği ve amaçları:* transmission to the mobile network for
    delivery; no other use.
  - *Saklama süresi:* the shortest the vendor offers for message bodies and logs. The
    owner obtains the vendor's figure in writing; this memo does not state one.
  - *(Alt) veri işleyene aktarımlar:* the vendor's sub-processors and the delivering
    carriers, as the vendor lists them.
  - *Alıcılar:* as above.
  - *VERBİS bilgileri:* INTAKE's registration, or the 2025/1572 exception if counsel
    rules INTAKE falls within it (see the data-categories draft).
- **Ek II — Teknik ve idari tedbirler,** with the extra measures for special-category
  data if §4 decides the number is health data.
- **Ek III — Alt veri işleyenler listesi.**
- **Madde 8 option** (sub-processors): specific prior authorisation or general
  authorisation with notice, with a notice period the parties write in.
- **Madde 16 option:** which party notifies the Kurum. The regulation's default, if
  the contract is silent, is the transferring party.
- Clauses that are fixed and matter here: prompt breach notice by the recipient on
  the Board's breach form (7.6(c)); return or deletion at the end, with proof (7.4);
  audit on request (7.9); the recipient's warranty that no national law or practice
  conflicts with the contract, and prompt notice if that changes (13); prompt notice
  of any request or direct access by an authority (14); Turkish law and courts (17–18).
- **Counsel decision:** whether a US vendor can truthfully give the Madde 13
  warranty, and what the owner should ask it to confirm first.

### 5.3 Steps, in order

1. Owner asks the vendor, in writing, whether it will sign Standard Contract 2 (and 3)
   **unchanged, in Turkish**, and obtains its sub-processor list and message-log
   retention.
2. Counsel reviews the filled annexes and the chosen options.
3. Both parties sign the Turkish text, each dating its signature, by authorised
   signatories (Kurum notice).
4. **Within five business days of the last signature**, notify the Kurum by the
   module, KEP or in person, attaching proof of authority, notarised Turkish
   translations and any apostilles.
5. Update the aydınlatma texts before the first real transfer: KVKK m.10(1)(c) and
   Aydınlatma Tebliği m.5(1)(ı) require the recipient groups and the purpose of the
   transfer to be named.
6. Only then add the egress allow-list row (INT-358 acceptance), citing the decision
   id; the operator writes the credentials to OpenBao on each host.
7. Put the re-notification triggers in a calendar: new party, changed annex, new
   sub-processor (Ek III and Ek I updated and notified), termination.

## 6 · The in-country alternative

An SMS provider that holds the number, the message and every log, backup and support
access inside Türkiye makes **no transfer abroad**, so Art. 9 and the standard
contract do not apply. What remains is an ordinary processor relationship: a written
agreement under KVKK m.12(2), which makes INTAKE and the provider jointly responsible
for the security measures, and a processor that notifies INTAKE without delay of a
breach (Board decision 2019/10).

This holds only if nothing is reachable from abroad: regulation m.4(1)(e) counts data
made *"erişilebilir"* abroad as transferred, so a foreign parent company's support
access, a foreign cloud backup or a foreign log pipeline brings Art. 9 back.

It also fits the repository's own posture: files/06 §1 (G2019-12 row) keeps
public-hospital tenants' health data in Türkiye with no foreign-provider cloud on the
PHI path, and the adapter already classes this call as PHI.

Checklist for an in-country provider: written confirmation that data, backups, logs
and support access stay in Türkiye; sub-processor list; message-log retention; breach
notice without delay; deletion on termination with proof; audit right; the provider's
authorisation to offer SMS services in Türkiye (the drafter did not retrieve the BTK
rules and states nothing about them).

## 7 · Comparison

| | US vendor + standard contract | in-country provider |
|---|---|---|
| Art. 9 transfer | yes | no, if nothing is reachable from abroad |
| Paperwork | Board text unchanged, annexes, notice in 5 business days, re-notice on change | processor agreement under m.12(2) |
| Standing risk | Madde 13 warranty; missed-notice fine under m.18(1)(d) | the provider's own residency holding true |
| Public-hospital tenants | conflicts with files/06 G2019-12 posture | consistent |

**The drafter's recommendation, for counsel to accept or reject:** an in-country
provider for all tenants, with the US route kept only if no in-country provider meets
the checklist in §6.

## 8 · Owner's checklist (to sign)

Decision id: …………………… Date: ……………………

- [ ] SMS vendor chosen: …………………… (legal name, country)
- [ ] Route: in-country (no Art. 9 transfer) / standard contract type …… / other: ……
- [ ] Ground for the processing (§4), as counsel confirmed: ……………………
- [ ] Vendor's written answers received: residency, sub-processors, message-log retention
- [ ] If standard contract: Board text unchanged; Ek I, II, III filled; options chosen
- [ ] If standard contract: signed in Turkish by authorised signatories, each signature dated
- [ ] If standard contract: notified to the Kurum on …………… by module / KEP / in person (within five business days of ……………); receipt filed at ……………
- [ ] Processor agreement (m.12(2)) signed on ……………
- [ ] Aydınlatma texts name the recipient and purpose before the first real transfer
- [ ] Egress allow-list row added by PR …… citing this decision id
- [ ] Operator wrote the credentials to OpenBao on each host; nothing committed
- [ ] Re-notification triggers diarised (party, annex, sub-processor, termination)

Owner: …………………… Signature: …………………… Counsel reviewed: …………………… Date: ……………

## 9 · Sources

Retrieved 2026-09-27.

- KVKK 6698, m.3, 5, 10, 12 (text as enacted): https://mgm.adalet.gov.tr/Resimler/SayfaDokuman/211020191355056698%20KVKK.pdf
- Law 7499, MADDE 34 (m.9), MADDE 35 (m.18), MADDE 40 (in force), RG 12.03.2024, sayı 32487: https://www.resmigazete.gov.tr/eskiler/2024/03/20240312-1.htm
- Kişisel Verilerin Yurt Dışına Aktarılmasına İlişkin Usul ve Esaslar Hakkında Yönetmelik, RG 10.07.2024, sayı 32598: https://www.resmigazete.gov.tr/eskiler/2024/07/20240710-2.htm
- Standard contracts index: https://www.kvkk.gov.tr/Icerik/7929/Standart-Sozlesmeler — Standard Contract 2: https://www.kvkk.gov.tr/SharedFolderServer/CMSFiles/b531d656-9cea-4cdb-84ce-1ab92198c9b1.pdf — Standard Contract 3 (title page read): https://www.kvkk.gov.tr/SharedFolderServer/CMSFiles/f2840ffa-4fcb-404f-ae01-573afb37ae85.pdf
- Kurum notice on defects in notified standard contracts: https://www.kvkk.gov.tr/Icerik/8170/Yurt-Disina-Kisisel-Veri-Aktariminda-Kullanilacak-Standart-Sozlesmelerde-Dikkat-Edilmesi-Gereken-Hususlara-Iliskin-Kamuoyu-Duyurusu
- Kurum notice on the notification module (Board decision 2024/1793): https://www.kvkk.gov.tr/Icerik/8043/Standart-Sozlesme-Bildirim-Modulu-Hakkinda-Kamuoyu-Duyurusu
- Board decision 2019/10 (processor's breach notice to the controller): https://www.kvkk.gov.tr/Icerik/5362/Veri-Ihlali-Bildirimi
- Aydınlatma Tebliği m.5, RG 10.03.2018, sayı 30356: https://www.resmigazete.gov.tr/eskiler/2018/03/20180310-5.htm

**Not retrieved, and so not relied on:** any Board adequacy decision (none found); the
vendor's own DPA, sub-processor list and retention terms; the BTK rules on SMS
providers and sender identities; the Kurum's *Kişisel Verilerin Yurt Dışına
Aktarılması Rehberi*.
