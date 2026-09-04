# Acıbadem: fetching a completed previsit

**Audience:** the Acıbadem integration engineer, working on the host that runs the
INTAKE demo API (shell access to the GPU server / the demo box).
**What this does:** returns one patient's finished previsit as JSON, keyed by the
hospital's own patient number, in the same structure every time.

There is exactly one call.

---

## The endpoint

```
POST /v1/previsit-output/fetch
```

- The patient number goes in the **request body**, never in the URL or a query
  string. A direct identifier in a URL lands in every access log, `Referer`
  header, browser history entry and proxy trace; the body keeps it out of all of
  them (INTAKE invariant 6). There is **no** `/…/{patient_number}` path — a test
  enforces that no route on this surface carries the number in a path.
- The number is echoed back in the response so you can join without re-sending
  it; INTAKE stores it in no column anywhere (it is resolved to an internal
  pseudonym through a tokenizer at request time).

## Authentication

Send the **admin bearer credential** in the `Authorization` header:

```
Authorization: Bearer <INTAKE_DEV_TOKEN_ADMIN>
```

> **Honest limitation (HB-A18, not yet built).** A hospital integration engine
> should present a dedicated **machine-to-machine** principal. That principal
> does not exist yet. For the demo the read-back therefore reuses the admin dev
> bearer token (`require_admin`) — the same door the clinic console uses. It
> authenticates the *clinic tenant*, and the fetch only ever returns that
> tenant's own patients. Treat the token as a secret; it is not a long-lived
> production credential.

## curl (run from the host, against the local API)

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/previsit-output/fetch \
  -H "Authorization: Bearer ${INTAKE_DEV_TOKEN_ADMIN}" \
  -H "Content-Type: application/json" \
  -d '{"patient_number":"42099176"}'
```

`42099176` is the demo patient (Harvey Specter). Substitute the hospital patient
number you want.

## The response you get back

`200 OK`, `application/json`. The `output` object is the frozen previsit; its
`schema_version` is the field you branch on. Shape:

```json
{
  "patient_number": "42099176",
  "output_ref": "previsit_output:<uuid>",
  "output": {
    "schema_version": "intake.clinical.previsit_output.v1",
    "visit_ref": "<uuid>",
    "completed_at": "2026-09-04T12:24:06.904619Z",
    "locale": "tr",
    "protocol_id": "previsit.dev.visit",
    "protocol_version": "int197-dev",
    "proxy_reported": false,
    "third_party_present": false,
    "sections": [
      { "id": "chief_complaint", "title_tr": "Başvuru nedeni", "lines": ["Göğüs ağrısı"] },
      { "id": "hpi",            "title_tr": "Şikâyet öyküsü",  "lines": ["Dünden beri devam eden göğüs ağrısı.", "…"] },
      { "id": "medications",    "title_tr": "Kullandığı ilaçlar", "lines": ["Metoprolol 50 mg", "…"] }
    ],
    "measurements": [],
    "triage": { "source": "not_evaluated", "reason": "rules_engine_not_on_this_path" },
    "llm_candidates": []
  }
}
```

Field notes:

- **`output_ref`** — a stable id for the disclosed previsit. It is the same
  reference written to INTAKE's disclosure audit log for this fetch, so your
  record and ours name the same event.
- **`sections`** — only the sections the patient chose to share when they sent
  the previsit. Section ids (`chief_complaint` / `hpi` / `medications`) are the
  join keys; `lines` are verbatim Turkish (invariant 5).
- **`triage`** — for this slice it is always
  `{"source":"not_evaluated","reason":"rules_engine_not_on_this_path"}`. **This
  is deliberate and must not be read as "no problem found."** A RED/YELLOW
  determination in INTAKE comes only from the rules engine, which does not run on
  this note path; the document says so explicitly rather than omitting the field
  (which would read as GREEN). Never infer a severity from `llm_candidates`.
- **`measurements`** — a number and its unit are always one atom here; the list
  is empty on this path.

## Responses other than 200

The read-back fails **closed** at every step, and each answer is a flat
`{"error": …}` object that never leaks patient data:

| HTTP | body | meaning |
|------|------|---------|
| `401` | (unauthenticated) | no / bad bearer token |
| `403` | `{"error":"forbidden"}` | the token is not the clinic/admin credential |
| `403` | `{"error":"consent_required","scope":"share:previsit_output"}` | the patient has not consented to sharing the previsit to a hospital system, or that consent was withdrawn or its text changed |
| `404` | `{"error":"not_found"}` | unknown patient number, **or** no finished previsit, **or** the patient took it back to draft. The distinction is intentionally not disclosed |
| `422` | `{"error":"validation_error",…}` | the patient number is malformed (the rejected value is never echoed) |
| `503` | `{"error":"previsit_output_recipient_unregistered"}` | this tenant has no approved reader row (see prerequisites) |
| `503` | `{"error":"previsit_output_unconfigured"}` | no tokenization key configured on the API |

A successful fetch is a **share** of clinical data, so it is only ever answered
after (1) the tenant has an approved reader row, (2) the patient's
`share:previsit_output` consent stands, and (3) the previsit is still sent (a
live share). All three are checked per patient, per call, and the disclosure is
audited before the body is returned.

---

## Prerequisites (one-time, for whoever runs the demo API)

1. **The API must serve this route.** Start (or restart) the API from a build
   that includes the previsit-output router — `POST /v1/previsit-output/fetch`
   must appear in `GET /openapi.json`.
2. **Register the reader.** Start the API with the demo recipient overlay:

   ```bash
   INTAKE_PREVISIT_OUTPUT_RECIPIENTS=infra/previsit_output/recipients.demo.yaml
   ```

   The shipped `infra/previsit_output/recipients.yaml` is intentionally empty
   (fail-closed); the overlay adds one clearly demo-tier row for the demo tenant.
   It names **no real DPA, approval or retention clause** — those are a
   human/legal decision (HB-A18), not something the demo invents.
3. **The row must be produced by the serving API process.** In `file-dev` KEK
   mode the envelope key lives in memory per process, so a previsit is
   decryptable only by the same API instance that wrote it. In practice: the
   previsit that a fetch returns is the one the patient completed through *this*
   running API.

---

## Türkçe özet

Acıbadem, tamamlanmış bir ön-değerlendirmeyi tek bir çağrıyla alır:

- **Uç nokta:** `POST /v1/previsit-output/fetch`
- **Hasta numarası GÖVDEDE gönderilir**, URL'de değil (kayıtlarda iz bırakmamak
  için — invariant 6): `{"patient_number":"42099176"}`.
- **Kimlik doğrulama:** admin taşıyıcı jetonu (`Authorization: Bearer …`).
  Gerçek makineden-makineye kimlik henüz yok (HB-A18); demo bu nedenle admin
  geliştirme jetonunu kullanır.
- **Yanıt:** hastanın paylaştığı bölümleri içeren, `schema_version` ile
  sürümlenmiş JSON belge. `triage` alanı `not_evaluated`'dır — bu "sorun yok"
  anlamına GELMEZ; RED/SARI yalnızca kural motorundan gelir ve bu akışta
  çalışmaz.
- Her çağrı bir **paylaşımdır**: onay (`share:previsit_output`) ve denetim kaydı
  zorunludur; başarısızlıkta sistem **kapalı** tarafta kalır (503/403/404).

Örnek:

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/previsit-output/fetch \
  -H "Authorization: Bearer ${INTAKE_DEV_TOKEN_ADMIN}" \
  -H "Content-Type: application/json" \
  -d '{"patient_number":"42099176"}'
```
