/**
 * Chiffrement hybride RSA-OAEP + AES-GCM pour sécuriser les données
 * sensibles (IBAN) transmises au backend.
 *
 * Principe :
 * 1. Le backend expose sa clé publique RSA (GET /api/payments/public-key).
 * 2. Le frontend génère une clé AES-256 éphémère et chiffre le payload avec.
 * 3. La clé AES est elle-même chiffrée avec la clé publique RSA du backend.
 * 4. Le backend déchiffre la clé AES avec sa clé privée, puis le payload.
 *
 * Utilise exclusivement l'API Web Crypto native du navigateur
 * (window.crypto.subtle) — aucune dépendance tierce nécessaire.
 */

export interface TransferPayload {
  iban: string;
  bic?: string;
  account_holder_name: string;
}

export interface EncryptedTransferPayload {
  encrypted_key: string; // clé AES chiffrée en RSA-OAEP, encodée en base64
  iv: string; // vecteur d'initialisation AES-GCM, encodé en base64
  ciphertext: string; // payload chiffré en AES-GCM, encodé en base64
}

/**
 * Convertit une chaîne PEM (format SPKI) en ArrayBuffer binaire DER,
 * nécessaire pour l'import via crypto.subtle.importKey.
 */
function pemToArrayBuffer(pem: string): ArrayBuffer {
  const base64 = pem
    .replace(/-----BEGIN PUBLIC KEY-----/, "")
    .replace(/-----END PUBLIC KEY-----/, "")
    .replace(/\s+/g, "");

  const binaryString = atob(base64);
  const bytes = new Uint8Array(binaryString.length);
  for (let i = 0; i < binaryString.length; i++) {
    bytes[i] = binaryString.codePointAt(i) ?? 0;
  }
  return bytes.buffer;
}

/**
 * Encode un ArrayBuffer en chaîne base64 pour transmission JSON.
 */
function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCodePoint(bytes[i]);
  }
  return btoa(binary);
}

/**
 * Importe la clé publique RSA du backend (format PEM/SPKI) en CryptoKey
 * utilisable pour le chiffrement RSA-OAEP.
 */
export async function importPublicKey(pem: string): Promise<CryptoKey> {
  const binaryDer = pemToArrayBuffer(pem);
  return crypto.subtle.importKey(
    "spki",
    binaryDer,
    { name: "RSA-OAEP", hash: "SHA-256" },
    false,
    ["encrypt"]
  );
}

/**
 * Chiffre le payload de virement (IBAN, BIC, titulaire) avec une clé AES-256
 * éphémère, puis chiffre cette clé AES avec la clé publique RSA du backend.
 *
 * Le payload en clair ne transite jamais sur le réseau : seul le résultat
 * chiffré est renvoyé, prêt à être envoyé au backend.
 */
export async function encryptTransferPayload(
  payload: TransferPayload,
  publicKey: CryptoKey
): Promise<EncryptedTransferPayload> {
  // 1. Génère une clé AES-256-GCM éphémère, utilisée une seule fois
  const aesKey = await crypto.subtle.generateKey(
    { name: "AES-GCM", length: 256 },
    true,
    ["encrypt"]
  );
  const iv = crypto.getRandomValues(new Uint8Array(12));

  // 2. Chiffre le payload avec AES-GCM (confidentialité + intégrité)
  const encoded = new TextEncoder().encode(JSON.stringify(payload));
  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    aesKey,
    encoded
  );

  // 3. Exporte la clé AES brute et la chiffre avec RSA-OAEP
  const rawAesKey = await crypto.subtle.exportKey("raw", aesKey);
  const encryptedKey = await crypto.subtle.encrypt(
    { name: "RSA-OAEP" },
    publicKey,
    rawAesKey
  );

  return {
    encrypted_key: arrayBufferToBase64(encryptedKey),
    iv: arrayBufferToBase64(iv.buffer as ArrayBuffer),
    ciphertext: arrayBufferToBase64(ciphertext),
  };
}
