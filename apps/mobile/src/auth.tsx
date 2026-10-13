import { ApiError, createApiClient, type SessionResponse, type User } from "@fault-sigma/core";
import * as LocalAuthentication from "expo-local-authentication";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { API_URL } from "./config";
import { getRefreshToken, setRefreshToken, wipeDevice } from "./secure";

let accessToken: string | null = null;

export const api = createApiClient({ baseUrl: API_URL, client: "mobile", getAccessToken: () => accessToken });

type AuthState =
  | { status: "loading" }
  | { status: "locked" } // a session exists on the device but needs biometric unlock
  | { status: "signed-out" }
  | { status: "signed-in"; user: User };

interface AuthContextValue {
  state: AuthState;
  acceptSession: (s: SessionResponse) => Promise<void>;
  unlock: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

async function biometricsAvailable(): Promise<boolean> {
  return (await LocalAuthentication.hasHardwareAsync()) && (await LocalAuthentication.isEnrolledAsync());
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading" });
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const signedOut = useCallback(async () => {
    clearTimeout(timer.current);
    accessToken = null;
    await wipeDevice();
    setState({ status: "signed-out" });
  }, []);

  const acceptSession = useCallback(
    async (s: SessionResponse) => {
      accessToken = s.access_token;
      if (s.refresh_token) await setRefreshToken(s.refresh_token);
      setState({ status: "signed-in", user: s.user });
      clearTimeout(timer.current);
      // refreshNow is declared below; it is only read when the timer fires, after first render.
      timer.current = setTimeout(() => void refreshNow(), Math.max(10, s.expires_in - 60) * 1000);
    },
    [],
  );

  const refreshNow = useCallback(async () => {
    const token = await getRefreshToken();
    if (!token) return signedOut();
    try {
      await acceptSession(await api.refresh(token));
    } catch (e) {
      // Revoked or expired on the server: wipe the device. Network errors keep the session for later.
      if (e instanceof ApiError && e.status === 401) await signedOut();
      else setState((prev) => (prev.status === "signed-in" ? prev : { status: "locked" }));
    }
  }, [acceptSession, signedOut]);

  const unlock = useCallback(async () => {
    if (await biometricsAvailable()) {
      const r = await LocalAuthentication.authenticateAsync({ promptMessage: "Unlock Fault Sigma" });
      if (!r.success) return;
    }
    await refreshNow();
  }, [refreshNow]);

  const signOut = useCallback(async () => {
    const token = await getRefreshToken();
    try {
      await api.logout(token ?? undefined);
    } catch {
      /* offline: the local wipe below still happens */
    }
    await signedOut();
  }, [signedOut]);

  useEffect(() => {
    void (async () => {
      if (!(await getRefreshToken())) return setState({ status: "signed-out" });
      if (await biometricsAvailable()) setState({ status: "locked" });
      else await refreshNow();
    })();
    return () => clearTimeout(timer.current);
  }, [refreshNow]);

  const value = useMemo(() => ({ state, acceptSession, unlock, signOut }), [state, acceptSession, unlock, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
