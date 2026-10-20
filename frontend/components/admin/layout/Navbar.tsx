"use client";

import Link from "next/link";
import { useAdminAuth } from "@/app/admin/AdminAuthContext";
import { UserMenu } from "./UserMenu";

export function Navbar() {
  const { user } = useAdminAuth();

  if (!user) {
    return null;
  }

  return (
    <header className="sticky top-0 z-40 flex h-[var(--ra-navbar-height)] w-full border-b border-[var(--ra-border-primary)] bg-[var(--ra-background)]">
      <div className="flex w-[var(--ra-sidebar-width)] shrink-0 items-center justify-center bg-[var(--ra-background-secondary)] px-6">
        <Link href="/admin/payments" className="text-[26px] font-bold text-[var(--ra-brand)]">
          Résilience α
        </Link>
      </div>

      <div className="flex flex-1 items-center justify-end gap-3 px-6">
        {/* CTA à ajouter ici (ex: rafraîchir la liste) à l'étape "page Payment" */}
        <UserMenu />
      </div>
    </header>
  );
}
