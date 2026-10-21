import type { AdminPayment } from "@/lib/admin-payments";
import { StatusBadge } from "./StatusBadge";

const GRID_TEMPLATE = "grid-cols-[1.2fr_1fr_1.4fr_110px]";
const ROW_SHELL =
  "grid min-h-[48px] w-full max-w-[820px] items-center justify-items-center gap-4 rounded-[4px] border border-[var(--ra-border-primary)] px-4";

interface PaymentsTableProps {
  items: AdminPayment[];
}

export function PaymentsTable({ items }: PaymentsTableProps) {
  return (
    <div className="flex w-full max-w-[820px] flex-col gap-3">
      <div
        className={`${ROW_SHELL} ${GRID_TEMPLATE} bg-[var(--ra-background-secondary)] text-xs font-medium text-[var(--ra-input-text)]`}
      >
        <span>Date</span>
        <span>Montant</span>
        <span>IBAN destinataire</span>
        <span>Statut</span>
      </div>
      {items.map((item) => (
        <div key={item.id} className={`${ROW_SHELL} ${GRID_TEMPLATE} bg-[var(--ra-background)]`}>
          <span className="flex min-w-0 items-center justify-center gap-2 text-center text-sm text-[var(--ra-foreground)]">
            {formatDate(item.created_at)}
            {item.initiated_by === "prober" && <ProberTag />}
          </span>
          <span className="min-w-0 text-center text-sm text-[var(--ra-foreground)]">
            {formatEuros(item.amount)}
          </span>
          <span className="min-w-0 text-center text-sm font-mono text-[var(--ra-foreground)]">
            {item.dst_iban_masked}
          </span>
          <StatusBadge status={item.status} />
        </div>
      ))}
    </div>
  );
}

/** Neutre exprès : une opération de sonde n'est ni une anomalie ni un succès métier. */
function ProberTag() {
  return (
    <span
      title="Opération générée par la sonde de supervision"
      className="rounded-full border border-[var(--ra-border-primary)] px-2 py-0.5 text-[10px] font-medium text-[var(--ra-input-text)]"
    >
      sonde
    </span>
  );
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

function formatEuros(amount: string): string {
  const value = Number(amount);
  if (Number.isNaN(value)) return `${amount} €`;
  return value.toLocaleString("fr-FR", { style: "currency", currency: "EUR" });
}
