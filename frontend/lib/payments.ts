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

// TODO: confirmer la base définitive une fois le routage WAF /api aligné
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/payments";

interface PublicKeyResponse {
  key_id: string;
  // TODO: confirmer le nom exact du champ contenant le PEM (vu via /docs)
  public_key_pem: string;
  algorithms: {
    rsa: string;
    aes: string;
  };
}

export interface TransferResult {
  ok: boolean;
  status: number;
  body: unknown;
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
  const key = await importPublicKey(data.public_key_pem);
  cachedPublicKey = { key, keyId: data.key_id };
  return key;
}

/**
 * Soumet un virement : chiffre l'IBAN et le montant, envoie la requête,
 * et retente une fois en cas d'échec de déchiffrement côté backend.
 */
export async function submitTransfer(
  payload: TransferPayload,
  amountCents: number
): Promise<TransferResult> {
  // Un seul Idempotency-Key pour toute la tentative, y compris le retry,
  // pour que le backend identifie bien qu'il s'agit du même virement
  const idempotencyKey = crypto.randomUUID();
  return attemptTransfer(payload, amountCents, idempotencyKey, true);
}

async function attemptTransfer(
  payload: TransferPayload,
  amountCents: number,
  idempotencyKey: string,
  allowRetry: boolean
): Promise<TransferResult> {
  const publicKey = await getPublicKey();
  const encrypted = await encryptTransferPayload(payload, publicKey);

  const res = await fetch(`${API_BASE}/transfer`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify({
      ...encrypted,
      amount_cents: amountCents,
    }),
  });

  if (res.status === 400) {
    const body = await res.clone().json().catch(() => null);
    // TODO: confirmer la forme exacte de l'erreur côté backend
    // (FastAPI renvoie {"detail": "..."} par défaut avec HTTPException)
    const isDecryptionFailure =
      body?.detail === "decryption_failed" ||
      body?.error_code === "decryption_failed";

    if (allowRetry && isDecryptionFailure) {
      await getPublicKey(true);
      return attemptTransfer(payload, amountCents, idempotencyKey, false);
    }
  }

  const body = await res.json().catch(() => null);
  return { ok: res.ok, status: res.status, body };
}
