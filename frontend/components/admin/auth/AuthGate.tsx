"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAdminAuth } from "@/app/admin/AdminAuthContext";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading, hasSessionWithoutOpsRole } = useAdminAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !isAuthenticated && !hasSessionWithoutOpsRole) {
      router.replace("/admin/login");
    }
  }, [isLoading, isAuthenticated, hasSessionWithoutOpsRole, router]);

  if (isLoading || (!isAuthenticated && !hasSessionWithoutOpsRole)) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-[var(--ra-input-text)]">Chargement...</p>
      </div>
    );
  }

  if (hasSessionWithoutOpsRole) {
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
