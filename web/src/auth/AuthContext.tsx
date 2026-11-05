import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';
import { login as apiLogin, type Session } from '../mock/api';
import type { Role } from '../mock/types';

type AuthState = {
  session: Session | null;
  login: (u: string, p: string) => Promise<void>;
  logout: () => void;
  role: Role | null;
};

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(() => {
    const raw = sessionStorage.getItem('sr_session');
    return raw ? (JSON.parse(raw) as Session) : null;
  });

  const value = useMemo<AuthState>(
    () => ({
      session,
      role: session?.role ?? null,
      async login(u, p) {
        const s = await apiLogin(u, p);
        sessionStorage.setItem('sr_session', JSON.stringify(s));
        setSession(s);
      },
      logout() {
        sessionStorage.removeItem('sr_session');
        setSession(null);
      },
    }),
    [session],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error('AuthProvider missing');
  return v;
}
