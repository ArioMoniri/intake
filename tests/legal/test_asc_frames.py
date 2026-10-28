"""INT-502: the App Store screenshots and header, their captions, sizes and capture.

GitHub #856. INT-502 captures the product page header and the iPhone screenshots
from the real app, with simulated patients only, and uploads them through
INT-495's writer once the owner says yes. This suite pins what can be checked
before the first byte is captured:

1. **The captions are store copy.** They are a draft for the legal lane until
   they are promoted. Turkish is complete and governs, and every Turkish line
   passes PolicyGuard and the `siz` register. Both languages pass the strict
   claims scan (invariant 20) and the device-claim gate. Every caption quotes
   the app string or served listing line it rests on, and the quote is present
   in the cited file.
2. **The sizes are Apple's.** docs/store/asc/assets.yaml equals the screenshot
   specifications table, re-read on 2026-10-29. The render targets cover 6.9
   inch, 6.5 inch and the required medium group, one target per slot.
3. **The frame is the app's own and stays readable.** The colours are
   theme.ts tokens and the fonts are the app's own OFL faces, pinned by sha256.
   The phone sits whole inside the canvas with even sides and keeps the
   capture's aspect. The text stays at a readable size, and every frame of a
   size puts the phone in the same place.
4. **Export reads served copy only and real captures only.** It refuses draft
   captions and refuses a capture of the wrong size or with a non-production
   name.
5. **The capture script sets a clean status bar and the frame's appearance**,
   refuses anything but synthetic data, and records provenance with hashes,
   never values.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import struct
import sys
import zlib
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

import pytest
import yaml
from intake_platform.legal import claims
from intake_platform.store import listing as listing_mod
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.policy_guard import FormOfAddress, PolicyGuard, policy_guard_for
from store_drafts_harness import BANNER, DRAFTS, REPO, STRICT, body

STORE_SCRIPTS = REPO / "scripts" / "store"
sys.path.insert(0, str(STORE_SCRIPTS))

import asc_assets  # noqa: E402
import capture_frames  # noqa: E402
import frame_plan  # noqa: E402
import render_frames  # noqa: E402

CAPTION_DRAFT = DRAFTS / "app-store.screenshots.draft.yaml"
THEME = REPO / "apps" / "mobile" / "src" / "lib" / "theme.ts"
MOBILE_PACKAGE = REPO / "apps" / "mobile" / "package.json"

#: developer.apple.com/help/app-store-connect/reference/screenshot-specifications,
#: read 2026-10-29: the iPhone groups this listing fills, portrait pixels.
#: creative-assets-specifications, same day: the 21:9 product page header.
APPLE_TABLE: dict[str, tuple[tuple[int, int], ...]] = {
    "iphone-large": ((1260, 2736), (1290, 2796), (1320, 2868)),
    "iphone-faceid-large": ((1284, 2778), (1242, 2688)),
    "iphone-medium": ((1179, 2556), (1206, 2622)),
    "product-page-header": ((3840, 1646),),
}
#: The one group the page says a submission needs.
APPLE_REQUIRED = {"iphone-medium"}


def _png(path: Path, width: int, height: int, *, color_type: int = 2) -> Path:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    payload = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"\0"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload + chunk(b"IEND", b""))
    return path


def _load_i18n_gate() -> ModuleType:
    """The register lexicon has one home (INT-253); read it, never copy it."""
    path = REPO / "tests" / "release" / "test_i18n_complete.py"
    spec = importlib.util.spec_from_file_location("i18n_gate_for_int502", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def guard() -> PolicyGuard:
    return policy_guard_for(
        locale="tr", profile=VoiceProfile.RESIDENCY_TR, form_of_address=FormOfAddress.SIZ
    )


@pytest.fixture(scope="module")
def spec() -> frame_plan.FrameSpec:
    return frame_plan.load_spec(frame_plan.FRAMES)


@pytest.fixture(scope="module")
def captions() -> dict[str, frame_plan.Caption]:
    return frame_plan.load_captions(CAPTION_DRAFT)


def _caption_lines(captions: dict[str, frame_plan.Caption], locale: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for caption in captions.values():
        eyebrow, headline = caption.text[locale]
        out.append((caption.caption_id, eyebrow))
        out.append((caption.caption_id, " ".join(headline.split("\n"))))
    return out


# --- 1. the captions are store copy --------------------------------------------------------


def test_the_caption_file_is_a_draft_for_the_legal_lane() -> None:
    assert CAPTION_DRAFT.read_text(encoding="utf-8").splitlines()[0].lstrip("#> ").strip() == (
        BANNER
    )
    provenance = body(CAPTION_DRAFT)["provenance"]
    assert provenance["status"] == "pending legal-lane review"
    assert provenance["issue"] == "INT-502"
    readme = (REPO / "docs" / "legal" / "drafts" / "README.md").read_text(encoding="utf-8")
    assert CAPTION_DRAFT.name in readme


def test_every_frame_and_the_header_has_a_complete_turkish_caption(
    spec: frame_plan.FrameSpec, captions: dict[str, frame_plan.Caption]
) -> None:
    wanted = {frame.frame_id for frame in spec.frames} | {spec.header_caption}
    assert set(captions) == wanted
    for caption in captions.values():
        assert set(caption.text) == {"tr", "en-US"}, caption.caption_id
        for locale, (eyebrow, headline) in caption.text.items():
            assert eyebrow.strip() and headline.strip(), (caption.caption_id, locale)


def test_a_caption_without_turkish_is_refused(tmp_path: Path) -> None:
    loaded = body(CAPTION_DRAFT)
    del loaded["captions"][0]["tr"]
    planted = tmp_path / "captions.yaml"
    planted.write_text(yaml.safe_dump(loaded, allow_unicode=True), encoding="utf-8")
    with pytest.raises(frame_plan.PlanError, match="tr"):
        frame_plan.load_captions(planted)


def test_every_turkish_caption_passes_policyguard(
    guard: PolicyGuard, captions: dict[str, frame_plan.Caption]
) -> None:
    found = [
        (where, violation.violation_class.value, sentence)
        for where, line in _caption_lines(captions, "tr")
        for sentence in guard.sentences(line)
        for violation in guard.inspect_sentence(sentence)
    ]
    assert found == []
    # Near misses: the guard this test leans on is armed for both arms it relies on.
    assert {v.violation_class.value for v in guard.inspect_sentence("Bu ilacı alın.")} == {
        "treatment"
    }
    assert {v.violation_class.value for v in guard.inspect_sentence("Sen anlat.")} == {"register"}


def test_no_turkish_caption_addresses_the_reader_as_sen(
    captions: dict[str, frame_plan.Caption],
) -> None:
    gate = _load_i18n_gate()
    assert [where for where, line in _caption_lines(captions, "tr") if gate._SEN.search(line)] == []
    assert gate._SEN.search("Notunu sen seç.")


def test_every_caption_passes_the_strict_claims_scan_and_the_device_claim_gate(
    captions: dict[str, frame_plan.Caption],
) -> None:
    hits = [
        (where, locale, hit.pattern)
        for locale in ("tr", "en-US")
        for where, line in _caption_lines(captions, locale)
        for hit in claims.scan_text(line, groups=STRICT, path=where)
    ]
    hits += [
        (where, locale, hit.pattern)
        for locale in ("tr", "en-US")
        for where, line in _caption_lines(captions, locale)
        for hit in listing_mod.device_claim_hits(line, field=where)
    ]
    assert hits == []
    assert claims.scan_text("Doğruluk oranı %95.", groups=STRICT), "the near miss must hit"


def test_every_caption_quotes_a_line_present_in_the_file_it_cites(
    captions: dict[str, frame_plan.Caption],
) -> None:
    for caption in captions.values():
        cited = REPO / caption.source.split(" ", 1)[0]
        assert cited.is_file(), (caption.caption_id, caption.source)
        assert caption.quote in cited.read_text(encoding="utf-8"), caption.caption_id


def test_headlines_fit_the_frame_and_carry_no_digit(
    spec: frame_plan.FrameSpec, captions: dict[str, frame_plan.Caption]
) -> None:
    for caption in captions.values():
        for locale, (eyebrow, headline) in caption.text.items():
            where = (caption.caption_id, locale)
            assert not re.search(r"\d", eyebrow + headline), where
            lines = headline.split("\n")
            if caption.caption_id == spec.header_caption:
                assert len(lines) == 1 and len(headline) <= frame_plan.HEADER_MAX_CHARS, where
            else:
                assert 1 <= len(lines) <= 2, where
                assert all(len(line) <= frame_plan.LINE_MAX_CHARS for line in lines), where


def test_the_header_headline_is_the_served_subtitle_verbatim(
    spec: frame_plan.FrameSpec, captions: dict[str, frame_plan.Caption]
) -> None:
    header = captions[spec.header_caption]
    for locale in ("tr", "en-US"):
        served = body(REPO / "docs" / "legal" / "store" / "listing" / f"app-store.{locale}.yaml")
        assert header.text[locale][1] == served["fields"]["subtitle"], locale


# --- 2. the sizes are Apple's ------------------------------------------------------------------


def test_the_manifest_equals_apples_table() -> None:
    manifest = asc_assets.load_manifest(asc_assets.MANIFEST)
    slots = {entry.asset_id: entry for entry in manifest.entries}
    assert set(slots) == set(APPLE_TABLE)
    for slot, sizes in APPLE_TABLE.items():
        assert set(slots[slot].sizes) == set(sizes), slot
        assert slots[slot].required == (slot in APPLE_REQUIRED), slot
    raw = yaml.safe_load(asc_assets.MANIFEST.read_text(encoding="utf-8"))
    assert raw["reverified_on"] == "2026-10-29"


def test_the_targets_cover_six_point_nine_six_point_five_and_the_required_group(
    spec: frame_plan.FrameSpec,
) -> None:
    manifest = asc_assets.load_manifest(asc_assets.MANIFEST)
    slots = {entry.asset_id: entry for entry in manifest.entries}
    screenshot_slots = {
        e.asset_id for e in manifest.entries if e.placement_type == "APP_SCREENSHOT"
    }
    assert sorted(t.slot for t in spec.targets) == sorted(screenshot_slots)
    for target in spec.targets:
        assert target.size in slots[target.slot].sizes, target
    assert {t.size for t in spec.targets} >= {(1320, 2868), (1284, 2778), (1206, 2622)}
    assert spec.header_size in slots[spec.header_slot].sizes
    assert spec.capture_size == (1320, 2868)


# --- 3. the frame is the app's own and stays readable ------------------------------------------


def test_the_frames_follow_the_journey_and_name_screens_that_exist(
    spec: frame_plan.FrameSpec,
) -> None:
    ids = [frame.frame_id for frame in spec.frames]
    assert len(ids) == len(set(ids)) <= 10
    assert ids[0] == "bugun"
    for frame in spec.frames:
        assert (REPO / frame.file).is_file(), frame.file
        assert frame.appearance in {"light", "dark"}
        assert not asc_assets.banned_name(frame.capture_name), frame.capture_name
    assert {frame.appearance for frame in spec.frames} == {"light", "dark"}
    assert set(spec.header_phones) <= set(ids)


def test_the_colours_are_theme_tokens(spec: frame_plan.FrameSpec) -> None:
    theme = THEME.read_text(encoding="utf-8")
    for appearance, colours in spec.theme.items():
        for name, value in colours.items():
            assert f'"{value}"' in theme, (appearance, name, value)


def test_the_fonts_are_the_apps_own_ofl_faces_pinned_by_hash(spec: frame_plan.FrameSpec) -> None:
    import json

    deps = json.loads(MOBILE_PACKAGE.read_text(encoding="utf-8"))["dependencies"]
    for font in spec.fonts.values():
        assert font.package in deps, font.package
        assert font.licence == "OFL-1.1"
        assert re.fullmatch(r"[0-9a-f]{64}", font.sha256)


def test_a_font_whose_bytes_differ_from_the_pin_is_refused(
    tmp_path: Path, spec: frame_plan.FrameSpec
) -> None:
    font = spec.fonts["display"]
    planted = tmp_path / "node_modules" / font.package / font.file
    planted.parent.mkdir(parents=True)
    planted.write_bytes(b"not the pinned font")
    with pytest.raises(frame_plan.PlanError, match="sha256"):
        frame_plan.resolve_font(font, (tmp_path / "node_modules",))
    good = frame_plan.FontSpec(
        font.package, font.version, font.file, font.licence, hashlib.sha256(b"x").hexdigest()
    )
    planted.write_bytes(b"x")
    assert frame_plan.resolve_font(good, (tmp_path / "node_modules",)) == planted


def test_every_frame_lists_what_no_capture_may_show(spec: frame_plan.FrameSpec) -> None:
    joined = " ".join(spec.must_not_show)
    for needle in ("deneme", "Sentetik test metni", "phone number", "RED", "LogBox", "logo"):
        assert needle in joined, needle


@pytest.mark.parametrize("canvas", [(1320, 2868), (1284, 2778), (1206, 2622)])
def test_the_phone_sits_whole_inside_the_canvas_with_even_sides(
    spec: frame_plan.FrameSpec, canvas: tuple[int, int]
) -> None:
    width, height = canvas
    layout = frame_plan.frame_layout(spec, canvas, spec.capture_size)
    phone = layout.phone.body
    assert phone.x == width - (phone.x + phone.w), "left and right margins are equal"
    assert phone.x >= spec.layout_frame["side"] * width - 1
    assert phone.y > layout.headline.y + layout.headline.h, "the phone sits below the text"
    assert phone.y + phone.h <= height - spec.layout_frame["bottom"] * height + 1
    screen = layout.phone.screen
    assert abs(screen.h / screen.w - spec.capture_size[1] / spec.capture_size[0]) < 0.003
    assert phone.w >= 0.70 * width, "the app, not the margin, is the picture"


@pytest.mark.parametrize("canvas", [(1320, 2868), (1284, 2778), (1206, 2622)])
def test_caption_text_stays_readable(spec: frame_plan.FrameSpec, canvas: tuple[int, int]) -> None:
    width, _ = canvas
    layout = frame_plan.frame_layout(spec, canvas, spec.capture_size)
    # At the App Store's phone width the headline stays near 30 pt and the eyebrow
    # near 13 pt. The ratio to the canvas is what survives the store's scaling.
    assert layout.headline_px / width >= 0.075
    assert layout.eyebrow_px / width >= 0.030
    assert layout.headline.h >= 2 * layout.headline_px


def test_every_frame_of_a_size_puts_the_phone_in_the_same_place(
    spec: frame_plan.FrameSpec, captions: dict[str, frame_plan.Caption]
) -> None:
    first = frame_plan.frame_layout(spec, (1320, 2868), spec.capture_size)
    for _ in captions:
        assert frame_plan.frame_layout(spec, (1320, 2868), spec.capture_size) == first


def test_the_header_centres_three_equal_phones(spec: frame_plan.FrameSpec) -> None:
    width, height = spec.header_size
    layout = frame_plan.header_layout(spec, spec.header_size, spec.capture_size)
    bodies = [phone.body for phone in layout.phones]
    assert len(bodies) == 3
    assert len({(b.w, b.h, b.y) for b in bodies}) == 1, "same size, same line"
    gutters = {bodies[i + 1].x - (bodies[i].x + bodies[i].w) for i in range(2)}
    assert len(gutters) == 1
    left, right = bodies[0].x, width - (bodies[-1].x + bodies[-1].w)
    assert abs(left - right) <= 1
    assert left >= 0.2 * width, "the focal group sits in the centre"
    assert all(b.y + b.h <= height - spec.layout_header["bottom"] * height + 1 for b in bodies)


# --- 4. export reads served copy only, and real captures only ----------------------------------


def test_export_refuses_when_no_served_caption_exists(tmp_path: Path) -> None:
    with pytest.raises(frame_plan.CaptionsMissingError, match="legal lane"):
        frame_plan.load_served_captions(tmp_path)


def test_the_cli_export_exits_three_without_served_captions(tmp_path: Path) -> None:
    assert render_frames.main(["--export", "--repo", str(tmp_path)]) == 3


def test_a_capture_must_be_the_device_size_and_a_production_name(
    tmp_path: Path, spec: frame_plan.FrameSpec
) -> None:
    good = _png(tmp_path / "01-bugun.png", 1320, 2868)
    assert render_frames.check_capture(good, spec) == ()
    small = _png(tmp_path / "02-konusma.png", 1206, 2622)
    assert any("1320x2868" in p for p in render_frames.check_capture(small, spec))
    named = _png(tmp_path / "03-demo-not.png", 1320, 2868)
    assert any("name" in p for p in render_frames.check_capture(named, spec))
    assert any("no such" in p for p in render_frames.check_capture(tmp_path / "x.png", spec))


def test_the_paint_plan_holds_only_pinned_fonts_the_capture_and_theme_colours(
    tmp_path: Path, spec: frame_plan.FrameSpec, captions: dict[str, frame_plan.Caption]
) -> None:
    fonts = {name: tmp_path / f"{name}.ttf" for name in spec.fonts}
    capture = _png(tmp_path / "01-bugun.png", 1320, 2868)
    plan = frame_plan.frame_paint(
        spec,
        frame_plan.frame_layout(spec, (1320, 2868), spec.capture_size),
        captions["bugun"].text["tr"],
        capture,
        "light",
        fonts,
        tmp_path / "out.png",
    )
    assert (plan["width"], plan["height"]) == (1320, 2868)
    texts = [item for item in plan["items"] if item["kind"] == "text"]
    assert [item["text"] for item in texts] == list(captions["bugun"].text["tr"])
    assert {item["font"] for item in texts} <= {str(p) for p in fonts.values()}
    phones = [item for item in plan["items"] if item["kind"] == "phone"]
    assert [item["capture"] for item in phones] == [str(capture)]
    colours = {plan["ground"], *(item["color"] for item in texts)}
    assert colours <= set(spec.theme["light"].values())


# --- 5. the capture script ---------------------------------------------------------------------


class FakeRunner:
    """Records every command; writes a PNG of ``size`` for a screenshot."""

    def __init__(self, size: tuple[int, int]) -> None:
        self.calls: list[list[str]] = []
        self.size = size

    def run(self, argv: Sequence[str]) -> str:
        self.calls.append(list(argv))
        if argv[:4] == ["xcrun", "simctl", "io", argv[3]] and "screenshot" in argv:
            _png(Path(argv[-1]), *self.size)
        return ""


def _session(
    tmp_path: Path, spec: frame_plan.FrameSpec, runner: FakeRunner, **kw: str
) -> capture_frames.CaptureSession:
    return capture_frames.CaptureSession(
        spec=spec,
        udid=kw.get("udid", "F6552A9C-2E27-4D18-816E-1217B2087507"),
        locale=kw.get("locale", "tr"),
        out_dir=tmp_path / "captures" / kw.get("locale", "tr"),
        app_sha=kw.get("app_sha", "a" * 40),
        data_class=kw.get("data_class", "synthetic"),
        api_label="local dev API, mock SMS and attestation adapters",
        runner=runner,
        confirm=lambda _message: None,
        resolved=frozenset(kw["resolved"].split(",")) if kw.get("resolved") else frozenset(),
    )


def test_the_session_sets_a_clean_status_bar_and_each_frames_appearance(
    tmp_path: Path, spec: frame_plan.FrameSpec
) -> None:
    runner = FakeRunner(spec.capture_size)
    session = _session(tmp_path, spec, runner, resolved="INT-588")
    capture_frames.prepare(session)
    shots = [capture_frames.shoot(session, frame) for frame in spec.frames]
    flat = [" ".join(call) for call in runner.calls]
    udid = session.udid
    assert any(
        c.startswith(f"xcrun simctl status_bar {udid} override") and "--time 09:41" in c
        for c in flat
    )
    dark = next(f for f in spec.frames if f.appearance == "dark")
    assert f"xcrun simctl ui {udid} appearance dark" in flat
    assert f"xcrun simctl ui {udid} appearance light" in flat
    assert [shot.name for shot in shots] == [frame.capture_name for frame in spec.frames]
    assert dark.capture_name in {shot.name for shot in shots}
    assert all(len(shot.sha256) == 64 for shot in shots)


def test_a_screenshot_of_the_wrong_size_is_refused_and_removed(
    tmp_path: Path, spec: frame_plan.FrameSpec
) -> None:
    runner = FakeRunner((1206, 2622))
    session = _session(tmp_path, spec, runner)
    with pytest.raises(capture_frames.CaptureError, match="1320x2868"):
        capture_frames.shoot(session, spec.frames[0])
    assert not (session.out_dir / spec.frames[0].capture_name).exists()


@pytest.mark.parametrize(
    ("field", "value", "needle"),
    [
        ("data_class", "real_phi", "synthetic"),
        ("app_sha", "main", "sha"),
        ("locale", "de", "locale"),
    ],
)
def test_the_session_refuses_anything_but_synthetic_data_from_a_known_build(
    tmp_path: Path, spec: frame_plan.FrameSpec, field: str, value: str, needle: str
) -> None:
    with pytest.raises(capture_frames.CaptureError, match=needle):
        _session(tmp_path, spec, FakeRunner(spec.capture_size), **{field: value})


def test_provenance_records_hashes_and_the_build_never_a_value(
    tmp_path: Path, spec: frame_plan.FrameSpec
) -> None:
    runner = FakeRunner(spec.capture_size)
    session = _session(tmp_path, spec, runner, resolved="INT-588")
    shots = [capture_frames.shoot(session, frame) for frame in spec.frames[:2]]
    path = capture_frames.write_provenance(session, shots, captured_on="2026-10-29")
    record = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert record["data_class"] == "synthetic"
    assert record["app_sha"] == "a" * 40
    assert record["device"] == spec.capture_device
    assert [row["file"] for row in record["captures"]] == [s.name for s in shots]
    for row in record["captures"]:
        data = (session.out_dir / row["file"]).read_bytes()
        assert row["sha256"] == hashlib.sha256(data).hexdigest()
    assert not re.search(r"\+?90\s?5\d{2}", path.read_text(encoding="utf-8"))
    assert record["app_state"] == {"voice": "off", "start_mode": "typed"}


def test_a_frame_waiting_for_an_issue_is_refused_until_the_build_has_it(
    tmp_path: Path, spec: frame_plan.FrameSpec
) -> None:
    """Legal review B6: the typed step still shows intake.open.hint's offer to speak
    until INT-588 lands, so that frame waits for it."""
    waiting = spec.frame("konusma")
    assert waiting.waits_for is not None and waiting.waits_for.startswith("INT-588")
    runner = FakeRunner(spec.capture_size)
    with pytest.raises(capture_frames.CaptureError, match="INT-588"):
        capture_frames.shoot(_session(tmp_path, spec, runner), waiting)
    assert not any("screenshot" in call for call in runner.calls)
    landed = _session(tmp_path / "landed", spec, runner, resolved="INT-588")
    assert capture_frames.shoot(landed, waiting).name == waiting.capture_name


def test_the_store_builds_state_is_set_before_the_first_shot(
    tmp_path: Path, spec: frame_plan.FrameSpec
) -> None:
    assert spec.app_state == {"voice": "off", "start_mode": "typed"}
    asked: list[str] = []
    session = _session(tmp_path, spec, FakeRunner(spec.capture_size))
    session.confirm = asked.append
    capture_frames.prepare(session)
    assert any("voice off" in message and "start_mode typed" in message for message in asked)


VOICE_SURFACES = ("DialogueIntake.tsx", "VoiceNote.tsx", "DevVoiceBanner.tsx")
_KEY = re.compile(r'"([a-z][A-Za-z0-9]*(?:\.[A-Za-z0-9]+)+)"')


def _keys_in(path: Path, known: set[str]) -> set[str]:
    return {key for key in _KEY.findall(path.read_text(encoding="utf-8")) if key in known}


def test_no_caption_rests_on_a_key_only_the_voice_surfaces_render() -> None:
    """Legal review: a store build renders neither the voice dialogue, the voice
    note nor the dev voice banner. A caption sourced from a key that only those
    render would describe a screen the store build cannot show."""
    tr = (REPO / "apps/mobile/src/lib/i18n/tr.ts").read_text(encoding="utf-8")
    known = set(re.findall(r'^\s*"([^"]+)":', tr, flags=re.MULTILINE))
    src = REPO / "apps/mobile/src"
    files = [
        p
        for p in src.rglob("*.ts*")
        if "i18n" not in p.parts and ".test." not in p.name and "e2e" not in p.parts
    ]
    voice = set().union(*(_keys_in(p, known) for p in files if p.name in VOICE_SURFACES))
    elsewhere = set().union(*(_keys_in(p, known) for p in files if p.name not in VOICE_SURFACES))
    voice_only = voice - elsewhere
    assert voice_only, "the guard is armed: the voice surfaces render keys of their own"
    captions = frame_plan.load_captions(CAPTION_DRAFT)
    cited = {
        key for c in captions.values() for key in _KEY.findall(f'"{c.source}"') if key in known
    }
    cited |= {
        token.strip(",;()")
        for c in captions.values()
        for token in c.source.split()
        if token.strip(",;()") in known
    }
    assert cited, "captions cite app keys"
    assert cited.isdisjoint(voice_only), sorted(cited & voice_only)
