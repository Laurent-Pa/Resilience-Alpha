interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
}

/**
 * Interrupteur on/off. Un vrai <button role="switch"> : atteignable au clavier,
 * annoncé comme tel par les lecteurs d'écran, et activable en cliquant sur le libellé.
 */
export function Toggle({ checked, onChange, label }: ToggleProps) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-sm text-[var(--ra-input-text)]">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--ra-brand)] ${
          checked ? "bg-[var(--ra-brand)]" : "bg-[var(--ra-border-primary)]"
        }`}
      >
        <span
          className={`inline-block h-4 w-4 rounded-full bg-[var(--ra-background)] shadow transition-transform ${
            checked ? "translate-x-4" : "translate-x-0.5"
          }`}
        />
      </button>
      {label}
    </label>
  );
}
