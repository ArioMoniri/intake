/**
 * The prebaked resolver is on the speech path, so its whole contract is: serve
 * the bundled clip for the EXACT text (invariant 10), miss cleanly for anything
 * else, and NEVER throw (a resolver that throws would end a turn the live lane
 * could have carried).
 */
import { describe, expect, it, vi } from "vitest";

import { clipTextHash } from "./clipHash";
import { makePrebakedResolver, prebakedClipCount } from "./prebakedClips";

const TEXT = "Bu şikâyetiniz ne zamandır var?";
const index = { [clipTextHash(TEXT)]: 42 } as const;
const toUri = (assetId: number) => `asset://${assetId}`;

describe("makePrebakedResolver", () => {
  it("returns the bundled clip's uri for the exact scripted text", async () => {
    const resolve = makePrebakedResolver(index, toUri);
    expect(await resolve("q_duration.wav", TEXT)).toBe("asset://42");
  });

  it("misses (null) when the text is not bundled — the live lane takes over", async () => {
    const resolve = makePrebakedResolver(index, toUri);
    expect(await resolve("q_onset.wav", "Şikâyetiniz nasıl başladı?")).toBeNull();
  });

  it("a single changed character misses — a stale clip never plays under moved text", async () => {
    const resolve = makePrebakedResolver(index, toUri);
    expect(await resolve("q_duration.wav", `${TEXT} `)).toBeNull();
  });

  it("never throws when the asset resolver fails — it degrades to null", async () => {
    const resolve = makePrebakedResolver(index, () => {
      throw new Error("resolveAssetSource blew up");
    });
    await expect(resolve("q_duration.wav", TEXT)).resolves.toBeNull();
  });

  it("treats a resolver that returns null (asset not registered) as a miss", async () => {
    const resolve = makePrebakedResolver(index, () => null);
    expect(await resolve("q_duration.wav", TEXT)).toBeNull();
  });

  it("does not resolve when the asset id is absent, without calling the uri resolver", async () => {
    const toUriSpy = vi.fn(toUri);
    const resolve = makePrebakedResolver({}, toUriSpy);
    expect(await resolve("q_duration.wav", TEXT)).toBeNull();
    expect(toUriSpy).not.toHaveBeenCalled();
  });

  it("prebakedClipCount reports the number of bundled clips", () => {
    expect(prebakedClipCount(index)).toBe(1);
    expect(prebakedClipCount({})).toBe(0);
  });
});
