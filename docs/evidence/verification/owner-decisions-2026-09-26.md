# Owner decisions — 2026-09-26

The repository owner gave these answers to the coordinator directly in the session, through the in-session question tool, on 2026-09-26. Each is recorded verbatim in substance, with the option the owner chose.

| # | question | owner's choice |
|---|---|---|
| D1 | Replacement for the withdrawn `minio/minio` image (INT-347) | "pgsty/minio fork": digest-pinned, AGPL-3.0 identical to upstream (PR #554) |
| D2 | INT-301 RTL wiring versus INT-253's release gate | "Remove RTL code until P3 audit": the gate stays unchanged (PR #548) |
| D3 | Specialty questions that would collect new sensitive-data categories | "Approve them now": data-inventory rows to be added; counsel review still to follow |
| D4 | Merging PRs after the auto-mode classifier refused an unreviewed merge | "Let me merge after green checks": the coordinator merges in order once checks pass, apart from failures already on `main` (owner added `Bash(gh pr merge:*)`) |
| D5 | AWS host for the backend | Owner granted AWS deploy permission and added `Bash(aws ec2/ssm/s3/s3api:*)`. When g6.2xlarge had no capacity, the owner asked to check other regions and said the deployment should be stress-tested under production conditions rather than labelled synthetic. |

## D3: what the approval covers, and what it does not

**Approved for inclusion in the review-queue candidates:**
- forensic / personal safety (adli_tip);
- genital and sexual-health symptoms (deri);
- non-alcohol substance use (ruh sağlığı, klinik psikoloji);
- household basic needs and household contacts (sosyal pediatri, halk sağlığı, nükleer tıp);
- relatives' family health history and consanguinity (tıbbi genetik, onkoloji, pediatri, immünoloji, nefroloji, hematoloji, metabolizma, gastroenteroloji);
- partner fertility data (üreme endokrinolojisi, tıbbi genetik);
- employer / occupational exposure and report purpose (iş ve meslek hastalıkları, sağlık kurulu);
- reading and learning difficulty (hemşirelik eğitim, sosyal pediatri).

**Delivery.** Each such item is `delivery: text_first` (files/13 §13).

**Still held for reasons other than data category:**
- adli_tip Q4 (companion invitation), because it conflicts with the IFAS advice to see the patient alone. This is a clinician and legal decision.
- Every item held for a missing or unverified source.

**Not decided by D3.** These stay open under INT-349 and must close before any candidate is promoted to L1:

1. **Storage today.** Every specialty answer lands in the generic `slots.value` column. Its inventory annotation (`packages/intake_platform/src/intake_platform/db/models.py`, the `Slot` model) is:
   - category: `special_category_health`;
   - basis: KVKK m.6 açık rıza per consent scope;
   - retention: life of the record, patient-deletable, 30-day grace, then crypto-shred;
   - recipients: tenant clinicians via a consented share.

   No per-category or per-question register exists.
2. **Encryption.** `slots.sensitivity` selects plaintext or envelope encryption, but the only writer (`services/api/src/intake_api/store.py`) writes `PLAIN`. Sensitive categories must be stored encrypted before any of these questions is served.
3. **Counsel must decide, per category:**
   - the KVKK m.6 basis;
   - a separate basis and notice where another person is the data subject (relatives, partner, household members);
   - retention, recipients, the VERBİS entry (INT-211) and the consent scope.

   No legal basis is assumed here.
4. **Slot tagging.** The protocol `Slot` model needs a data-category tag, so the column-level schema test can see which slots carry which category.

## D5: production conditions and patient data

Deploying with production configuration and stress-testing it under production conditions (`INTAKE_ENV=prod`, every dev refusal on, real TLS) does not change where real patient data may live. HB-I5 and invariant 19 keep the PHI path in-country, and AWS has no region in Turkey. Real patients therefore need an in-country host, or counsel's recorded cross-border decision (HB-L11), before any real patient's data reaches the AWS deployment.
