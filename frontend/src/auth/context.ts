import { createContext, useContext } from "react";
import type { User } from "../lib/types";

export interface AuthState {
  user: User | null;
  /** Null while the session is still being restored from storage. */
  loading: boolean;
  login: (username: string, password: string) => Promise<User>;
  logout: () => void;
  /** Refresh the cached profile (after a password change, for example). */
  reload: () => Promise<void>;
}

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
