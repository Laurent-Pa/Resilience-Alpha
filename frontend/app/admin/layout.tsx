import type { Metadata } from "next";
import { Poppins, REM, Geist_Mono } from "next/font/google";
import "./admin.css";
import { AdminAuthProvider } from "./AdminAuthContext";
import { Navbar } from "@/components/admin/layout/Navbar";
import { Sidebar } from "@/components/admin/layout/Sidebar";

const poppins = Poppins({
  variable: "--font-poppins",
  subsets: ["latin"],
  weight: ["400", "500", "700"],
});

const rem = REM({
  variable: "--font-rem",
  subsets: ["latin"],
  weight: ["500"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Résilience Alpha — Back-office",
  description: "Administration des paiements et supervision.",
};

export default function AdminLayout({ children }: LayoutProps<"/admin">) {
  return (
    <div
      className={`ra-admin ${poppins.variable} ${rem.variable} ${geistMono.variable} flex min-h-screen flex-col`}
    >
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
