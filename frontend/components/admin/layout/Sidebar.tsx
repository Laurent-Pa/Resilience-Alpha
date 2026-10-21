"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAdminAuth } from "@/app/admin/AdminAuthContext";

const NAV_LINKS = [
  { href: "/admin/payments", label: "Payment" },
  { href: "/admin/monitoring", label: "Monitoring" },
  { href: "/admin/biometrics", label: "Biométrie" },
];

export function Sidebar() {
  const { user } = useAdminAuth();
  const pathname = usePathname();

  if (!user) {
    return null;
  }

  return (
    <nav
      aria-label="Navigation back-office"
      className="flex w-[var(--ra-sidebar-width)] shrink-0 flex-col gap-1 bg-[var(--ra-background-secondary)] p-4"
    >
      {NAV_LINKS.map((link) => {
        const isActive = pathname === link.href || pathname?.startsWith(`${link.href}/`);
        return (
          <Link
            key={link.href}
            href={link.href}
            aria-current={isActive ? "page" : undefined}
            className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              isActive
                ? "bg-[var(--ra-brand)] text-white"
                : "text-[var(--ra-input-text)] hover:bg-[var(--ra-background)] hover:text-[var(--ra-foreground)]"
            }`}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
