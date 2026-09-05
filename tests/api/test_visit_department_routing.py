"""INT-323 — department-dynamic previsit routing wired to visit creation.

The INT-197 mirror path carries a free-text ``department`` and, by default,
derives no branch (a patient's pre-taxonomy local visit — pinned unchanged in
test_visits.py). INT-323 adds an inbound-source opt-in: a connector / MHRS
bridge that carries only a department asks the server to MAP it onto the
branch taxonomy, so the previsit becomes department-dynamic.

Fail closed is the whole point: a department the taxonomy cannot map keeps its
free-text label and derives NO branch — never a silent wrong specialty — and a
department that maps to Acil Tıp is refused exactly as the branch path refuses
it. The branch → served-pack step (invariant 13) stays with the runtime; the
pack CONTENT is HB-C1-gated.
"""

from __future__ import annotations

from api_harness import ApiHarness


def test_default_mirror_path_still_derives_no_branch(harness: ApiHarness) -> None:
    # Without the opt-in, a mappable free-text department is left exactly as the
    # INT-197 contract has it: honest free text, no branch, no type.
    body = {"hospital": "Hastane", "department": "Kardiyoloji", "date": "2026-09-03"}
    response = harness.client.post("/v1/visits", json=body, headers=harness.patient())
    assert response.status_code == 201, response.text
    out = response.json()
    assert out["department"] == "Kardiyoloji"
    assert out["branch_id"] is None


def test_inbound_opt_in_maps_department_to_branch(harness: ApiHarness) -> None:
    body = {
        "hospital": "Hastane",
        "department": "Kardiyoloji",
        "resolve_department": True,
        "date": "2026-09-03",
    }
    response = harness.client.post("/v1/visits", json=body, headers=harness.patient())
    assert response.status_code == 201, response.text
    out = response.json()
    # invariant 5: the tr label is the taxonomy's own name_tr, verbatim.
    assert out["branch_id"] == "kardiyoloji"
    assert out["department"] == "Kardiyoloji"


def test_inbound_opt_in_maps_a_derived_alias(harness: ApiHarness) -> None:
    body = {"hospital": "Hastane", "department": "Dahiliye", "resolve_department": True}
    response = harness.client.post("/v1/visits", json=body, headers=harness.patient())
    assert response.status_code == 201, response.text
    out = response.json()
    assert out["branch_id"] == "ic_hastaliklari"
    assert out["department"] == "İç Hastalıkları"


def test_unmapped_department_fails_closed_to_no_branch(harness: ApiHarness) -> None:
    # The acceptance guarantee: an unknown department, even asking to route,
    # never silently gets a specialty — it keeps its free text and no branch.
    body = {"hospital": "Hastane", "department": "Uzay Tıbbı", "resolve_department": True}
    response = harness.client.post("/v1/visits", json=body, headers=harness.patient())
    assert response.status_code == 201, response.text
    out = response.json()
    assert out["branch_id"] is None
    assert out["department"] == "Uzay Tıbbı"


def test_department_mapping_to_excluded_branch_is_refused(harness: ApiHarness) -> None:
    # Acil Tıp books no pre-visit intake (files/09 §1) — the same refusal the
    # branch path gives, reached through the department map.
    body = {"hospital": "Hastane", "department": "Acil Tıp", "resolve_department": True}
    response = harness.client.post("/v1/visits", json=body, headers=harness.patient())
    assert response.status_code == 422
    assert response.json() == {"error": "excluded_branch"}
