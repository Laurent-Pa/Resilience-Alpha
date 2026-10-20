/**
 * Client API pour le service de paiement par virement.
 *
 * Orchestration :
 * - Récupère (et met en cache) la clé publique RSA du backend
 * - Chiffre le payload IBAN avec crypto.ts
 * - Envoie la requête avec un Idempotency-Key
 * - Si le backend répond 400 decryption_failed (clé RSA backend expirée/
 *   renouvelée depuis le dernier fetch), recharge la clé publique et
 *   retente UNE seule fois avec le MÊME Idempotency-Key
 */

import {
  importPublicKey,
  encryptTransferPayload,
  type TransferPayload,
} from "./crypto";
import { getAccessToken, login } from "./auth";

// Confirmé via contracts/openapi-payment.json : le service expose bien
// ses routes sous /api/payments, le WAF route sans réécriture de chemin.
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/payments";

interface PublicKeyResponse {
  public_key: string;
  key_id: string;
  algorithm: string; // "RSA-OAEP-256"
  content_encryption: string; // "A256GCM"
}

// Forme confirmée des erreurs métier (voir CLAUDE.md §7) :
// {"detail": {"code": "...", "message": "..."}}
interface ErrorDetail {
  code: string;
  message: string;
}

interface ErrorResponse {
  detail: ErrorDetail;
}

// Réponse de succès (201 créé, ou 200 en cas de rejeu identique)
export interface Payment {
  id: string;
  src_account: string;
  dst_account: string;
  dst_iban_masked: string;
  amount: string; // euros, ex. "50.05"
  status: "COMPLETED" | "REJECTED";
  created_at: string;
}

export interface TransferResult {
  ok: boolean;
  status: number;
  body: Payment | ErrorResponse | unknown;
}

/**
 * Extrait un message d'erreur lisible depuis le body d'une réponse en échec,
 * quand sa forme correspond à ErrorResponse ({detail: {code, message}}).
 * Le message backend ne contient jamais de valeur saisie par l'utilisateur
 * (voir CLAUDE.md §7), donc il est sûr à afficher tel quel.
 */
export function extractErrorMessage(body: unknown): string | null {
  if (
    body &&
    typeof body === "object" &&
    "detail" in body &&
    body.detail &&
    typeof body.detail === "object" &&
    "message" in body.detail &&
    typeof body.detail.message === "string"
  ) {
    return body.detail.message;
  }
  return null;
}

let cachedPublicKey: { key: CryptoKey; keyId: string } | null = null;

/**
 * Récupère la clé publique RSA du backend, avec mise en cache en mémoire.
 * `forceRefresh` permet de recharger après un 400 decryption_failed (le
 * backend a pu redémarrer avec une nouvelle clé si elle n'est pas montée
 * depuis un secret persistant).
 */
async function getPublicKey(forceRefresh = false): Promise<CryptoKey> {
  if (!forceRefresh && cachedPublicKey) {
    return cachedPublicKey.key;
  }

  const res = await fetch(`${API_BASE}/public-key`);
  if (!res.ok) {
    throw new Error(
      "Impossible de récupérer la clé publique de paiement (HTTP " +
        res.status +
        ")"
    );
  }

  const data: PublicKeyResponse = await res.json();
  const key = await importPublicKey(data.public_key);
  cachedPublicKey = { key, keyId: data.key_id };
  return key;
}

/**
 * Soumet un virement : chiffre l'IBAN et le montant, envoie la requête,
 * et retente une fois en cas d'échec de déchiffrement côté backend.
 */
export async function submitTransfer(
  payload: TransferPayload,
  amount: string
): Promise<TransferResult> {
  // Un seul Idempotency-Key pour toute la tentative, y compris le retry,
  // pour que le backend identifie bien qu'il s'agit du même virement
  const idempotencyKey = crypto.randomUUID();
  return attemptTransfer(payload, amount, idempotencyKey, true);
}

async function attemptTransfer(
  payload: TransferPayload,
  amount: string,
  idempotencyKey: string,
  allowRetry: boolean
): Promise<TransferResult> {
  const token = await getAccessToken();
  if (!token) {
    await login();
    throw new Error("Session expirée, redirection vers la connexion.");
  }

  const publicKey = await getPublicKey();
  const encrypted = await encryptTransferPayload(payload, publicKey);

  const res = await fetch(`${API_BASE}/transfer`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      ...encrypted,
      amount,
    }),
  });

  if (res.status === 400) {
    const body: ErrorResponse | null = await res
      .clone()
      .json()
      .catch(() => null);
    const isDecryptionFailure = body?.detail?.code === "decryption_failed";

    if (allowRetry && isDecryptionFailure) {
      await getPublicKey(true);
      return attemptTransfer(payload, amount, idempotencyKey, false);
    }
  }

  const body = await res.json().catch(() => null);
  return { ok: res.ok, status: res.status, body };
}
