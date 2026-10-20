/**
 * Utilitaires d'affichage pour les données de paiement.
 */

/**
 * Masque un IBAN pour l'affichage (ex: récapitulatif après soumission),
 * ne garde visibles que le code pays et les 4 derniers caractères.
 * Exemple : "FR7630006000011234567890189" -> "FR76 **** **** **** 0189"
 */
export function maskIban(iban: string): string {
  const cleaned = iban.replace(/\s+/g, "").toUpperCase();
  if (cleaned.length < 8) {
    return cleaned;
  }
  const countryAndCheck = cleaned.slice(0, 4);
  const last4 = cleaned.slice(-4);
  return `${countryAndCheck} **** **** **** ${last4}`;
}

/**
 * Formate la saisie d'un IBAN en groupes de 4 caractères séparés par des
 * espaces, pour faciliter la lecture pendant la frappe.
 * Exemple : "FR7630006000011234567890189" -> "FR76 3000 6000 0112 3456 7890 189"
 *
 * Retire tout caractère non alphanumérique (espaces existants compris) avant
 * de regrouper, pour éviter l'accumulation d'espaces si l'utilisateur
 * modifie le champ au milieu de la saisie.
 */
export function formatIbanInput(value: string): string {
  const cleaned = value.replace(/[^a-zA-Z0-9]/g, "").toUpperCase();
  return cleaned.match(/.{1,4}/g)?.join(" ") ?? cleaned;
}

/**
 * Formate un montant en euros pour affichage (ex: "135.5" -> "135,50 €").
 * Affichage seulement : le montant est envoyé à l'API tel que saisi (chaîne).
 */
export function formatEuros(amount: string): string {
  return Number(amount).toLocaleString("fr-FR", {
    style: "currency",
    currency: "EUR",
  });
}
