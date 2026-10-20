"use client";

import { useEffect, useRef, useState } from "react";
import { useAdminAuth } from "@/app/admin/AdminAuthContext";

const ROLE_LABELS: Record<string, string> = {
  ops: "Opérateur",
};

export function UserMenu() {
  const { user, logoutUser } = useAdminAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;

    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setIsOpen(false);
    }

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [isOpen]);

  async function handleLogout() {
    setIsLoggingOut(true);
    try {
      await logoutUser();
    } finally {
      setIsLoggingOut(false);
    }
  }

  if (!user) {
    return null;
  }

  return (
    <div ref={menuRef} className="relative">
      <button
        type="button"
        onClick={() => setIsOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        title="Menu utilisateur"
        className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-[var(--ra-background-secondary)]"
      >
        <AvatarIcon />
        <span className="text-sm font-medium text-[var(--ra-foreground)]">
          {ROLE_LABELS[user.role] ?? user.role}
        </span>
        <ChevronDownIcon isOpen={isOpen} />
      </button>

      {isOpen && (
        <div
          role="menu"
          className="absolute right-0 top-full mt-2 w-[var(--ra-user-menu-width)] rounded-lg border border-[var(--ra-border-primary)] bg-[var(--ra-background)] py-1 shadow-lg"
        >
          <button
            type="button"
            role="menuitem"
            onClick={handleLogout}
            disabled={isLoggingOut}
            className="w-full px-3 py-2 text-left text-sm text-[var(--ra-input-text)] hover:bg-[var(--ra-background-secondary)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isLoggingOut ? "Déconnexion..." : "Se déconnecter"}
          </button>
        </div>
      )}
    </div>
  );
}

function AvatarIcon() {
  return (
    <div
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--ra-background-secondary)] text-[var(--ra-input-text)]"
      aria-hidden="true"
    >
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
        <circle cx="12" cy="7" r="4" />
      </svg>
    </div>
  );
}

function ChevronDownIcon({ isOpen }: { isOpen: boolean }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      className={`transition-transform ${isOpen ? "rotate-180" : ""}`}
    >
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}
