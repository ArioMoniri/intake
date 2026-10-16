"""INT-248 — PolicyGuard precision against the real Turkish catalogue.

A localization audit ran the guard over the shipped copy and returned 23
findings. Every one is a guard false positive, and three of them are
load-bearing:

* ``Devam edin`` — the polite imperative, the commonest sentence in the
  product. The ``sen`` detector matched ``\\w+din``, so the Talker could not
  say it.
* ``…hekiminize ulaşsın`` — the third-person optative, matched by ``\\w+sın``.
* ``Vizite tanı koymaz`` — the *disclaimer*, matched by ``\\btanı\\s+koy``.

And two findings land on RED action scripts (``Acil Servis'e gidin``), where
CLAUDE.md invariant 21 makes the bare imperative plural mandatory: a guard
that flags those is a safety failure in the opposite direction.

The morphology under test is the ``-in/-iniz`` polite imperative and the
third-person optative ``-sın/-sin`` — neither is second-person-singular
address — against ``sen``, ``senin`` and the bare second-person-singular
imperative, which are. Every narrowing below is paired with a near-miss
positive control, because a guard that is merely permissive is not fixed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.policy_guard import (
    FormOfAddress,
    PolicyGuard,
    ViolationClass,
    policy_guard_for,
)

#: The classes invariant 2 names, plus the register rule. These are the ones
#: the audit scoped; a finding here is either a copy defect or a guard defect.
CLINICAL: frozenset[ViolationClass] = frozenset(
    {
        ViolationClass.DIAGNOSIS,
        ViolationClass.TREATMENT,
        ViolationClass.PROGNOSIS,
        ViolationClass.REGISTER,
    }
)

_REPO = Path(__file__).resolve().parents[2]
_CATALOGUE = _REPO / "apps/mobile/src/lib/i18n/tr.ts"
_LIFE_THREAT = _REPO / "files/protocols/base.life_threat.yaml"


@pytest.fixture()
def guard() -> PolicyGuard:
    return policy_guard_for(locale="tr", profile=VoiceProfile.RESIDENCY_TR)


def _classes(guard: PolicyGuard, text: str) -> set[ViolationClass]:
    return {v.violation_class for v in guard.filter(text, scripted=True).violations}


# --- the 23 audit findings, verbatim from the catalogue ------------------------------

#: Every string the audit flagged, with the resource key it came from. The
#: guard must return no clinical or register finding for any of them.
AUDIT_FINDINGS: tuple[tuple[str, str], ...] = (
    ("app.tagline", "Muayeneden önce, anlattıklarınız hekiminize ulaşsın."),
    (
        "app.disclaimer",
        "Vizite tanı koymaz. Anlattıklarınız hekim değerlendirmesinin yerine geçmez.",
    ),
    ("welcome.phoneCta", "Telefonla devam edin"),
    ("auth.phone.invalid", "Numarayı kontrol edin; 05 ile başlamalı."),
    ("auth.error.code", "Kod doğrulanamadı. Kodu kontrol edin ya da yeni kod isteyin."),
    ("auth.error.network", "Sunucuya ulaşılamadı. Bağlantınızı kontrol edin."),
    ("today.continueCta", "Devam edin"),
    ("visits.new.dateOptional", "Randevu tarihiniz belli değilse boş bırakın."),
    ("visits.new.smsFilled", "Randevu bilgileriniz dolduruldu. Lütfen kontrol edin."),
    ("records.consent.cta", "İzinlere gidin"),
    (
        "wellbeing.intro",
        "Kendinizi nasıl hissettiğinizi takip edin; paylaşım her zaman sizin kontrolünüzde.",
    ),
    (
        "voice.transport.needsDevBuild",
        "Sesli görüşme bu uygulama sürümünde açılamıyor. "
        "Tam sürümü kullanın ya da yazarak devam edin.",
    ),
    ("voiceFirst.typeInstead", "Yazarak devam edin"),
    ("intake.next", "Devam edin"),
    ("review.intro", "Bölümleri kontrol edin. Neyin paylaşılacağına siz karar verirsiniz."),
    ("review.resume", "Kaldığınız yerden devam edin"),
    ("visit.reviewNote", "Notu kontrol edin"),
    ("consent.firstRun.continue", "Devam edin"),
    ("consent.basis.service", "Vizite'yi kullanmayı bırakırsanız sona erer."),
    ("health.attach.confirm", "Bu özet, vizit notunuzun taslağına eklensin mi?"),
    (
        "base.life_threat rules[0].action.ON_SITE.action_tr",
        "**Acil Servis'e gidin[ — {{tenant.acil_location_tr}}].** Randevunuzu beklemeyin. "
        'Görevlilere haber verildi. Girişte **"göğüs ağrım var"** deyin.',
    ),
    (
        "base.life_threat rules[1].action.ON_SITE.action_tr",
        "**Acil Servis'e gidin[ — {{tenant.acil_location_tr}}].** Randevunuzu beklemeyin. "
        "Görevlilere haber verildi.",
    ),
)


@pytest.mark.parametrize(("key", "text"), AUDIT_FINDINGS, ids=[k for k, _ in AUDIT_FINDINGS])
def test_the_shipped_catalogue_carries_no_clinical_or_register_finding(
    guard: PolicyGuard, key: str, text: str
) -> None:
    """The red run: every one of these is legitimate copy the guard rejected."""
    found = _classes(guard, text) & CLINICAL
    assert found == set(), f"{key} is legitimate copy but the guard reported {found}"


def test_the_commonest_sentence_in_the_product_can_be_spoken(guard: PolicyGuard) -> None:
    """``Devam edin`` is the polite imperative — ``et-`` plus ``-in``, second
    person *plural*. If the guard rejects it the Talker has no continue turn."""
    verdict = guard.filter("Devam edin.", scripted=False)
    assert verdict.text_tr == "Devam edin."
    assert verdict.violations == ()
    assert verdict.bridge_required is False


# --- invariant 21: the RED action scripts must survive the guard ----------------------


@pytest.mark.parametrize(
    "script",
    [
        "Hemen 112'yi arayın.",
        "Çocuğunuzu kucağınızda, dik ve rahat bir şekilde tutun.",
        "Ağzını veya boğazını açıp bakmayın.",
        "Acil Servis'e gidin.",
        "Bugün içinde bir acil servise başvurun.",
        "Kendi aracınızla yola çıkmayın.",
        "Tek başınıza kalmayın.",
        "Su, yiyecek ya da ilaç vermeyin.",
        "Çocuğunuzu sırtüstü yatırmayın.",
        "Yanından ayrılmayın.",
        "Poliklinik sırasında beklemeyin.",
        "Görevlilerden yardım isteyin.",
        "Randevunuzu beklemeyin.",
    ],
)
def test_red_action_scripts_pass_the_register_rule(guard: PolicyGuard, script: str) -> None:
    """CLAUDE.md invariant 21 and the clinical content rules make the bare
    imperative *plural* (Tutun · Arayın · Bakmayın) mandatory inside RED. A
    guard that reads ``-in``/``-ın`` as ``sen`` would flag the one register
    the spec requires."""
    assert ViolationClass.REGISTER not in _classes(guard, script)


def test_the_whole_life_threat_pack_passes(guard: PolicyGuard) -> None:
    """Every spoken string in the shipped RED pack, not just the sampled ones."""
    doc = yaml.safe_load(_LIFE_THREAT.read_text(encoding="utf-8"))
    offenders: list[tuple[str, ViolationClass]] = []
    for path, value in _spoken_strings(doc):
        found = _classes(guard, value) & CLINICAL
        offenders.extend((path, cls) for cls in found)
    assert offenders == []


def test_the_generic_red_copy_passes(guard: PolicyGuard) -> None:
    """INT-465: CD-24's generic RED copy, rendered as the device shows it, passes the
    guard's clinical and register classes. Before round 3 only base.life_threat was swept."""
    from protocols.generic_red import generic_red_strings, load_generic_red
    from protocols.red_render import render_red_text

    copy = load_generic_red(_REPO / "packages/protocols/generic/generic_red.yaml")
    rendered = [render_red_text(s, acil_location_tr=None) for s in generic_red_strings(copy)]
    assert rendered
    offenders = [(text, sorted(_classes(guard, text) & CLINICAL)) for text in rendered]
    assert [o for o in offenders if o[1]] == []
    # Near miss: a known diagnosis claim run through the same sweep is still flagged.
    assert ViolationClass.DIAGNOSIS in _classes(
        guard, render_red_text("Kalp krizi geçiriyorsunuz.", acil_location_tr=None)
    )


# --- near-miss positive controls: the guard still catches the real thing --------------


@pytest.mark.parametrize(
    ("form", "sentence"),
    [
        ("pronoun", "Sen nerede ağrı hissediyorsun?"),
        ("pronoun-genitive", "Senin ağrın ne zaman başladı?"),
        ("pronoun-dative", "Sana bir soru soracağım."),
        ("pronoun-accusative", "Seni dinliyorum."),
        ("pronoun-locative", "Sende bir değişiklik var."),
        ("pronoun-ablative", "Senden bunu duymak istiyorum."),
        ("question-clitic", "İyi misin?"),
        ("question-clitic-u", "Uyanık musun?"),
        ("progressive", "Şu anda ağrı hissediyorsun."),
        ("aorist", "Bu ilacı her gün alırsın."),
        ("aorist-negative", "Bunu tek başına yapamazsın."),
        ("future", "Yarın kendini daha iyi hissedeceksin."),
        ("evidential", "Dün akşam düşmüşsün."),
        ("necessitative", "Bir an önce dinlenmelisin."),
        ("conditional", "İstersen kısa bir ara verelim."),
        # -DI is -d after a voiced sound and -t after a voiceless obstruent;
        # both halves of the assimilation rule are exercised.
        ("past-after-vowel", "Bunu daha önce yaşadın mı?"),
        ("past-after-l", "Ne zaman geldin?"),
        ("past-after-k", "Nereye baktın?"),
        ("past-after-t", "Ne zaman gittin?"),
        ("nominal-predicate", "Şu anda çok yorgunsun."),
        ("nominal-predicate-hasta", "Demek ki hastasın."),
        ("nasilsin", "Nasılsın?"),
        ("bare-imperative", "Bana biraz anlat."),
        ("bare-imperative-bak", "Şuraya bak."),
        ("bare-imperative-negative", "Oraya bakma."),
        ("bare-imperative-nefes", "Derin bir nefes al."),
    ],
)
def test_a_genuine_sen_address_is_still_caught(
    guard: PolicyGuard, form: str, sentence: str
) -> None:
    """Precision must not become permissiveness: every second-person-singular
    construction the product could emit still trips the register rule."""
    assert ViolationClass.REGISTER in _classes(guard, sentence), form


@pytest.mark.parametrize(
    ("form", "sentence"),
    [
        ("pronoun", "Sen nerede ağrı hissediyorsun?"),
        ("question-clitic", "İyi misin?"),
        ("aorist", "Bu ilacı her gün alırsın."),
        ("past", "Nereye baktın?"),
        ("nominal-predicate", "Şu anda çok yorgunsun."),
        ("bare-imperative", "Bana biraz anlat."),
    ],
)
def test_every_sen_rule_stands_down_once_the_patient_has_mirrored_it(
    form: str, sentence: str
) -> None:
    """``sen`` is reachable only by mirroring, and mirroring releases the whole
    detector, not the tier that happened to fire first."""
    mirrored = policy_guard_for(
        locale="tr", profile=VoiceProfile.RESIDENCY_TR, form_of_address=FormOfAddress.SEN
    )
    assert ViolationClass.REGISTER not in _classes(mirrored, sentence), form


@pytest.mark.parametrize(
    "sentence",
    [
        "Size teşhis koyabilirim.",
        "Bu bir migren atağı.",
        "Kalp krizi geçiriyorsunuz.",
        "Doktorunuz gibi ben de tanı koyarım.",
        "Bu şikâyete migren tanısı koydum.",
    ],
)
def test_a_genuine_diagnosis_claim_is_still_caught(guard: PolicyGuard, sentence: str) -> None:
    assert ViolationClass.DIAGNOSIS in _classes(guard, sentence)


@pytest.mark.parametrize(
    "sentence",
    [
        "Günde iki kez ağrı kesici alın.",
        "Bu ilacı kullanmayı bırakın.",
        "Size bir tedavi öneriyorum.",
        "İlacınızın dozunu artırın.",
        "Antibiyotiğinizi hemen kullanın.",
        "Bu hapı günde bir kez alın.",
    ],
)
def test_a_genuine_treatment_instruction_is_still_caught(guard: PolicyGuard, sentence: str) -> None:
    assert ViolationClass.TREATMENT in _classes(guard, sentence)


@pytest.mark.parametrize(
    "sentence",
    [
        "Merak etmeyin, kısa sürede geçer.",
        "Ciddi bir şey değil.",
        "Endişelenmenize gerek yok.",
        "Birkaç güne iyileşirsiniz.",
    ],
)
def test_a_genuine_prognosis_is_still_caught(guard: PolicyGuard, sentence: str) -> None:
    assert ViolationClass.PROGNOSIS in _classes(guard, sentence)


# --- the morphology, as contrast pairs -----------------------------------------------


@pytest.mark.parametrize(
    ("polite", "singular"),
    [
        ("Devam edin.", "Devam et."),
        ("Acil Servis'e gidin.", "Acil servise git."),
        ("Çocuğunuzu kucağınızda tutun.", "Çocuğunu kucağında tut."),
        ("Bana anlatın.", "Bana anlat."),
        ("Şuraya bakın.", "Şuraya bak."),
        ("Oraya bakmayın.", "Oraya bakma."),
        ("Biraz bekleyin.", "Biraz bekle."),
        ("Nasılsınız?", "Nasılsın?"),
        ("İyi misiniz?", "İyi misin?"),
        ("Ne zaman başladınız?", "Ne zaman başladın."),
    ],
)
def test_the_polite_plural_passes_and_its_singular_twin_does_not(
    guard: PolicyGuard, polite: str, singular: str
) -> None:
    """The whole defect in one shape: ``-in/-iniz`` is the register the spec
    mandates; the bare stem and the 2sg suffixes are the one it forbids."""
    assert ViolationClass.REGISTER not in _classes(guard, polite), polite
    assert ViolationClass.REGISTER in _classes(guard, singular), singular


@pytest.mark.parametrize(
    "sentence",
    [
        "Anlattıklarınız hekiminize ulaşsın.",
        "Bu özet taslağa eklensin.",
        "Notunuz hekiminize gönderilsin.",
        "Kolay gelsin.",
        "Geçmiş olsun.",
    ],
)
def test_the_third_person_optative_is_not_address(guard: PolicyGuard, sentence: str) -> None:
    """``-sın/-sin`` on a third-person subject is not second-person anything."""
    assert ViolationClass.REGISTER not in _classes(guard, sentence)


@pytest.mark.parametrize(
    "sentence",
    [
        "Kadın Hastalıkları ve Doğum",
        "Bütün gün sürdü mü?",
        "Bu metin size gösterilecek.",
        "Randevu saatinizi kapatın.",
        "Şikâyetinizi anlatın.",
        "Bilgilerinizi yönetin.",
        "Hizmetin kapsamı budur.",
        "Doksan gün içinde silinir.",
    ],
)
def test_nouns_that_end_in_the_same_syllables_are_not_address(
    guard: PolicyGuard, sentence: str
) -> None:
    """``kadın``, ``bütün``, ``metin`` and the polite imperatives ``kapatın``,
    ``anlatın``, ``yönetin`` all end in the syllables a naive ``-DIn`` pattern
    matches. None of them is a verb in the second person singular."""
    assert ViolationClass.REGISTER not in _classes(guard, sentence)


# --- the disclaimer, and negation generally -------------------------------------------


@pytest.mark.parametrize(
    "sentence",
    [
        "Vizite tanı koymaz.",
        "Bu uygulama teşhis koymaz.",
        "Vizite size tanı koymuyor.",
        "Burada tanı konmadı.",
        "Doktorunuz size bir tanı söyledi mi?",
    ],
)
def test_a_disclaimer_is_not_a_diagnosis(guard: PolicyGuard, sentence: str) -> None:
    """The Turkish negative and the infinitive both attach ``-m`` directly to
    the stem; an affirmative finite form never does. Flagging the sentence
    that disclaims diagnosis is the guard inverting its own purpose."""
    assert ViolationClass.DIAGNOSIS not in _classes(guard, sentence)


@pytest.mark.parametrize(
    "sentence",
    [
        "Randevu tarihiniz belli değilse boş bırakın.",
        "Tam sürümü kullanın ya da yazarak devam edin.",
        "Vizite'yi kullanmayı bırakırsanız sona erer.",
        "Bölümleri kontrol edin.",
        "Düzenli kullandığınız bir ilaç var mı?",
        "Daha önce bu şikâyet için tedavi gördünüz mü?",
    ],
)
def test_an_interface_instruction_is_not_a_treatment_instruction(
    guard: PolicyGuard, sentence: str
) -> None:
    """``kullanın`` and ``bırakın`` are treatment only when what is used or
    stopped is a medicine or a dose. A form field is neither."""
    assert ViolationClass.TREATMENT not in _classes(guard, sentence)


# --- one question per turn ------------------------------------------------------------


def test_a_fronted_subject_is_not_a_second_question(guard: PolicyGuard) -> None:
    """A comma before the main clause is not a second question. The rule fires
    on a comma-joined *second* interrogative, which requires the fragment
    before the comma to have asked one already."""
    text = "Bu özet, vizit notunuzun taslağına eklensin mi?"
    assert ViolationClass.MULTI_QUESTION not in _classes(guard, text)


def test_two_comma_joined_questions_are_still_caught(guard: PolicyGuard) -> None:
    text = "Şu anda hastanede misiniz, yanınızda biri var mı?"
    assert ViolationClass.MULTI_QUESTION in _classes(guard, text)


# --- the whole catalogue, as a standing gate -------------------------------------------


def _spoken_strings(node: object, path: str = "") -> list[tuple[str, str]]:
    """Every patient-facing Turkish string in a protocol pack."""
    keys = {"action_tr", "why_tr", "ask_one_tr", "text_tr", "prompt_tr", "label_tr"}
    lists = {"do_nots_tr"}
    out: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else str(key)
            if key in keys and isinstance(value, str):
                out.append((here, value))
            elif key in lists and isinstance(value, list):
                out.extend(
                    (f"{here}[{i}]", item) for i, item in enumerate(value) if isinstance(item, str)
                )
            else:
                out.extend(_spoken_strings(value, here))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            out.extend(_spoken_strings(item, f"{path}[{i}]"))
    return out


_ENTRY = re.compile(r'^\s*"([^"]+)":\s*"((?:[^"\\]|\\.)*)",?\s*$', re.MULTILINE)


def _catalogue() -> list[tuple[str, str]]:
    src = _CATALOGUE.read_text(encoding="utf-8")
    src = re.sub(r'":\s*\n\s*"', '": "', src)  # values wrapped onto the next line
    return [(m.group(1), m.group(2).replace('\\"', '"')) for m in _ENTRY.finditer(src)]


def test_the_whole_shipped_catalogue_is_clean(guard: PolicyGuard) -> None:
    """The standing gate. Any finding here is a real copy defect or a new
    guard false positive, and the failure message says which string."""
    entries = _catalogue()
    assert len(entries) > 500, "the catalogue parser stopped matching — fix the parser"
    offenders = [
        (key, cls.value)
        for key, value in entries
        for cls in sorted(_classes(guard, value) & CLINICAL)
    ]
    assert offenders == []
