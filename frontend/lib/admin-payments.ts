/**
 * Client API pour la vue back-office des paiements (GET /api/admin/payments,
 * rôle ops). Distinct de lib/payments.ts (client paiement, côté utilisateur).
 */

const ADMIN_API_BASE = process.env.NEXT_PUBLIC_ADMIN_API_BASE_URL ?? "/api/admin";

export interface AdminPayment {
  id: string;
  src_account: string;
  dst_account: string;
  dst_iban_masked: string;
  amount: string; // euros, ex. "50.05"
  status: "COMPLETED" | "REJECTED";
  created_at: string;
  // Origine de l'opération ; "prober" = trafic de la sonde de supervision.
  initiated_by: "user" | "prober";
}

export interface AdminPaymentPage {
  items: AdminPayment[];
  total: number;
  page: number;
  page_size: number;
}

/**
 * Le trafic de la sonde est exclu par défaut côté API : `includeProber` ne sert qu'à
 * le réafficher ponctuellement (débogage).
 */
export async function fetchAdminPayments(
  page: number,
  pageSize: number,
  accessToken: string | null,
  includeProber = false
): Promise<AdminPaymentPage> {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (includeProber) params.set("include_prober", "true");
  const url = `${ADMIN_API_BASE}/payments?${params}`;
  const res = await fetch(url, {
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
  });
  if (!res.ok) {
    throw new Error(`Impossible de charger les paiements (HTTP ${res.status})`);
  }
  return res.json();
}
