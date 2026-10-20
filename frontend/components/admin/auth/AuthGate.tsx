"use client";

import { useAdminAuth } from "@/app/admin/AdminAuthContext";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAdminAuth();

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-[var(--ra-input-text)]">Chargement...</p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-[var(--ra-input-text)]">
          Accès réservé aux comptes avec le rôle « ops ».
        </p>
      </div>
    );
  }

  return <>{children}</>;
}
