"use client";

import { AuthGate } from "@/components/admin/auth/AuthGate";

export default function AdminPaymentsPage() {
  return (
    <AuthGate>
      <main className="flex-1 p-8">
        <h1 className="text-2xl font-semibold text-[var(--ra-foreground)]">Paiements</h1>
        <p className="mt-1 text-sm text-[var(--ra-input-text)]">
          Liste des virements — à venir.
        </p>
      </main>
    </AuthGate>
  );
}
