"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type { User } from "oidc-client-ts";
import { adminUserManager, adminLogout, rolesFromAccessToken } from "@/lib/admin-auth";

const REQUIRED_ROLE = "ops";

export interface AdminUser {
  sub: string;
  name: string;
  role: string; // "ops" (seul rôle autorisé à passer le AuthGate)
}

interface AdminAuthState {
  user: AdminUser | null; // non-null seulement si le rôle "ops" est confirmé
  accessToken: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  /** Connecté à Keycloak, mais sans le rôle ops : distinct de "pas connecté du tout",
   * pour ne pas renvoyer en boucle vers l'écran de connexion. */
  hasSessionWithoutOpsRole: boolean;
  logoutUser: () => Promise<void>;
}

const AdminAuthContext = createContext<AdminAuthState | null>(null);

export function AdminAuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AdminUser | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [hasSessionWithoutOpsRole, setHasSessionWithoutOpsRole] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const mgr = adminUserManager();
    let cancelled = false;

    function apply(current: User | null) {
      if (cancelled) return;
      if (!current || current.expired) {
        setUser(null);
        setAccessToken(null);
        setHasSessionWithoutOpsRole(false);
        return;
      }
      const roles = rolesFromAccessToken(current.access_token);
      if (!roles.includes(REQUIRED_ROLE)) {
        setUser(null);
        setAccessToken(null);
        setHasSessionWithoutOpsRole(true);
        return;
      }
      const username =
        typeof current.profile.preferred_username === "string"
          ? current.profile.preferred_username
          : current.profile.sub;
      setUser({ sub: current.profile.sub, name: username, role: REQUIRED_ROLE });
      setAccessToken(current.access_token);
      setHasSessionWithoutOpsRole(false);
    }

    mgr
      .getUser()
      .then(apply)
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    const onUserLoaded = (u: User) => apply(u);
    const onUnload = () => apply(null);
    mgr.events.addUserLoaded(onUserLoaded);
    mgr.events.addUserUnloaded(onUnload);
    mgr.events.addUserSignedOut(onUnload);
    return () => {
      cancelled = true;
      mgr.events.removeUserLoaded(onUserLoaded);
      mgr.events.removeUserUnloaded(onUnload);
      mgr.events.removeUserSignedOut(onUnload);
    };
  }, []);

  async function logoutUser() {
    await adminLogout();
  }

  return (
    <AdminAuthContext.Provider
      value={{
        user,
        accessToken,
        isLoading,
        isAuthenticated: user !== null,
        hasSessionWithoutOpsRole,
        logoutUser,
      }}
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
