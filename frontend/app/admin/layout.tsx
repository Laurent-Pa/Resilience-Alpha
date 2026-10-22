import type { Metadata } from "next";
import { AdminAuthProvider } from "./AdminAuthContext";
import { Navbar } from "@/components/admin/layout/Navbar";
import { Sidebar } from "@/components/admin/layout/Sidebar";
import { AssistantPanel } from "@/components/admin/assistant/AssistantPanel";

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
        {/* Monté dans le layout (et non dans chaque page) : la conversation survit à la
            navigation entre Paiements et Monitoring. Visible pour le rôle ops seulement. */}
        <AssistantPanel />
      </AdminAuthProvider>
    </div>
  );
}
