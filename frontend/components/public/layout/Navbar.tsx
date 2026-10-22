"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { userManager, logout, rolesFromAccessToken } from "@/lib/auth";
import { UserMenu } from "./UserMenu";

const OPS_ROLE = "ops";

/**
 * Header de la partie "publique" (/payment, /login, /callback). Même langage
 * visuel que components/admin/layout/Navbar.tsx, mais branché sur la session
 * oidc-client-ts (lib/auth.ts) plutôt que sur AdminAuthContext : ce sont deux
 * sessions Keycloak différentes (client web-pay vs back-office).
 *
 * Masqué tant que la session n'est pas confirmée (évite un flash "déconnecté").
 */
export function Navbar() {
  const [status, setStatus] = useState<"checking" | "authenticated" | "anonymous">("checking");
  const [username, setUsername] = useState<string | null>(null);
  const [isOps, setIsOps] = useState(false);

  useEffect(() => {
    let cancelled = false;
    userManager()
      .getUser()
      .then((user) => {
        if (cancelled) return;
        if (user && !user.expired) {
          setUsername(
            typeof user.profile?.preferred_username === "string"
              ? user.profile.preferred_username
              : null
          );
          setIsOps(rolesFromAccessToken(user.access_token).includes(OPS_ROLE));
          setStatus("authenticated");
        } else {
          setStatus("anonymous");
        }
      })
      .catch(() => {
        if (!cancelled) setStatus("anonymous");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (status !== "authenticated") {
    return null;
  }

  return (
    <header className="sticky top-0 z-40 flex h-[var(--ra-navbar-height)] w-full border-b border-[var(--ra-border-primary)] bg-[var(--ra-background)]">
      <div className="flex w-[var(--ra-sidebar-width)] shrink-0 items-center justify-center bg-[var(--ra-background-secondary)] px-6">
        <Link href="/payment" className="text-[26px] font-bold text-[var(--ra-brand)]">
          Résilience α
        </Link>
      </div>

      <div className="flex flex-1 items-center justify-end gap-3 px-6">
        <UserMenu
          label={username ?? "Mon compte"}
          onLogout={() => logout()}
          links={isOps ? [{ href: "/admin/payments", label: "Administration" }] : []}
        />
      </div>
    </header>
  );
}
