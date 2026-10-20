"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export interface AdminUser {
  sub: string;
  name: string;
  role: string; // "ops" attendu
}

interface AdminAuthState {
  user: AdminUser | null;
  accessToken: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  logoutUser: () => Promise<void>;
}

const AdminAuthContext = createContext<AdminAuthState | null>(null);

/**
 * Implémentation provisoire, en attendant le branchement Keycloak/oidc-client-ts
 * (CLAUDE.md §6, en cours côté collègue). Le contrat exposé ici (user/accessToken/
 * isLoading/logoutUser) est celui du futur AuthProvider OIDC : Navbar, Sidebar,
 * AuthGate et les appels API n'auront rien à changer une fois le vrai provider
 * branché dans ce fichier.
 *
 * TODO(Keycloak) : supprimer le bloc "bypass de dev" ci-dessous une fois la vraie
 * init OIDC branchée ici — il n'existe que pour visualiser/tester le back-office
 * en local avant que l'authentification soit prête.
 */
export function AdminAuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AdminUser | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // TODO(Keycloak): remplacer tout ce bloc par l'initialisation oidc-client-ts
    // (silent sign-in), en conservant la forme user/accessToken ci-dessus.
    if (process.env.NEXT_PUBLIC_ADMIN_DEV_BYPASS === "true") {
      setUser({
        sub: "dev-bypass",
        name: process.env.NEXT_PUBLIC_ADMIN_DEV_NAME ?? "Compte de test (bypass)",
        role: process.env.NEXT_PUBLIC_ADMIN_DEV_ROLE ?? "ops",
      });
      setAccessToken(process.env.NEXT_PUBLIC_ADMIN_DEV_TOKEN ?? null);
    }
    setIsLoading(false);
  }, []);

  async function logoutUser() {
    setUser(null);
    setAccessToken(null);
  }

  return (
    <AdminAuthContext.Provider
      value={{ user, accessToken, isLoading, isAuthenticated: user !== null, logoutUser }}
    >
      {children}
    </AdminAuthContext.Provider>
  );
}

export function useAdminAuth(): AdminAuthState {
  const ctx = useContext(AdminAuthContext);
  if (!ctx) {
    throw new Error("useAdminAuth doit être utilisé sous AdminAuthProvider");
  }
  return ctx;
}
