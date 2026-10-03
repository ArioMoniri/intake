/**
 * INT-478 (GitHub #820): OS-level capture protection stays active while any
 * protected screen is mounted, and is released only when the last one goes.
 *
 * The defect: every protected screen passed expo-screen-capture the same key,
 * `intake-clinical`, and the library tracks a SET of keys. The first protected
 * screen to unmount emptied the set and released protection for all of them:
 * closing the doctor-link issue screen left the share centre under it
 * capturable. The lock counts screens itself and asks the OS once for the
 * first and releases once after the last.
 *
 * The OS is modelled here with expo-screen-capture's own key-set semantics
 * (node_modules/expo-screen-capture/build/ScreenCapture.js), so the defect is
 * reproduced, not described.
 */
import { describe, expect, it } from "vitest";

import { createCaptureLock, type CaptureGuard } from "./captureLock";

const KEY = "intake-clinical";

/**
 * The OS window flag behind expo-screen-capture's key set: prevent adds the
 * key and protects when the set was empty of it; allow deletes the key and
 * releases when the set is empty.
 */
function expoLikeOs() {
  const tags = new Set<string>();
  const os = { protected: false, prevents: 0, allows: 0 };
  return {
    os,
    prevent: async (key: string) => {
      if (!tags.has(key)) {
        tags.add(key);
        os.prevents += 1;
        os.protected = true;
      }
    },
    allow: async (key: string) => {
      tags.delete(key);
      if (tags.size === 0) {
        os.allows += 1;
        os.protected = false;
      }
    },
  };
}

function guardOver(expo: ReturnType<typeof expoLikeOs>): CaptureGuard {
  return { prevent: () => expo.prevent(KEY), allow: () => expo.allow(KEY) };
}

const flush = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

describe("the defect, reproduced: one shared key, released by the first screen to close", () => {
  it("near miss (the old guard): shares and issue-link each ask with the same key; closing issue-link releases shares", async () => {
    const expo = expoLikeOs();
    // The old hook, once per screen: prevent on mount, allow on unmount.
    await expo.prevent(KEY); // shares
    await expo.prevent(KEY); // issue-link, pushed over it
    await expo.allow(KEY); // issue-link closes
    expect(expo.os.protected).toBe(false); // shares is still on screen
  });
});

describe("the lock: protected while any screen holds it", () => {
  it("open A and B, close A: still protected", async () => {
    const expo = expoLikeOs();
    const lock = createCaptureLock(guardOver(expo));
    const shares = lock.acquire();
    const issueLink = lock.acquire();
    await flush();
    expect(expo.os.protected).toBe(true);
    issueLink();
    await flush();
    expect(expo.os.protected).toBe(true);
    expect(expo.os.allows).toBe(0);
    expect(lock.held()).toBe(true);
    shares();
    await flush();
    expect(expo.os.protected).toBe(false);
  });

  it("near miss: close both, and protection is released, once", async () => {
    const expo = expoLikeOs();
    const lock = createCaptureLock(guardOver(expo));
    const a = lock.acquire();
    const b = lock.acquire();
    a();
    b();
    await flush();
    expect(expo.os.protected).toBe(false);
    expect(expo.os.allows).toBe(1);
    expect(lock.held()).toBe(false);
  });

  it("the OS is asked once for the first screen, not once per screen", async () => {
    const calls: string[] = [];
    const lock = createCaptureLock({
      prevent: async () => void calls.push("prevent"),
      allow: async () => void calls.push("allow"),
    });
    const release = [lock.acquire(), lock.acquire(), lock.acquire()];
    for (const r of release) {
      r();
    }
    await flush();
    expect(calls).toEqual(["prevent", "allow"]);
  });

  it("a release counts once: a second call cannot drop another screen's hold", async () => {
    const expo = expoLikeOs();
    const lock = createCaptureLock(guardOver(expo));
    const a = lock.acquire();
    lock.acquire();
    a();
    a();
    await flush();
    expect(expo.os.protected).toBe(true);
    expect(lock.held()).toBe(true);
  });

  it("a screen that opens after the last one closed asks again, in order", async () => {
    const calls: string[] = [];
    const lock = createCaptureLock({
      prevent: async () => void calls.push("prevent"),
      allow: async () => void calls.push("allow"),
    });
    lock.acquire()();
    lock.acquire();
    await flush();
    // The release is sent before the new request, so the last word is "prevent".
    expect(calls).toEqual(["prevent", "allow", "prevent"]);
    expect(lock.held()).toBe(true);
  });

  it("a remount (React's development double effect) leaves the screen protected", async () => {
    const expo = expoLikeOs();
    const lock = createCaptureLock(guardOver(expo));
    lock.acquire()(); // mount, then the development cleanup
    lock.acquire(); // the second mount
    await flush();
    expect(expo.os.protected).toBe(true);
  });
});

describe("capability detect: a runtime without the module neither crashes nor miscounts", () => {
  it("a refused request and a refused release are swallowed, and the count still governs", async () => {
    const calls: string[] = [];
    const lock = createCaptureLock({
      prevent: () => {
        calls.push("prevent");
        return Promise.reject(new Error("unavailable"));
      },
      allow: () => {
        calls.push("allow");
        return Promise.reject(new Error("unavailable"));
      },
    });
    const a = lock.acquire();
    const b = lock.acquire();
    a();
    expect(lock.held()).toBe(true);
    b();
    await flush();
    expect(calls).toEqual(["prevent", "allow"]);
    expect(lock.held()).toBe(false);
  });

  it("a guard that throws synchronously is treated as a refusal", async () => {
    const lock = createCaptureLock({
      prevent: () => {
        throw new Error("no native module");
      },
      allow: () => {
        throw new Error("no native module");
      },
    });
    const release = lock.acquire();
    expect(lock.held()).toBe(true);
    release();
    await flush();
    expect(lock.held()).toBe(false);
  });
});
