import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError } from "./api";
import i18n, { setLang, type Lang } from "./i18n";

export type Role = "admin" | "dpo" | "it" | "auditor";
export interface User {
  id: number;
  username: string;
  display_name: string;
  role: Role;
  locale: Lang;
  capabilities: string[];
  mfa_enabled?: boolean;
}

interface AuthState {
  user: User | null;
  loading: boolean;
  needsSetup: boolean;
  /** Resolves to an MFA token when the account needs a second step; call verifyMfa with it. */
  login: (username: string, password: string) => Promise<string | void>;
  verifyMfa: (mfaToken: string, code: string) => Promise<void>;
  setUser: (u: User) => void;
  setup: (username: string, displayName: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  can: (capability: string) => boolean;
  changeLang: (lang: Lang) => Promise<void>;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [needsSetup, setNeedsSetup] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const me = await api.get<User>("/api/auth/me");
        setUser(me);
        await setLang(me.locale);
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) {
          try {
            const s = await api.get<{ needs_setup: boolean }>("/api/auth/status");
            setNeedsSetup(s.needs_setup);
          } catch {
            /* server down */
          }
        }
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const finishSignIn = useCallback(async (me: User) => {
    // The language chosen on the sign-in screen wins and is saved to the profile.
    const shown = (i18n.language === "ar" ? "ar" : "en") as Lang;
    if (shown !== me.locale) {
      try {
        setUser(await api.put<User>("/api/auth/me/locale", { locale: shown }));
        return;
      } catch {
        /* fall through */
      }
    }
    setUser(me);
  }, []);

  const login = useCallback(
    async (username: string, password: string) => {
      const res = await api.post<User | { mfa_required: true; mfa_token: string }>("/api/auth/login", { username, password });
      if ("mfa_required" in res) return res.mfa_token;
      await finishSignIn(res);
    },
    [finishSignIn],
  );

  const verifyMfa = useCallback(
    async (mfa_token: string, code: string) => {
      await finishSignIn(await api.post<User>("/api/auth/mfa/verify", { mfa_token, code }));
    },
    [finishSignIn],
  );

  const setup = useCallback(async (username: string, display_name: string, password: string) => {
    const me = await api.post<User>("/api/auth/setup", { username, display_name, password });
    setNeedsSetup(false);
    setUser(me);
  }, []);

  const logout = useCallback(async () => {
    await api.post("/api/auth/logout");
    setUser(null);
  }, []);

  const can = useCallback((c: string) => !!user?.capabilities.includes(c), [user]);

  const changeLang = useCallback(
    async (lang: Lang) => {
      await setLang(lang);
      if (user) {
        try {
          const me = await api.put<User>("/api/auth/me/locale", { locale: lang });
          setUser(me);
        } catch {
          /* keep local choice */
        }
      }
    },
    [user],
  );

  return (
    <Ctx.Provider value={{ user, loading, needsSetup, login, verifyMfa, setUser, setup, logout, can, changeLang }}>{children}</Ctx.Provider>
  );
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}
