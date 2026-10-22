import type { Metadata } from "next";
import { Poppins, REM, Geist_Mono } from "next/font/google";
import "./globals.css";

// Body copy : titres, sous-titres, labels, boutons (même police que /admin).
const poppins = Poppins({
  variable: "--font-poppins",
  subsets: ["latin"],
  weight: ["400", "500", "700"],
});

// Réservé à la saisie utilisateur (IBAN, montant, nom...), comme sur /admin.
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
  title: "Résilience Alpha",
  description: "Virements bancaires — Résilience Alpha.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="fr"
      className={`${poppins.variable} ${rem.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
