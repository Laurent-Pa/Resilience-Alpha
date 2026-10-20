"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { userManager } from "@/lib/auth";

export default function CallbackPage() {
  const router = useRouter();
  const handled = useRef(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    // Le code d'autorisation est à usage unique : StrictMode monte deux fois en dev.
    if (handled.current) return;
    handled.current = true;
    userManager()
      .signinRedirectCallback()
      .then((user) => {
        const target = typeof user.state === "string" ? user.state : "/payment";
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
