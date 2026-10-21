/**
 * Client API du SLI de la sonde (GET /api/admin/prober/success-rate, rôle ops).
 *
 * Le taux par minute est calculé côté backend ; ce module n'en dérive que la synthèse
 * affichée en tête de page (sommes, pas de nouvelle hypothèse).
 */

const ADMIN_API_BASE = process.env.NEXT_PUBLIC_ADMIN_API_BASE_URL ?? "/api/admin";

export interface ProberMinute {
  minute: string; // début de la minute, ISO 8601 UTC
  success_count: number;
  expected_count: number; // 60 / intervalle de la sonde
  success_pct: number; // 0-100, plafonné à 100
}

export interface ProberSuccessRate {
  interval_s: number;
  window_minutes: number;
  points: ProberMinute[]; // du plus ancien au plus récent
}

export async function fetchProberSuccessRate(
  accessToken: string | null
): Promise<ProberSuccessRate> {
  const res = await fetch(`${ADMIN_API_BASE}/prober/success-rate`, {
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
  });
  if (!res.ok) {
    throw new Error(`Impossible de charger le SLI de la sonde (HTTP ${res.status})`);
  }
  return res.json();
}

export interface ProberSummary {
  windowPct: number; // réussites / attendus sur toute la fenêtre, plafonné à 100
  last: ProberMinute | null; // dernière minute complète
  minutesWithoutSuccess: number;
}

/**
 * Le taux de la fenêtre se calcule sur les sommes, pas en moyennant les pourcentages :
 * les minutes plafonnées à 100 % (13 virements pour 12 attendus) fausseraient la moyenne.
 */
export function summarize(points: ProberMinute[]): ProberSummary {
  const success = points.reduce((acc, p) => acc + p.success_count, 0);
  const expected = points.reduce((acc, p) => acc + p.expected_count, 0);
  return {
    windowPct: expected > 0 ? Math.min(100, (100 * success) / expected) : 0,
    last: points.at(-1) ?? null,
    minutesWithoutSuccess: points.filter((p) => p.success_count === 0).length,
  };
}

const PCT = new Intl.NumberFormat("fr-FR", { style: "percent", maximumFractionDigits: 1 });

/** 99.6 -> "99,6 %" */
export function formatPct(value: number): string {
  return PCT.format(value / 100);
}

/** Heure locale du navigateur (les minutes arrivent en UTC). */
export function formatMinute(iso: string): string {
  return new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}
