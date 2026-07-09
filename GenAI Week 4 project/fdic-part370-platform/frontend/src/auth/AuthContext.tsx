import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
  type ReactNode,
} from "react";
import { useMsal } from "@azure/msal-react";
import { loginRequest } from "./msalConfig";
import { setAuthToken } from "../api/client";

export type Role = "Analyst" | "Reviewer" | "Admin";

export interface AuthUser {
  name: string;
  email?: string;
  roles: Role[];
  mode: "sso" | "demo";
}

interface AuthContextValue {
  user: AuthUser | null;
  ready: boolean;
  azureConfigured: boolean;
  error: string | null;
  loginSso: () => Promise<void>;
  loginDemo: (name: string, role: Role) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);
const DEMO_KEY = "fdic.demoUser";

// SSO is only wired when a real Azure AD app registration is configured at build
// time. Otherwise the app runs in demo mode (backend ENVIRONMENT=local bypasses
// token validation and grants an Admin principal), so no token is needed.
export const azureConfigured = Boolean(import.meta.env.VITE_AZURE_CLIENT_ID);

export function AuthProvider({ children }: { children: ReactNode }) {
  const { instance, accounts } = useMsal();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Pull an access token for the API and attach it to the axios client.
  const attachToken = useCallback(async () => {
    try {
      const account = instance.getAllAccounts()[0];
      if (!account) return;
      const res = await instance.acquireTokenSilent({ ...loginRequest, account });
      setAuthToken(res.accessToken);
    } catch {
      /* silent-acquire failure is non-fatal in demo/local backend */
    }
  }, [instance]);

  // Restore session on load: an active MSAL account, else a saved demo user.
  useEffect(() => {
    (async () => {
      const account = accounts[0];
      if (azureConfigured && account) {
        const roles = ((account.idTokenClaims as any)?.roles ?? ["Analyst"]) as Role[];
        setUser({ name: account.name ?? account.username, email: account.username,
                  roles, mode: "sso" });
        await attachToken();
      } else {
        const saved = sessionStorage.getItem(DEMO_KEY);
        if (saved) setUser(JSON.parse(saved) as AuthUser);
      }
      setReady(true);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loginSso = useCallback(async () => {
    setError(null);
    try {
      const res = await instance.loginPopup(loginRequest);
      const account = res.account!;
      const roles = ((account.idTokenClaims as any)?.roles ?? ["Analyst"]) as Role[];
      setUser({ name: account.name ?? account.username, email: account.username,
                roles, mode: "sso" });
      await attachToken();
    } catch (e: any) {
      setError(e?.message ?? "Azure AD sign-in failed");
    }
  }, [instance, attachToken]);

  const loginDemo = useCallback((name: string, role: Role) => {
    const demo: AuthUser = { name: name.trim() || "Demo User", roles: [role], mode: "demo" };
    sessionStorage.setItem(DEMO_KEY, JSON.stringify(demo));
    setUser(demo);
  }, []);

  const logout = useCallback(() => {
    sessionStorage.removeItem(DEMO_KEY);
    setAuthToken("");
    const wasSso = user?.mode === "sso";
    setUser(null);
    if (wasSso && azureConfigured) {
      instance.logoutPopup().catch(() => {});
    }
  }, [instance, user]);

  const value = useMemo<AuthContextValue>(
    () => ({ user, ready, azureConfigured, error, loginSso, loginDemo, logout }),
    [user, ready, error, loginSso, loginDemo, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
