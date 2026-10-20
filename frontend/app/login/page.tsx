"use client";

import { useEffect } from "react";
import { login } from "@/lib/auth";

export default function LoginPage() {
  useEffect(() => {
    login("/payment");
  }, []);

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <p className="text-gray-600">Redirection vers la connexion...</p>
    </main>
  );
}
