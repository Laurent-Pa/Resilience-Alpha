import type { Metadata } from "next";
import { AdminAuthProvider } from "./AdminAuthContext";
import { Navbar } from "@/components/admin/layout/Navbar";
import { Sidebar } from "@/components/admin/layout/Sidebar";

export const metadata: Metadata = {
  title: "Résilience Alpha — Back-office",
  description: "Administration des paiements et supervision.",
};

export default function AdminLayout({ children }: LayoutProps<"/admin">) {
  return (
    <div className="flex min-h-screen flex-col">
      <AdminAuthProvider>
        <Navbar />
        <div className="flex flex-1">
          <Sidebar />
          <div className="min-w-0 flex-1">{children}</div>
        </div>
      </AdminAuthProvider>
    </div>
  );
}
