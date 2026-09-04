/**
 * Wires the pure prebaked-clip resolver (`prebakedClips.ts`) to the two real,
 * platform-bound pieces it takes as arguments: the generated `hash → assetId`
 * index (which statically imports the bundled `.wav` clips so Metro serves
 * them) and `Image.resolveAssetSource`, which turns an asset id into the URI
 * expo-audio plays — an `http://<metro>/assets/…` URL in dev, a bundled file in
 * a release build, with no extra native module needed.
 *
 * This is the one module that touches both `react-native` and the wav bundle,
 * so it is never imported by a vitest test; `prebakedClips.ts` holds the logic
 * and is unit-tested with both dependencies injected.
 */
import { Image } from "react-native";

import { prebakedClips } from "@/assets/dialogue-clips/index.generated";
import {
  makePrebakedResolver,
  prebakedClipCount,
  type PrebakedClipResolver,
} from "./prebakedClips";

/** How many ElevenLabs clips this build bundles (0 before the generator runs). */
export const prebakedDemoClipCount: number = prebakedClipCount(prebakedClips);

/** The store's prebaked seam, over the bundled index and the RN asset resolver. */
export const resolvePrebakedClip: PrebakedClipResolver = makePrebakedResolver(
  prebakedClips,
  (assetId) => Image.resolveAssetSource(assetId)?.uri ?? null,
);
