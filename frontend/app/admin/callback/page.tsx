"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { adminUserManager } from "@/lib/admin-auth";

export default function AdminCallbackPage() {
  const router = useRouter();
  const handled = useRef(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    // Le code d'autorisation est à usage unique : StrictMode monte deux fois en dev.
    if (handled.current) return;
    handled.current = true;
    adminUserManager()
      .signinRedirectCallback()
      .then((user) => {
        const target = typeof user.state === "string" ? user.state : "/admin/payments";
        router.replace(target);
      })
      .catch(() => setError(true));
  }, [router]);

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <p className="text-[var(--ra-input-text)]">
        {error ? "Échec de la connexion." : "Connexion en cours..."}
      </p>
    </main>
  );
}
