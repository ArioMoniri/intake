"""Protocol Authoring Agent: deterministic L0 scaffolds (INT-057).

files/09 §2, L0 row: a "starter pack drafted by the *Protocol Authoring
Agent* from the cluster pack + branch template + cited public guidance
(Turkish specialty-society guidelines, MoH clinical protocols); every slot
has ``ask_tr/follow_up_tr``; red flags only *copied* from base/cluster,
never invented" — and it is never served: review queue only, and an L0 pack
resolved for a live session raises (CLAUDE.md invariant 13, enforced by
:mod:`protocols.taxonomy` and pinned in tests/protocols/test_l0_guard.py).

What this module deliberately is NOT:

- **Not clinical authorship.** The scaffold's single red-flag entry is a
  ``draft_needs_source`` stub whose trigger is the invariant-17
  sole-exception form; its enum fields sit on the schema's lowest rungs and
  assert nothing. The INT-040 compilability surface
  (:func:`protocols.validator.pack_compilable`) refuses draft rules for a
  served pack; generation self-checks that refusal and fails closed rather
  than ever emitting a stub a compiler would serve.
- **Not a guideline inventor.** The blueprint names Turkish guidance
  *categories* (files/09 §2) and one binding instrument (files/04 §3, the
  EK-4 Tebliğ) but no cluster-specific guideline title; every scaffold says
  exactly that, and the missing titles are awaiting-human content
  (files/04 §8.1 rule 3: never an invented citation).
- **Not a patient-data reader.** files/09 §7: "The Protocol Authoring Agent
  (L0 drafts) has no access to patient data at all — it reads the taxonomy,
  cluster packs and cited guidance only." The import boundary is enforced
  by AST scan in tests/protocols/test_l0_guard.py, not by convention.

Regeneration is deterministic: the same taxonomy and template produce a
byte-identical file, and a pack promoted beyond L0 is never overwritten.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Final

import yaml

from protocols.loader import load_pack
from protocols.pack import ProtocolPack
from protocols.taxonomy import Branch, Cluster, Taxonomy
from protocols.types import Maturity, PackLayer
from protocols.validator import PLACEHOLDER_SIGNOFF_RE, pack_compilable

__all__ = [
    "CLUSTER_GUIDANCE",
    "NAMED_GUIDANCE_SOURCES",
    "AuthoringError",
    "ExcludedBranchAuthoringError",
    "MissingClusterTemplateError",
    "PromotedPackOverwriteError",
    "generate_all",
    "generate_l0",
]


class AuthoringError(Exception):
    """Base of every authoring refusal — the generator fails closed."""


class ExcludedBranchAuthoringError(AuthoringError):
    """No intake pack may exist for a branch of the excluded cluster —
    pre-visit intake is never used for emergencies (files/09 §1 row 9)."""


class PromotedPackOverwriteError(AuthoringError):
    """The target pack has been promoted beyond L0 — clinician-reviewed
    content is never overwritten by the generator (files/09 §2)."""


class MissingClusterTemplateError(AuthoringError):
    """An intake cluster without an authoring-template entry — fail closed
    rather than scaffold with unnamed guidance sources (files/09 §2)."""


# The Turkish guidance sources the blueprint itself names — categories from
# files/09 §2 plus the one named binding instrument of files/04 §3. Nothing
# here is invented; no cluster-specific guideline title exists anywhere in
# files/04 or files/09, and the scaffold states that instead of guessing.
NAMED_GUIDANCE_SOURCES: Final[tuple[str, str, str]] = (
    "T.C. Sağlık Bakanlığı klinik protokolleri / HSGM rehberleri "
    "(files/09 §2 'MoH clinical protocols'; files/04 §8.4)",
    "İlgili uzmanlık derneği kılavuzları (files/09 §2 'Turkish specialty-society guidelines')",
    "Yataklı Sağlık Tesislerinde Acil Servis Hizmetlerinin Uygulama Usul ve "
    "Esasları Hakkında Tebliğ, RG 13/9/2022 sayı 31952, EK-4 "
    "(files/04 §3 — acuity levels are bound by law, not guidance)",
)

# The eight intake clusters of files/09 §1 (the ninth, `excluded`, books no
# intake and gets no scaffold). Every entry resolves to the same named
# sources because the blueprint names none more specific for any cluster —
# tests cross-check this table against taxonomy/branches.yaml so a new
# cluster fails closed here instead of scaffolding unnamed.
CLUSTER_GUIDANCE: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        cluster_id: NAMED_GUIDANCE_SOURCES
        for cluster_id in (
            "medical",
            "surgical",
            "sensory",
            "womens_health",
            "child_health",
            "mental_health",
            "dental",
            "allied_and_reports",
        )
    }
)

_NO_TITLE_NOTE: Final[str] = (
    "files/04 and files/09 name no specific guideline title for the "
    "{cluster!r} cluster — selection awaits the branch clinician "
    "(awaiting-human; files/04 §8.1 rule 3: never an invented citation)"
)


def _stub_rule(branch: Branch, cluster: Cluster) -> dict[str, object]:
    """The one red-flag entry of a scaffold: a ``draft_needs_source`` stub.

    files/09 §2: red flags are "only *copied* from base/cluster, never
    invented" — the real rules arrive through the ``extends`` chain once the
    cluster pack lands (P1). This stub is not a rule: its trigger is the
    invariant-17 sole-exception form, its level and route are the schema's
    lowest rungs (YESIL / EXPEDITE — structural, asserting nothing), and the
    compiler refuses to emit it into a served pack (files/04 §8.1 rule 3).
    """
    source_gap = (
        "Rule set not yet authored: trigger, EK-4 level and route await "
        "clinical sign-off. The `when` field carries the sole permitted "
        "pending-value literal (CLAUDE.md invariant 17); level YESIL and "
        "route EXPEDITE are the schema's lowest rungs and assert nothing "
        "clinically; this rule is never compiled into a served pack "
        "(files/04 §8.1 rule 3). Expected named Turkish guidance "
        "(files/09 §2; files/04 §3): "
        + "; ".join(NAMED_GUIDANCE_SOURCES)
        + ". "
        + _NO_TITLE_NOTE.format(cluster=cluster.id)
        + "."
    )
    return {
        "id": f"rf.{branch.id}_l0_taslak",
        "label_tr": f"{branch.name_tr} — branşa özgü kırmızı bayrak taslağı (klinik onay bekliyor)",
        "when": f"TODO: {branch.id} branch-specific red-flag trigger requires clinical sign-off",
        "tense": "ever",
        "tense_anchor": "sikayet_suresi",
        "level": "YESIL",
        "route": "EXPEDITE",
        "notify_clinic": "never",
        "status": "draft_needs_source",
        "source_gap": source_gap,
    }


def _payload(branch: Branch, cluster: Cluster) -> dict[str, object]:
    """The scaffold document, insertion-ordered for deterministic output.

    The branch template (files/09 §2 "branch template"): one generic
    visit-context section whose slots all carry ``ask_tr``/``follow_up_tr``
    (≤ B1 Turkish, ``siz`` register, one question per turn, no numerals —
    CLAUDE.md invariant 22). Cluster and base content — the real sections
    and red flags — arrive through ``extends`` (files/03 §6), never by
    copy-paste into a draft.
    """
    return {
        "kind": "pack",
        "id": f"specialty.{branch.id}",
        "layer": PackLayer.SPECIALTY.value,
        "version": "0.1.0",
        "schema_version": 2,
        "maturity": Maturity.L0.value,
        "status": "generated-l0-awaiting-clinical-review",
        "language": "tr",
        "title_tr": f"{branch.name_tr} ön görüşme protokolü (L0 taslak)",
        "extends": cluster.pack,
        "visit_types": [visit_type.value for visit_type in branch.visit_types],
        "sections": {
            "ziyaret_baglami": {
                "slots": {
                    "basvuru_nedeni": {
                        "type": "string",
                        "required": True,
                        "ask_tr": "Bugünkü randevunuzun sebebini kısaca anlatır mısınız?",
                        "follow_up_tr": "Sizi hekime getiren en önemli şikâyetiniz nedir?",
                    },
                    "sikayet_suresi": {
                        "type": "duration",
                        "required": False,
                        "ask_tr": "Bu şikâyetiniz ne zamandır var?",
                        "follow_up_tr": "Gün ya da hafta olarak yaklaşık söyleyebilir misiniz?",
                    },
                },
            },
        },
        "red_flags": [_stub_rule(branch, cluster)],
    }


def _header(branch: Branch, cluster: Cluster, sources: tuple[str, ...]) -> str:
    lines = [
        "# L0 TASLAK — ÜRETİLDİ, ASLA SERVİS EDİLMEZ / generated draft, never served.",
        "# files/09 §2 (L0 = review queue only); CLAUDE.md invariant 13 (an L0 pack",
        "# resolved for a live session raises — protocols.taxonomy.L0PackServedError).",
        f"# Generated by `protocols generate-l0 --branch {branch.id}` (INT-057) from",
        "# packages/protocols/taxonomy/branches.yaml + the cluster authoring template.",
        "# Deterministic: same taxonomy + template => byte-identical regeneration; a",
        "# pack promoted beyond L0 is never overwritten by the generator.",
        "#",
        f"# Named Turkish guidance sources for the {cluster.id!r} cluster — what the",
        "# branch clinician sources real rules FROM (files/09 §2; files/04 §3):",
    ]
    lines.extend(f"#   - {source}" for source in sources)
    note = _NO_TITLE_NOTE.format(cluster=cluster.id)
    lines.extend(f"# {line}" for line in _wrap(note, width=78))
    lines.extend(
        [
            "#",
            "# The red_flags entry below is a draft_needs_source stub: the compiler",
            "# refuses to emit it into a served pack (protocols.validator.pack_compilable;",
            "# CLAUDE.md invariant 17 sole-exception form).",
        ]
    )
    return "\n".join(lines) + "\n"


def _wrap(text: str, width: int) -> list[str]:
    """Deterministic greedy wrap (textwrap would also do, but the break
    points of the committed drafts must never drift with stdlib changes)."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _render(branch: Branch, cluster: Cluster, sources: tuple[str, ...]) -> str:
    payload = _payload(branch, cluster)
    pack = ProtocolPack.model_validate(payload)
    _self_check(pack)
    body = yaml.safe_dump(
        payload,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=10_000,  # every scalar on one line — the gate matches per line
    )
    return _header(branch, cluster, sources) + body


def _self_check(pack: ProtocolPack) -> None:
    """Refuse to emit a scaffold whose stub the compiler would serve."""
    (stub,) = pack.red_flags
    if PLACEHOLDER_SIGNOFF_RE.match(stub.when) is None:
        raise AuthoringError(
            f"{pack.id}: stub trigger drifted from the invariant-17 "
            "sole-exception form — refusing to write the scaffold"
        )
    if stub.id not in pack_compilable(pack).excluded_rules:
        raise AuthoringError(
            f"{pack.id}: the compilability surface would serve the stub "
            f"{stub.id!r} — refusing to write the scaffold (files/04 §8.1 rule 3)"
        )


def generate_l0(taxonomy: Taxonomy, branch_id: str, packs_root: Path) -> Path:
    """Scaffold one branch's L0 draft under ``<packs_root>/specialty/``.

    Raises :class:`protocols.taxonomy.UnknownBranchError` for an unmapped
    branch id, :class:`ExcludedBranchAuthoringError` for the excluded
    cluster, :class:`MissingClusterTemplateError` for a cluster the template
    table does not know, and :class:`PromotedPackOverwriteError` when the
    target pack's maturity is past L0. Regeneration over an existing L0
    draft is byte-identical given the same inputs.
    """
    branch = taxonomy.branch(branch_id)
    cluster = taxonomy.cluster_of(branch)
    if not cluster.intake or cluster.pack is None:
        raise ExcludedBranchAuthoringError(
            f"branch {branch.id!r} is in the excluded cluster — pre-visit intake "
            "is never used for emergencies, so no intake pack may exist for it "
            "(files/09 §1 row 9)"
        )
    sources = CLUSTER_GUIDANCE.get(cluster.id)
    if sources is None:
        raise MissingClusterTemplateError(
            f"cluster {cluster.id!r} has no authoring-template entry — refusing "
            "to scaffold with unnamed guidance sources (files/09 §2)"
        )
    content = _render(branch, cluster, sources)
    target = packs_root / PackLayer.SPECIALTY.value / f"{branch.id}.yaml"
    if target.exists():
        existing = load_pack(target)
        if existing.maturity is not Maturity.L0:
            raise PromotedPackOverwriteError(
                f"{target}: pack {existing.id!r} is {existing.maturity.value}, "
                "past L0 — clinician-reviewed content is never overwritten by "
                "the generator (files/09 §2)"
            )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def generate_all(taxonomy: Taxonomy, packs_root: Path) -> tuple[Path, ...]:
    """Scaffold every intake branch (files/09 §2 rollout: "P0 generates L0
    for **all** branches"), in taxonomy order.

    Excluded branches get no draft at all; a branch whose pack has been
    promoted past L0 is left untouched and does not appear in the result —
    the promoted file is the clinician's, not the generator's.
    """
    written: list[Path] = []
    for branch in taxonomy.branches:
        if not taxonomy.cluster_of(branch).intake:
            continue
        try:
            written.append(generate_l0(taxonomy, branch.id, packs_root))
        except PromotedPackOverwriteError:
            continue
    return tuple(written)
