/**
 * The prebaked-clip resolver (INT-demo ElevenLabs dev lane), pure and
 * node-testable. Given a question's scripted text, it answers with the URI of
 * the bundled ElevenLabs clip for that EXACT text, or `null` when there is no
 * bundled clip — in which case the clip store falls through to the live dev
 * TTS lane exactly as before.
 *
 * The two effectful pieces — the generated `hash → assetId` index (which
 * statically `import`s the `.wav` assets, so Metro bundles them) and turning an
 * asset id into a playable URI (`Image.resolveAssetSource`) — are INJECTED, so
 * this module imports neither `react-native` nor the wav bundle and runs under
 * vitest. `clips.ts` wires the real index and resolver in.
 *
 * Verbatim by construction (invariant 10): the lookup key is
 * `clipTextHash(text)`, so a clip only plays for the text it was synthesised
 * from. A word changed in the catalogue changes the hash, the lookup misses,
 * and the live lane speaks the new wording — a stale clip can never be served
 * under moved text.
 *
 * Never throws: a resolver on the speech path must degrade to the live lane, so
 * every failure (a text the guard would reject, a missing asset, a resolver
 * that returns nothing) is a `null`, never an exception that would surface as a
 * dead turn.
 */
import { clipTextHash } from "./clipHash";

/** The generated map from a clip's text hash to its bundled asset id. */
export type PrebakedClipIndex = Readonly<Record<string, number>>;

/** Turns a bundled asset id into a playable URI, or `null` if it cannot. */
export type AssetUriResolver = (assetId: number) => string | null;

/** The store's prebaked seam: `(name, text) → uri | null`. */
export type PrebakedClipResolver = (name: string, text: string) => Promise<string | null>;

/**
 * Build a resolver over a concrete index and asset-uri function. Both are
 * arguments so the whole thing is a pure unit test away from the bundle.
 */
export function makePrebakedResolver(
  index: PrebakedClipIndex,
  toUri: AssetUriResolver,
): PrebakedClipResolver {
  return async (_name: string, text: string): Promise<string | null> => {
    let assetId: number | undefined;
    try {
      assetId = index[clipTextHash(text)];
    } catch {
      return null; // a text the hash cannot take is simply not prebaked
    }
    if (assetId === undefined) {
      return null;
    }
    try {
      return toUri(assetId);
    } catch {
      return null; // resolution failed — fall through to the live lane
    }
  };
}

/** How many clips an index carries — for the dev voice banner/diagnostic. */
export function prebakedClipCount(index: PrebakedClipIndex): number {
  return Object.keys(index).length;
}
