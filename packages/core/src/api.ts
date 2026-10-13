import { z } from "zod";
import {
  dashboardHomeSchema,
  loginResponseSchema,
  sessionResponseSchema,
  userSchema,
  type DashboardHome,
  type LoginRequest,
  type LoginResponse,
  type MfaVerifyRequest,
  type SessionResponse,
  type User,
} from "./schemas";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface ApiClientOptions {
  baseUrl: string;
  /** "web" relies on the httpOnly refresh cookie; "mobile" sends the refresh token in the body. */
  client: "web" | "mobile";
  getAccessToken: () => string | null;
  fetchImpl?: typeof fetch;
}

const noContent = z.null();

/**
 * Thin typed client for the Fault Sigma API, shared by web and mobile.
 * Every response is validated with Zod so a server/client mismatch fails loudly.
 */
export function createApiClient(opts: ApiClientOptions) {
  const doFetch = opts.fetchImpl ?? fetch;

  async function request<S extends z.ZodTypeAny>(
    path: string,
    schema: S,
    init: RequestInit = {},
  ): Promise<z.infer<S>> {
    const headers = new Headers(init.headers);
    headers.set("Accept", "application/json");
    headers.set("X-Client", opts.client);
    if (init.body) headers.set("Content-Type", "application/json");
    const token = opts.getAccessToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);

    const res = await doFetch(`${opts.baseUrl}${path}`, {
      ...init,
      headers,
      credentials: opts.client === "web" ? "include" : "omit",
    });
    const body: unknown = res.status === 204 ? null : await res.json().catch(() => null);
    if (!res.ok) {
      const detail = (body as { detail?: unknown } | null)?.detail;
      throw new ApiError(res.status, typeof detail === "string" ? detail : `Request failed (${res.status})`);
    }
    return schema.parse(body);
  }

  const post = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });
  const refreshBody = (refreshToken?: string) => (refreshToken ? { refresh_token: refreshToken } : {});

  return {
    login: (body: LoginRequest): Promise<LoginResponse> =>
      request("/auth/login", loginResponseSchema, post(body)),
    verifyMfa: (body: MfaVerifyRequest): Promise<SessionResponse> =>
      request("/auth/mfa/verify", sessionResponseSchema, post(body)),
    refresh: (refreshToken?: string): Promise<SessionResponse> =>
      request("/auth/refresh", sessionResponseSchema, post(refreshBody(refreshToken))),
    logout: async (refreshToken?: string): Promise<void> => {
      await request("/auth/logout", noContent, post(refreshBody(refreshToken)));
    },
    me: (): Promise<User> => request("/me", userSchema),
    dashboardHome: (): Promise<DashboardHome> => request("/dashboard/home", dashboardHomeSchema),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
