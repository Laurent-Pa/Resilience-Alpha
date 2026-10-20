interface StatusBadgeProps {
  status: "COMPLETED" | "REJECTED";
}

const STATUS_STYLES: Record<StatusBadgeProps["status"], { label: string; className: string }> = {
  COMPLETED: {
    label: "effectué",
    className: "text-[var(--ra-status-ok-text)] bg-[var(--ra-status-ok-bg)]",
  },
  REJECTED: {
    label: "rejeté",
    className: "text-[var(--ra-status-alert-text)] bg-[var(--ra-status-alert-bg)]",
  },
};

export function StatusBadge({ status }: StatusBadgeProps) {
  const { label, className } = STATUS_STYLES[status];
  return (
    <span
      className={`inline-flex h-8 w-24 shrink-0 items-center justify-center rounded-full text-center text-xs font-medium ${className}`}
    >
      {label}
    </span>
  );
}
