"use client";

import { useCallback, useEffect, useState } from "react";
import { AuthGate } from "@/components/admin/auth/AuthGate";
import { useAdminAuth } from "@/app/admin/AdminAuthContext";
import { fetchAdminPayments, type AdminPayment } from "@/lib/admin-payments";
import { PaymentsTable } from "@/components/admin/payments/PaymentsTable";
import { Pagination } from "@/components/admin/ui/Pagination";
import { PageSizeSelector } from "@/components/admin/ui/PageSizeSelector";
import { Toggle } from "@/components/admin/ui/Toggle";

export default function AdminPaymentsPage() {
  return (
    <AuthGate>
      <AdminPaymentsContent />
    </AuthGate>
  );
}

function AdminPaymentsContent() {
  const { accessToken } = useAdminAuth();
  const [items, setItems] = useState<AdminPayment[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [includeProber, setIncludeProber] = useState(false);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (cancelledRef: { current: boolean }) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchAdminPayments(page, pageSize, accessToken, includeProber);
      if (cancelledRef.current) return;
      setItems(data.items);
      setTotal(data.total);
    } catch {
      if (!cancelledRef.current) {
        setError("Impossible de charger les paiements. Réessayez dans un instant.");
      }
    } finally {
      if (!cancelledRef.current) setIsLoading(false);
    }
  }, [page, pageSize, accessToken, includeProber]);

  useEffect(() => {
    const cancelledRef = { current: false };
    // Fetch de données réseau au montage / changement de page, pas un "miroir" de props :
    // cas explicitement documenté par la règle comme faux positif légitime.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load(cancelledRef);
    return () => {
      cancelledRef.current = true;
    };
  }, [load]);

  function handlePageSizeChange(size: number) {
    setPageSize(size);
    setPage(1);
  }

  function handleIncludeProberChange(next: boolean) {
    setIncludeProber(next);
    // Le total change du tout au tout : la page courante peut ne plus exister.
    setPage(1);
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <main className="flex-1 p-8">
      <h1 className="text-2xl font-semibold text-[var(--ra-foreground)]">Paiements</h1>
      <p className="mt-1 text-sm text-[var(--ra-input-text)]">
        Les virements effectués, tous émetteurs et destinataires confondus. Les opérations
        de la sonde de supervision sont masquées par défaut.
      </p>

      <div className="mt-6 flex w-full max-w-[820px] justify-end">
        <Toggle
          checked={includeProber}
          onChange={handleIncludeProberChange}
          label="Afficher les opérations de la sonde"
        />
      </div>

      <div className="mt-4">
        {error ? (
          <p role="alert" className="py-8 text-center text-sm text-[var(--ra-status-alert-text)]">
            {error}
          </p>
        ) : isLoading ? (
          <p className="py-8 text-center text-sm text-[var(--ra-input-text)]">Chargement...</p>
        ) : items.length === 0 ? (
          <p className="py-8 text-center text-sm text-[var(--ra-input-text)]">
            Aucun paiement pour l&apos;instant.
          </p>
        ) : (
          <PaymentsTable items={items} />
        )}
      </div>

      <div className="mt-6 grid grid-cols-3 items-center">
        <div className="justify-self-start">
          <PageSizeSelector value={pageSize} onChange={handlePageSizeChange} />
        </div>
        <div className="justify-self-center">
          <Pagination currentPage={page} totalPages={totalPages} onPageChange={setPage} />
        </div>
      </div>
    </main>
  );
}
