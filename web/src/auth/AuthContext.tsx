import { useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../api";
import type { CurrentUser } from "../api/types";
import { aborted, ApiError } from "../api/http";

import { AuthContext as Ctx, type AuthState } from "./context";
export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [initialError, setInitialError] = useState<unknown>(null);
  useEffect(() => {
    // Remove M0's entire legacy session, including any old mock token. Never parse or reuse it.
    sessionStorage.removeItem("sr_session");
    const controller = new AbortController();
    const expired = () => setSession(null);
    window.addEventListener("session-expired", expired);
    void api
      .me(controller.signal)
      .then((user) => {
        if (!controller.signal.aborted) setSession(user);
      })
      .catch((error: unknown) => {
        if (!aborted(error)) {
          setSession(null);
          if (!(error instanceof ApiError) || error.problem.status !== 401)
            setInitialError(error);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => {
      controller.abort();
      window.removeEventListener("session-expired", expired);
    };
  }, []);
  const value = useMemo<AuthState>(
    () => ({
      session,
      loading,
      initialError,
      role: session?.role ?? null,
      async login(u, p) {
        const result = await api.login(u, p);
        setSession(result.user);
        setInitialError(null);
      },
      async logout() {
        await api.logout();
        setSession(null);
      },
    }),
    [session, loading, initialError],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
