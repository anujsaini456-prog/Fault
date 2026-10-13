import { describe, expect, it, vi } from "vitest";
import {
  ApiError,
  createApiClient,
  hasAnyRole,
  loginRequestSchema,
  loginResponseSchema,
  totpCodeSchema,
} from "./index";

describe("loginRequestSchema", () => {
  it("normalises email", () => {
    expect(loginRequestSchema.parse({ email: "  Boss@Example.COM ", password: "x" }).email).toBe(
      "boss@example.com",
    );
  });
  it("rejects a malformed email", () => {
    expect(loginRequestSchema.safeParse({ email: "nope", password: "x" }).success).toBe(false);
  });
});

describe("totpCodeSchema", () => {
  it.each(["123456", " 000000 "])("accepts %j", (c) => expect(totpCodeSchema.safeParse(c).success).toBe(true));
  it.each(["12345", "1234567", "abcdef"])("rejects %j", (c) =>
    expect(totpCodeSchema.safeParse(c).success).toBe(false),
  );
});

describe("loginResponseSchema", () => {
  it("discriminates on status", () => {
    expect(loginResponseSchema.parse({ status: "mfa_required", mfa_token: "t" }).status).toBe("mfa_required");
    expect(loginResponseSchema.safeParse({ status: "weird" }).success).toBe(false);
  });
});

describe("hasAnyRole", () => {
  it("matches any overlap", () => {
    expect(hasAnyRole(["engineer"], ["admin", "engineer"])).toBe(true);
    expect(hasAnyRole(["executive"], ["admin"])).toBe(false);
  });
});

describe("createApiClient", () => {
  const ok = (body: unknown, status = 200) =>
    new Response(body === null ? null : JSON.stringify(body), { status });

  it("sends bearer token and client header", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(ok({ status: "mfa_required", mfa_token: "t" }));
    const api = createApiClient({ baseUrl: "/api", client: "mobile", getAccessToken: () => "abc", fetchImpl });
    await api.login({ email: "a@b.co", password: "p" });
    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    const headers = new Headers(init.headers);
    expect(url).toBe("/api/auth/login");
    expect(headers.get("Authorization")).toBe("Bearer abc");
    expect(headers.get("X-Client")).toBe("mobile");
    expect(init.credentials).toBe("omit");
  });

  it("surfaces server detail as ApiError", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(ok({ detail: "Invalid email or password" }, 401));
    const api = createApiClient({ baseUrl: "", client: "web", getAccessToken: () => null, fetchImpl });
    await expect(api.login({ email: "a@b.co", password: "p" })).rejects.toEqual(
      new ApiError(401, "Invalid email or password"),
    );
  });

  it("accepts 204 on logout", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(ok(null, 204));
    const api = createApiClient({ baseUrl: "", client: "web", getAccessToken: () => null, fetchImpl });
    await expect(api.logout()).resolves.toBeUndefined();
  });
});
