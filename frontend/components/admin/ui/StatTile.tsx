interface StatTileProps {
  label: string;
  value: string;
  hint?: string;
}

/** Une valeur en tête de page. Texte neutre : la tuile informe, elle ne juge pas. */
export function StatTile({ label, value, hint }: StatTileProps) {
  return (
    <div className="flex flex-col gap-1 rounded-[4px] border border-[var(--ra-border-primary)] bg-[var(--ra-background)] px-4 py-3">
      <span className="text-xs font-medium text-[var(--ra-input-text)]">{label}</span>
      <span className="text-2xl font-semibold text-[var(--ra-foreground)]">{value}</span>
      {hint && <span className="text-xs text-[var(--ra-input-text)]">{hint}</span>}
    </div>
  );
}
