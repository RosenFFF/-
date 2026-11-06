import { createContext, useContext } from "react";
import type { CurrentUser } from "../api/types";
export type AuthState = {
  session: CurrentUser | null;
  loading: boolean;
  initialError: unknown;
  login: (u: string, p: string) => Promise<void>;
  logout: () => Promise<void>;
  role: CurrentUser["role"] | null;
};
export const AuthContext = createContext<AuthState | null>(null);
export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("AuthProvider missing");
  return value;
}
