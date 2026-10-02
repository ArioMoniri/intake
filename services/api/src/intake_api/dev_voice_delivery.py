"""The conversational delivery lines the dev George route admits (INT-414).

The route is catalogue-only (INT-326): ``text_tr`` reaches the vendor only when
its ``clip_text_hash`` is a row of a compiled clip manifest. The delivery lines
— the welcome, lead-ins, topic transitions, acknowledgements and the repair
line the mobile composer (``apps/mobile/src/lib/dialogue/delivery.ts``) speaks
around a scripted question — are fixed catalogue copy too, but they are app
copy rather than pack content, so no manifest carries them. This module is
where they are admitted instead, on exactly the same terms:

- **Verbatim, from the ``tr`` catalogue.** Every value is the Turkish string of
  its key in ``apps/mobile/src/lib/i18n/tr.ts``, byte for byte —
  ``tests/release/test_delivery_copy.py`` fails on any drift, and the mobile
  suite (``deliveryPlan.test.ts``) fails unless the key set is exactly the
  lines the voice lane can speak. The catalogue stays the source of truth
  (invariant 5); this is a pinned mirror of it, not a second author.
- **Hashed like a manifest row.** :func:`delivery_text_hashes` keys each line
  with ``clip_text_hash``, the function the compiled manifests use, so the
  route's single membership test covers both.
- **Nothing a patient said.** Every line is fixed copy with no slot to fill;
  a patient's words cannot hash to one (invariant 2/10 posture).
- **No numeral** (invariant 22); the route asserts it again before any dial.
- **No RED, no instrument item.** Those are pack content with their own pinned
  delivery contexts; a delivery line pins none and is refused under ``red``
  by the route like any other text.

Lines the voice lane never speaks — the typed lane's orientation, the closing
(rendered on the review screen) and the measurements topic (text-only steps) —
are deliberately absent: the allow-list is what is spoken, not what exists.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from protocols.dsl import clip_text_hash

__all__ = ["DELIVERY_TR", "delivery_text_hashes"]

#: key → Turkish line, in deck order. Keys are the mobile catalogue's own.
DELIVERY_TR: Final[Mapping[str, str]] = MappingProxyType(
    {
        "dialogue.delivery.welcome.a": (
            "Hoş geldiniz. Muayenenizden önce size bazı sorular soracağım."
        ),
        "dialogue.delivery.welcome.b": (
            "Merhaba, hoş geldiniz. Muayeneden önce birlikte bazı sorular üzerinden geçelim."
        ),
        "dialogue.delivery.welcome.c": (
            "Hoş geldiniz. Muayenenize hazırlık için size bazı sorular sormak istiyorum."
        ),
        "dialogue.delivery.orientVoice.a": (
            "Soruları ekranda da görebilirsiniz. Dilerseniz yazarak da yanıt verebilirsiniz."
        ),
        "dialogue.delivery.orientVoice.b": (
            "Ben konuşurken araya girebilirsiniz. Sorular ekranda yazılı olarak da durur."
        ),
        "dialogue.delivery.resume.a": "Kaldığımız yerden devam edelim.",
        "dialogue.delivery.resume.b": "Kaldığımız yerden sürdürelim.",
        "dialogue.delivery.lead.a": "Devam edelim.",
        "dialogue.delivery.lead.b": "Sıradaki soruya geçelim.",
        "dialogue.delivery.lead.c": "Şimdi şunu soralım.",
        "dialogue.delivery.lead.d": "Bir de şunu öğrenmek istiyorum.",
        "dialogue.delivery.thanks.a": "Teşekkürler.",
        "dialogue.delivery.thanks.b": "Teşekkür ederim.",
        "dialogue.delivery.thanks.c": "Not aldım, teşekkürler.",
        "dialogue.delivery.hesitant.a": "Anlıyorum, devam edelim.",
        "dialogue.delivery.hesitant.b": "Peki, bu şekilde not aldım.",
        "dialogue.delivery.revised.a": "Düzeltmeniz için teşekkürler.",
        "dialogue.delivery.revised.b": "Düzelttiğinizi not aldım.",
        "dialogue.delivery.silence.a": "Önceki soruya sonra ekrandan dönebilirsiniz.",
        "dialogue.delivery.silence.b": "Önceki soruyu daha sonra ekranda yanıtlayabilirsiniz.",
        "dialogue.notUnderstood": (
            "Söylediğinizi tam anlayamadım. Aynı soruyu bir kez daha soralım."
        ),
        "dialogue.delivery.repair.b": "Yanıtınızı tam anlayamadım. Soruyu bir kez daha soralım.",
        "dialogue.delivery.pain.a": "Ağrınızı biraz daha iyi anlamak istiyorum.",
        "dialogue.delivery.pain.b": "Ağrınızla ilgili birkaç ayrıntı soralım.",
        "dialogue.delivery.instrument.a": (
            "Sıradaki sorular standart bir ankete ait. Bu yüzden her zaman aynı şekilde sorulur."
        ),
        "dialogue.delivery.instrument.b": "Şimdi herkese aynı biçimde sorulan bir ankete geçelim.",
        "dialogue.delivery.sensitive.a": (
            "Sıradaki konu biraz daha özel. Acele etmeden yanıtlayabilirsiniz."
        ),
        "dialogue.delivery.sensitive.b": "Şimdi biraz daha kişisel bir konuya geçelim.",
        "dialogue.delivery.sensitiveLead.a": "Yavaş yavaş devam edelim.",
        "dialogue.delivery.sensitiveLead.b": "Nasıl rahat ediyorsanız öyle yanıtlayabilirsiniz.",
        "dialogue.delivery.topic.allergies.a": "Şimdi alerjilerle ilgili sorulara geçelim.",
        "dialogue.delivery.topic.allergies.b": "Sırada alerjilerle ilgili sorular var.",
        "dialogue.delivery.topic.medications.a": "Şimdi ilaçlarla ilgili sorulara geçelim.",
        "dialogue.delivery.topic.medications.b": "Sırada ilaçlarla ilgili sorular var.",
        "dialogue.delivery.topic.pmh.a": "Şimdi sağlık geçmişinizle ilgili sorulara geçelim.",
        "dialogue.delivery.topic.pmh.b": "Sırada sağlık geçmişinizle ilgili sorular var.",
        "dialogue.delivery.topic.family.a": (
            "Şimdi ailenizin sağlık geçmişine geçelim. Acele etmeden yanıtlayabilirsiniz."
        ),
        "dialogue.delivery.topic.family.b": "Sıradaki sorular ailenizin sağlık geçmişiyle ilgili.",
        "dialogue.delivery.topic.social.a": "Şimdi günlük yaşamınızla ilgili sorulara geçelim.",
        "dialogue.delivery.topic.social.b": "Sırada günlük yaşamınızla ilgili sorular var.",
        "dialogue.delivery.topic.wrapup.a": "Bitirmeden önce şunu da soralım.",
        "dialogue.delivery.topic.wrapup.b": "Sona yaklaştık.",
    }
)


def delivery_text_hashes() -> frozenset[str]:
    """The ``clip_text_hash`` of every admitted delivery line."""
    return frozenset(clip_text_hash(text) for text in DELIVERY_TR.values())
