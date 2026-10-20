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
}

export interface AdminPaymentPage {
  items: AdminPayment[];
  total: number;
  page: number;
  page_size: number;
}

export async function fetchAdminPayments(
  page: number,
  pageSize: number,
  accessToken: string | null
): Promise<AdminPaymentPage> {
  const url = `${ADMIN_API_BASE}/payments?page=${page}&page_size=${pageSize}`;
  const res = await fetch(url, {
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
  });
  if (!res.ok) {
    throw new Error(`Impossible de charger les paiements (HTTP ${res.status})`);
  }
  return res.json();
}
