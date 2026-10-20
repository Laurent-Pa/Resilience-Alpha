"use client";

import { useEffect } from "react";
import { adminLogin } from "@/lib/admin-auth";

export default function AdminLoginPage() {
  useEffect(() => {
    adminLogin("/admin/payments");
  }, []);

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <p className="text-[var(--ra-input-text)]">Redirection vers la connexion...</p>
    </main>
  );
}
