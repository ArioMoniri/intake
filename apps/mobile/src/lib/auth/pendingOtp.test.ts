import { afterEach, describe, expect, it } from "vitest";

import { forgetOtpRequest, pendingOtpRequestId, rememberOtpRequest } from "./pendingOtp";

// INT-578: a code is bound to the request id its 202 answered with, so the
// verify call has to send that id back.
const ID_A = "0123456789abcdef0123456789abcdef";
const ID_B = "fedcba9876543210fedcba9876543210";

afterEach(() => {
  forgetOtpRequest();
});

describe("the pending OTP request id", () => {
  it("is empty until a request is answered", () => {
    expect(pendingOtpRequestId()).toBeNull();
  });

  it("remembers the id the server answered with", () => {
    rememberOtpRequest({ request_id: ID_A, resend_after_s: 60 });
    expect(pendingOtpRequestId()).toBe(ID_A);
  });

  it("a resend replaces it: only the newest code is live", () => {
    rememberOtpRequest({ request_id: ID_A });
    rememberOtpRequest({ request_id: ID_B });
    expect(pendingOtpRequestId()).toBe(ID_B);
  });

  it.each([
    ["missing", {}],
    ["upper-case", { request_id: ID_A.toUpperCase() }],
    ["one short", { request_id: ID_A.slice(1) }],
    ["not hex", { request_id: "z".repeat(32) }],
    ["a number", { request_id: 123 }],
    ["not an object", "0123456789abcdef0123456789abcdef"],
  ])("a %s id clears it instead of keeping a stale one", (_label, body) => {
    rememberOtpRequest({ request_id: ID_A });
    rememberOtpRequest(body);
    expect(pendingOtpRequestId()).toBeNull();
  });

  it("is forgotten once the code is spent", () => {
    rememberOtpRequest({ request_id: ID_A });
    forgetOtpRequest();
    expect(pendingOtpRequestId()).toBeNull();
  });
});
