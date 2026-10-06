import { useCallback, useEffect, useMemo, useState } from "react";
import { api, clearTokens, getAccessToken, getRefreshToken, storeTokens } from "../lib/api";
import type { LoginResponse, User } from "../lib/types";
import { AuthContext, type AuthState } from "./context";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
  }, []);

  const reload = useCallback(async () => {
    if (!getAccessToken()) return;
    try {
      const { data } = await api.get<User>("/auth/me");
      setUser(data);
    } catch {
      clearTokens();
      setUser(null);
    }
  }, []);

  const login = useCallback(async (username: string, password: string): Promise<User> => {
    const { data } = await api.post<LoginResponse>("/auth/login", { username, password });
    storeTokens(data);
    setUser(data.user);
    return data.user;
  }, []);

  // Restore a previous session on first paint.
  useEffect(() => {
    let cancelled = false;
    async function restore() {
      if (!getAccessToken() && !getRefreshToken()) {
        if (!cancelled) setLoading(false);
        return;
      }
      try {
        const { data } = await api.get<User>("/auth/me");
        if (!cancelled) setUser(data);
      } catch {
        if (!cancelled) clearTokens();
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void restore();
    return () => {
      cancelled = true;
    };
  }, []);

  // The API client signals an unrecoverable 401 after a failed refresh.
  useEffect(() => {
    const onSignedOut = () => logout();
    window.addEventListener("registry:signed-out", onSignedOut);
    return () => window.removeEventListener("registry:signed-out", onSignedOut);
  }, [logout]);

  const value = useMemo<AuthState>(
    () => ({ user, loading, login, logout, reload }),
    [user, loading, login, logout, reload],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
