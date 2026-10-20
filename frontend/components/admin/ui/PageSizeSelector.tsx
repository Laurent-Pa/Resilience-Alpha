const PAGE_SIZE_OPTIONS = [10, 20, 50] as const;

interface PageSizeSelectorProps {
  value: number;
  onChange: (pageSize: number) => void;
}

export function PageSizeSelector({ value, onChange }: PageSizeSelectorProps) {
  return (
    <label className="flex items-center gap-2 text-sm text-[var(--ra-input-text)]">
      Afficher
      <select
        className="rounded-2xl border border-[var(--ra-border-primary)] bg-[var(--ra-background)] px-3 py-1.5 text-sm text-[var(--ra-input-text)]"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      >
        {PAGE_SIZE_OPTIONS.map((size) => (
          <option key={size} value={size}>
            {size}
          </option>
        ))}
      </select>
      lignes
    </label>
  );
}
