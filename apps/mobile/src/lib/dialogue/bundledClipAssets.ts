/**
 * The bundled clips Metro found at build time (INT-440). Expo-bound: Metro's
 * `require.context` resolves `apps/mobile/assets/clips/<context>/<hash>.wav`
 * into asset module ids when the bundle is built, so a clip rendered by
 * scripts/voice/render_bundled_clips.py is in the app with no synthesis and no
 * network on the turn.
 *
 * The directory is gitignored apart from its .gitignore (ADR-028: the
 * vendor-terms question is a human blocker, so rendered clips are a dev build
 * input and never committed). An unrendered tree bundles an empty map, and the
 * dialogue speaks through the live lanes exactly as before.
 */
import { bundledClipAddressFromFile } from "./bundledClips";

const context = require.context("../../../assets/clips", true, /^\.\/[a-z]+\/[0-9a-f]{64}\.wav$/);

function load(): ReadonlyMap<string, number> {
  const assets = new Map<string, number>();
  for (const file of context.keys()) {
    const address = bundledClipAddressFromFile(file);
    if (address !== null) {
      assets.set(address, context(file) as number);
    }
  }
  return assets;
}

/** `<context>/<clip_text_hash>` → the asset module id createAudioPlayer accepts. */
export const BUNDLED_CLIP_ASSETS: ReadonlyMap<string, number> = load();
