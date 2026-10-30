/**
 * INT-583 — the registration run over fake native and network ports.
 *
 * What it pins: the system prompt is reached only when the patient asked; a
 * refusal or a native failure never throws to the screen; the token sent is
 * the native APNs token and passes the shape check first; and a session the
 * server cannot bind to a device stops the attempts until the next sign-in.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import type { PushTokenResult } from "./api";
import type { PushPermission } from "./plan";
import { resetPushRegistration, syncPushRegistration, type PushPorts } from "./registration";

/** An APNs-shaped device token: 32 bytes of lower-case hex, low entropy on purpose. */
const TOKEN = "b2".repeat(32);

function ports(
  options: {
    permission?: PushPermission;
    afterPrompt?: PushPermission;
    token?: string | null;
    put?: PushTokenResult;
  } = {},
) {
  const fake = {
    readPermission: vi.fn(async () => options.permission ?? "granted"),
    requestPermission: vi.fn(async () => options.afterPrompt ?? "granted"),
    deviceToken: vi.fn(async () => (options.token === undefined ? TOKEN : options.token)),
    putToken: vi.fn(async (_token: string) => options.put ?? ({ ok: true } as PushTokenResult)),
    deleteToken: vi.fn(async () => ({ ok: true }) as PushTokenResult),
  };
  return fake satisfies PushPorts;
}

afterEach(() => {
  resetPushRegistration();
});

describe("silent registration at app start", () => {
  it("granted: the native token is sent, no prompt is shown", async () => {
    const fake = ports({ permission: "granted" });
    expect(await syncPushRegistration(fake, { asked: false })).toEqual({
      permission: "granted",
      outcome: "registered",
    });
    expect(fake.requestPermission).not.toHaveBeenCalled();
    expect(fake.putToken).toHaveBeenCalledWith(TOKEN);
  });

  it("undetermined: nothing is asked and nothing is sent", async () => {
    const fake = ports({ permission: "undetermined" });
    expect(await syncPushRegistration(fake, { asked: false })).toEqual({
      permission: "undetermined",
      outcome: "skipped",
    });
    expect(fake.requestPermission).not.toHaveBeenCalled();
    expect(fake.deviceToken).not.toHaveBeenCalled();
    expect(fake.putToken).not.toHaveBeenCalled();
  });

  it("denied: nothing is sent, and the state is returned for the screen to explain", async () => {
    const fake = ports({ permission: "denied" });
    expect(await syncPushRegistration(fake, { asked: false })).toEqual({
      permission: "denied",
      outcome: "skipped",
    });
    expect(fake.putToken).not.toHaveBeenCalled();
  });

  it("a shared clinic device registers nothing even with permission granted", async () => {
    const fake = ports({ permission: "granted" });
    expect(await syncPushRegistration(fake, { asked: false, sharedDevice: true })).toEqual({
      permission: "granted",
      outcome: "skipped",
    });
    expect(fake.deviceToken).not.toHaveBeenCalled();
    expect(fake.putToken).not.toHaveBeenCalled();
  });
});

describe("the patient taps the enable button", () => {
  it("undetermined then granted: one prompt, then the token is sent", async () => {
    const fake = ports({ permission: "undetermined", afterPrompt: "granted" });
    expect(await syncPushRegistration(fake, { asked: true })).toEqual({
      permission: "granted",
      outcome: "registered",
    });
    expect(fake.requestPermission).toHaveBeenCalledTimes(1);
    expect(fake.putToken).toHaveBeenCalledWith(TOKEN);
  });

  it("undetermined then refused: explained, not thrown, nothing sent", async () => {
    const fake = ports({ permission: "undetermined", afterPrompt: "denied" });
    expect(await syncPushRegistration(fake, { asked: true })).toEqual({
      permission: "denied",
      outcome: "denied",
    });
    expect(fake.putToken).not.toHaveBeenCalled();
  });

  it("undetermined then still undetermined: no second prompt (near miss)", async () => {
    const fake = ports({ permission: "undetermined", afterPrompt: "undetermined" });
    expect(await syncPushRegistration(fake, { asked: true })).toEqual({
      permission: "undetermined",
      outcome: "skipped",
    });
    expect(fake.requestPermission).toHaveBeenCalledTimes(1);
  });

  it("already denied: iOS will not ask again, so the screen explains Settings", async () => {
    const fake = ports({ permission: "denied" });
    expect(await syncPushRegistration(fake, { asked: true })).toEqual({
      permission: "denied",
      outcome: "denied",
    });
    expect(fake.requestPermission).not.toHaveBeenCalled();
  });
});

describe("the screen learns the permission before the token work", () => {
  it("reports the read permission once, before anything is sent", async () => {
    const fake = ports({ permission: "granted" });
    const seen: string[] = [];
    fake.putToken.mockImplementationOnce(async () => {
      seen.push("put");
      return { ok: true };
    });
    await syncPushRegistration(fake, {
      asked: false,
      onPermission: (permission) => seen.push(permission),
    });
    expect(seen).toEqual(["granted", "put"]);
  });

  it("after a prompt it reports the answer, not the earlier undetermined", async () => {
    const fake = ports({ permission: "undetermined", afterPrompt: "denied" });
    const seen: string[] = [];
    await syncPushRegistration(fake, {
      asked: true,
      onPermission: (permission) => seen.push(permission),
    });
    expect(seen).toEqual(["denied"]);
  });

  it("a native token call that never settles still leaves the permission reported", async () => {
    const fake = ports({ permission: "granted" });
    fake.deviceToken.mockReturnValueOnce(new Promise<string | null>(() => undefined));
    const seen: string[] = [];
    void syncPushRegistration(fake, {
      asked: false,
      onPermission: (permission) => seen.push(permission),
    });
    await vi.waitFor(() => expect(seen).toEqual(["granted"]));
    expect(fake.putToken).not.toHaveBeenCalled();
  });
});

describe("failures stay inside the run", () => {
  it("a native permission read that throws reads as unavailable", async () => {
    const fake = ports();
    fake.readPermission.mockRejectedValueOnce(new Error("native module missing"));
    expect(await syncPushRegistration(fake, { asked: true })).toEqual({
      permission: "unavailable",
      outcome: "skipped",
    });
  });

  it("a prompt that throws reads as unavailable and sends nothing", async () => {
    const fake = ports({ permission: "undetermined" });
    fake.requestPermission.mockRejectedValueOnce(new Error("prompt failed"));
    expect(await syncPushRegistration(fake, { asked: true })).toEqual({
      permission: "unavailable",
      outcome: "skipped",
    });
    expect(fake.putToken).not.toHaveBeenCalled();
  });

  it("a native token call that throws is a failed run, not a crash", async () => {
    const fake = ports();
    fake.deviceToken.mockRejectedValueOnce(new Error("aps-environment missing"));
    expect(await syncPushRegistration(fake, { asked: false })).toEqual({
      permission: "granted",
      outcome: "failed",
    });
    expect(fake.putToken).not.toHaveBeenCalled();
  });

  it("no native token is a failed run", async () => {
    const fake = ports({ token: null });
    expect((await syncPushRegistration(fake, { asked: false })).outcome).toBe("failed");
    expect(fake.putToken).not.toHaveBeenCalled();
  });

  it("a malformed native token is never sent (near miss: uppercase)", async () => {
    const fake = ports({ token: TOKEN.toUpperCase() });
    expect((await syncPushRegistration(fake, { asked: false })).outcome).toBe("failed");
    expect(fake.putToken).not.toHaveBeenCalled();
  });

  it("an unreachable server is a failed run that a later run retries", async () => {
    const fake = ports({ put: { ok: false, error: "unreachable" } });
    expect((await syncPushRegistration(fake, { asked: false })).outcome).toBe("failed");
    expect((await syncPushRegistration(fake, { asked: false })).outcome).toBe("failed");
    expect(fake.putToken).toHaveBeenCalledTimes(2);
  });

  it("a server-side token refusal is failed, not registered", async () => {
    const fake = ports({ put: { ok: false, error: "invalid_token" } });
    expect((await syncPushRegistration(fake, { asked: false })).outcome).toBe("failed");
  });
});

describe("notices turned off on the phone: the server's token goes too", () => {
  it("denied at app start, registration unknown: the token is deleted (DELETE is idempotent)", async () => {
    const fake = ports({ permission: "denied" });
    expect(await syncPushRegistration(fake, { asked: false })).toEqual({
      permission: "denied",
      outcome: "skipped",
    });
    expect(fake.deleteToken).toHaveBeenCalledTimes(1);
    expect(fake.putToken).not.toHaveBeenCalled();
  });

  it("denied and known to be registered: the token is deleted", async () => {
    const fake = ports({ permission: "denied" });
    await syncPushRegistration(fake, { asked: false, registered: true });
    expect(fake.deleteToken).toHaveBeenCalledTimes(1);
  });

  it("refused at the prompt, registration unknown: the token is deleted", async () => {
    const fake = ports({ permission: "undetermined", afterPrompt: "denied" });
    expect((await syncPushRegistration(fake, { asked: true })).outcome).toBe("denied");
    expect(fake.deleteToken).toHaveBeenCalledTimes(1);
  });

  it("denied but known not to be registered: nothing is sent (near miss)", async () => {
    const fake = ports({ permission: "denied" });
    await syncPushRegistration(fake, { asked: true, registered: false });
    expect(fake.deleteToken).not.toHaveBeenCalled();
  });

  it("undetermined is not a refusal: nothing is deleted (near miss)", async () => {
    const fake = ports({ permission: "undetermined" });
    await syncPushRegistration(fake, { asked: false, registered: true });
    expect(fake.deleteToken).not.toHaveBeenCalled();
  });

  it("granted never deletes, whatever the registration (near miss)", async () => {
    const fake = ports({ permission: "granted" });
    await syncPushRegistration(fake, { asked: false, registered: true });
    expect(fake.deleteToken).not.toHaveBeenCalled();
  });

  it("a delete that throws or does not land stays inside the run", async () => {
    const fake = ports({ permission: "denied" });
    fake.deleteToken.mockRejectedValueOnce(new Error("offline"));
    expect(await syncPushRegistration(fake, { asked: true })).toEqual({
      permission: "denied",
      outcome: "denied",
    });
    fake.deleteToken.mockResolvedValueOnce({ ok: false, error: "unreachable" });
    expect((await syncPushRegistration(fake, { asked: false })).outcome).toBe("skipped");
  });
});

describe("a server with no push channel wired", () => {
  it("503 push_unavailable is not registered, silently, and a later run tries again", async () => {
    const fake = ports({ put: { ok: false, error: "push_unavailable" } });
    expect(await syncPushRegistration(fake, { asked: false })).toEqual({
      permission: "granted",
      outcome: "failed",
    });
    fake.putToken.mockResolvedValueOnce({ ok: true });
    expect((await syncPushRegistration(fake, { asked: false })).outcome).toBe("registered");
    expect(fake.putToken).toHaveBeenCalledTimes(2);
  });
});

describe("a session the server cannot bind to a device", () => {
  it("409 stops further attempts until the next sign-in, and tells nobody", async () => {
    const fake = ports({ put: { ok: false, error: "session_unbound" } });
    expect(await syncPushRegistration(fake, { asked: false })).toEqual({
      permission: "granted",
      outcome: "unbound",
    });
    expect(await syncPushRegistration(fake, { asked: true })).toEqual({
      permission: "granted",
      outcome: "unbound",
    });
    expect(fake.putToken).toHaveBeenCalledTimes(1);
    expect(fake.deviceToken).toHaveBeenCalledTimes(1);
  });

  it("signing out clears the stop, so the next session tries again", async () => {
    const fake = ports({ put: { ok: false, error: "session_unbound" } });
    await syncPushRegistration(fake, { asked: false });
    resetPushRegistration();
    fake.putToken.mockResolvedValueOnce({ ok: true });
    expect((await syncPushRegistration(fake, { asked: false })).outcome).toBe("registered");
    expect(fake.putToken).toHaveBeenCalledTimes(2);
  });
});
