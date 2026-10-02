# ruff: noqa: E501 -- the patch strings are TypeScript fragments matched byte-for-byte against upstream.
"""Build the Önvizit store-screenshot editor (INT-425).

The editor is the app-store-screenshots skill's own Next.js template
(github.com/ParthJadhav/app-store-screenshots, MIT), pinned to TEMPLATE_COMMIT.
It is not vendored into this repo: this script copies the upstream template to
a directory you choose, applies the small "onvizit-clinical" theme patch below,
and drops in the committed project file, captures and brand assets.

    git clone https://github.com/ParthJadhav/app-store-screenshots /tmp/ass
    git -C /tmp/ass checkout 8bd7520
    python3 docs/store/screenshots/tools/build_editor.py /tmp/ass /tmp/onvizit-editor
    cd /tmp/onvizit-editor && pnpm install --ignore-workspace && pnpm dev

The theme patch changes presentation only: a flat background with no blobs or
gradients, a sentence-case eyebrow (no case transform, so Turkish İ/ı survive),
platform type (SF Pro on Apple frames, Roboto on Android frames), a neutral
bezel, and a flat feature graphic. Every patch site is asserted to match once.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageOps

TEMPLATE_COMMIT = "8bd7520"
HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent

THEME_ID = "onvizit-clinical"
FONT_ID = "platform-native"


def patch(path: Path, pairs: list[tuple[str, str, int]]) -> None:
    text = path.read_text(encoding="utf-8")
    for old, new, count in pairs:
        found = text.count(old)
        if found != count:
            raise SystemExit(
                f"{path.name}: expected {count} match(es), found {found}: {old[:60]!r}"
            )
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")


def patch_types(src: Path) -> None:
    patch(
        src / "lib/types.ts",
        [
            (
                "export type Slide = {\n  id: string;",
                "export type Slide = {\n  id: string;\n"
                "  /** Overrides the layout's caption alignment (onvizit-clinical sets left). */\n"
                '  captionAlign?: "left" | "center";',
                1,
            ),
            (
                '  | "vintage-travel-poster";',
                '  | "vintage-travel-poster"\n  | "onvizit-clinical";',
                1,
            ),
            (
                '  | "futura"\n  | "self-hosted";',
                '  | "futura"\n  | "platform-native"\n  | "self-hosted";',
                1,
            ),
        ],
    )


def patch_constants(src: Path) -> None:
    patch(
        src / "lib/constants.ts",
        [
            (
                '  "futura": { name: "Futura", family: "Futura, \'Trebuchet MS\', sans-serif" },',
                '  "futura": { name: "Futura", family: "Futura, \'Trebuchet MS\', sans-serif" },\n'
                "  // SF Pro on Apple decks, Roboto on Android decks (see platformFont).\n"
                '  "platform-native": { name: "Platform (SF Pro / Roboto)", family: "PLATFORM_NATIVE" },',
                1,
            ),
            (
                "export function themeById(",
                "/** Resolves the platform-native sentinel to the platform's own UI face. */\n"
                "export function platformFont(family: string | undefined, device: Device): string | undefined {\n"
                '  if (family !== "PLATFORM_NATIVE") return family;\n'
                '  if (device.startsWith("android") || device === "feature-graphic") {\n'
                '    return "var(--font-roboto), Roboto, sans-serif";\n'
                "  }\n"
                '  return \'-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", system-ui, sans-serif\';\n'
                "}\n\n"
                "export function themeById(",
                1,
            ),
            (
                "export const THEMES: Record<string, Theme> = {",
                "export const THEMES: Record<string, Theme> = {\n"
                "  // Önvizit (INT-425): the app's own tokens (apps/mobile/src/lib/theme.ts,\n"
                "  // INT-422): systemGroupedBackground, label, one teal accent. Flat only.\n"
                f'  "{THEME_ID}": {{\n'
                f'    id: "{THEME_ID}",\n'
                '    name: "Önvizit clinical",\n'
                '    bg: "#F2F2F7",\n'
                '    bgAlt: "#000000",\n'
                '    fg: "#000000",\n'
                '    fgAlt: "#FFFFFF",\n'
                '    accent: "#0B7366",\n'
                '    accentAlt: "#4FC3B1",\n'
                '    muted: "#48484A",\n'
                "  },",
                1,
            ),
        ],
    )


def patch_layout(src: Path) -> None:
    patch(
        src / "app/layout.tsx",
        [
            (
                'import { Inter } from "next/font/google";',
                'import { Inter, Roboto } from "next/font/google";',
                1,
            ),
            (
                'const font = Inter({ subsets: ["latin"] });',
                'const font = Inter({ subsets: ["latin"] });\n'
                "// Android frames set in Roboto; latin-ext carries the Turkish letters.\n"
                'const roboto = Roboto({ subsets: ["latin", "latin-ext"], weight: ["500", "700"], variable: "--font-roboto" });',
                1,
            ),
            ('<html lang="en">', '<html lang="tr" className={roboto.variable}>', 1),
        ],
    )


CAPTION_BRANCH = """  const unit = Math.min(cW, cH);
  if (theme.id === "onvizit-clinical") {
    // Önvizit: sentence-case eyebrow (no case transform: Turkish İ/ı), one
    // headline weight, tight display leading, no shadow or emphasis colour.
    return (
      <div style={{ textAlign: align === "left" ? "start" : align, position: "relative", width: "100%" }}>
        <EditableText
          value={pickText(slide.label, locale)}
          editable={editable}
          onChange={edit?.onLabelChange}
          onFocus={onFocus}
          style={{ fontSize: unit * 0.034 * labelScale, fontWeight: 600, color: accent, marginBottom: unit * 0.02 }}
        />
        <EditableText
          value={pickText(slide.headline, locale)}
          editable={editable}
          multiline
          onChange={edit?.onHeadlineChange}
          onFocus={onFocus}
          style={{ fontSize: unit * 0.085 * headlineScale, fontWeight: 700, lineHeight: 1.06, letterSpacing: "-0.02em", color: fg }}
        />
      </div>
    );
  }
  return (
    // "start" rather than "left\""""

FEATURE_BRANCH = """  const { headlineScale, appNameScale } = slideFontScales(slide);
  if (theme.id === "onvizit-clinical") {
    // Flat 1024×500 banner: the app icon, the name, one line of benefit.
    const iconSrc = appIcon ? img(appIcon) : "";
    return (
      <div style={{ width: "100%", height: "100%", background: theme.bg, display: "flex", alignItems: "center", gap: cW * 0.045, padding: `0 ${cW * 0.08}px` }}>
        {iconSrc && (
          <img src={iconSrc} alt="" draggable={false} style={{ width: cW * 0.19, height: cW * 0.19, borderRadius: cW * 0.19 * 0.2237, flexShrink: 0 }} />
        )}
        <div>
          <div style={{ fontSize: cW * 0.074 * appNameScale, fontWeight: 700, letterSpacing: "-0.02em", color: theme.fg, lineHeight: 1.05 }}>{appName || "App"}</div>
          <div style={{ fontSize: cW * 0.036 * headlineScale, fontWeight: 500, color: theme.muted, marginTop: cW * 0.016, lineHeight: 1.25, whiteSpace: "pre-wrap" }}>
            {pickText(slide.headline, locale)}
          </div>
        </div>
      </div>
    );
  }
  const inverted = slide.inverted ?? true;"""


def patch_canvas(src: Path) -> None:
    patch(
        src / "components/editor/slide-canvas.tsx",
        [
            ("  carPlayW,\n", "  carPlayW,\n  platformFont,\n", 1),
            (
                '  const unit = Math.min(cW, cH);\n  return (\n    // "start" rather than "left"',
                CAPTION_BRANCH,
                1,
            ),
            (
                '  const inverted = !!slide.inverted;\n  return (\n    <div\n      style={{\n        position: "absolute",\n        inset: 0,\n        overflow: "hidden",\n        background: backgroundFor(theme, inverted, slide.backgroundColor),',
                "  const inverted = !!slide.inverted;\n"
                '  if (theme.id === "onvizit-clinical") {\n'
                "    // Flat ground, no gradient and no blobs.\n"
                '    return <div style={{ position: "absolute", inset: 0, background: slide.backgroundColor || (inverted ? theme.bgAlt : theme.bg) }} />;\n'
                "  }\n"
                '  return (\n    <div\n      style={{\n        position: "absolute",\n        inset: 0,\n        overflow: "hidden",\n        background: backgroundFor(theme, inverted, slide.backgroundColor),',
                1,
            ),
            (
                "  const { headlineScale, appNameScale } = slideFontScales(slide);\n  const inverted = slide.inverted ?? true;",
                FEATURE_BRANCH,
                1,
            ),
            (
                '        align={captionRect.align || "center"}',
                '        align={slide.captionAlign || captionRect.align || "center"}',
                1,
            ),
            (
                '  const { cW, cH } = getCanvas(device, orientation);\n\n  if (slide.layout === "feature-graphic"',
                '  const { cW, cH } = getCanvas(device, orientation);\n  fontFamily = platformFont(fontFamily, device);\n\n  if (slide.layout === "feature-graphic"',
                1,
            ),
            (
                "  const { cW, cH } = getCanvas(device, orientation);\n  const totalW",
                "  const { cW, cH } = getCanvas(device, orientation);\n  fontFamily = platformFont(fontFamily, device);\n  const totalW",
                1,
            ),
        ],
    )


def install_assets(dst: Path) -> None:
    public = dst / "public"
    # Neutral bezel: the template's mockup, desaturated. Same pixels and
    # geometry, so PHONE_SCREEN needs no re-measuring.
    bezel = Image.open(public / "mockup.png").convert("RGBA")
    grey = ImageOps.grayscale(bezel.convert("RGB")).point(lambda v: min(255, int(v * 1.08)))
    neutral = Image.merge("RGBA", (grey, grey, grey, bezel.getchannel("A")))
    neutral.save(public / "mockup.png")
    for name in ("onvizit-icon.png", "onvizit-icon-rounded.png"):
        shutil.copyfile(PROJECT / "assets" / name, public / name)
    shots = public / "screenshots" / "captures"
    shots.mkdir(parents=True, exist_ok=True)
    for png in sorted((PROJECT / "captures").glob("*.png")):
        shutil.copyfile(png, shots / png.name)
    project = json.loads((PROJECT / "app-store-screenshots.json").read_text(encoding="utf-8"))
    (dst / "app-store-screenshots.json").write_text(
        json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main(template_repo: str, dst_dir: str) -> None:
    template = Path(template_repo) / "skills" / "app-store-screenshots" / "template"
    dst = Path(dst_dir)
    if dst.exists() and any(dst.iterdir()):
        raise SystemExit(f"{dst} is not empty")
    shutil.copytree(template, dst, dirs_exist_ok=True)
    src = dst / "src"
    patch_types(src)
    patch_constants(src)
    patch_layout(src)
    patch_canvas(src)
    install_assets(dst)
    print(f"editor ready in {dst} (template {TEMPLATE_COMMIT}, theme {THEME_ID})")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: build_editor.py <app-store-screenshots checkout> <empty target dir>"
        )
    main(sys.argv[1], sys.argv[2])
