import { ApiError, createApiClient, type SessionResponse, type User } from "@fault-sigma/core";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

/**
 * The access token lives only in memory (never localStorage), so an XSS bug cannot lift a
 * long-lived credential. The refresh token is an httpOnly cookie the page cannot read at all;
 * on reload we call /auth/refresh to get a fresh access token.
 */
let accessToken: string | null = null;

export const api = createApiClient({
  baseUrl: "/api",
  client: "web",
  getAccessToken: () => accessToken,
});

type AuthState =
  | { status: "loading" }
  | { status: "signed-out" }
  | { status: "signed-in"; user: User };

interface AuthContextValue {
  state: AuthState;
  acceptSession: (s: SessionResponse) => void;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading" });
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const acceptSession = useCallback((s: SessionResponse) => {
    accessToken = s.access_token;
    setState({ status: "signed-in", user: s.user });
    clearTimeout(timer.current);
    // Renew a minute before expiry; a failure simply signs the user out.
    timer.current = setTimeout(
      () => {
        api.refresh().then(acceptSession, () => {
          accessToken = null;
          setState({ status: "signed-out" });
        });
      },
      Math.max(10, s.expires_in - 60) * 1000,
    );
  }, []);

  const signOut = useCallback(async () => {
    clearTimeout(timer.current);
    try {
      await api.logout();
    } finally {
      accessToken = null;
      setState({ status: "signed-out" });
    }
  }, []);

  useEffect(() => {
    api.refresh().then(acceptSession, (e: unknown) => {
      if (!(e instanceof ApiError)) console.warn("Session restore failed", e);
      setState({ status: "signed-out" });
    });
    return () => clearTimeout(timer.current);
  }, [acceptSession]);

  const value = useMemo(() => ({ state, acceptSession, signOut }), [state, acceptSession, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
