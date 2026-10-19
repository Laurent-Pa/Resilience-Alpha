import { describe, it, expect, beforeAll } from "vitest";
import { webcrypto } from "node:crypto";
import {
  importPublicKey,
  encryptTransferPayload,
  type TransferPayload,
} from "./crypto";

/**
 * Tests de la feature de chiffrement IBAN (RSA-OAEP + AES-GCM).
 *
 * Ces tests simulent le rôle du backend : ils génèrent une paire de clés
 * RSA côté test (jouant le rôle du backend), exposent la clé publique au
 * code testé (comme le ferait GET /api/payments/public-key), puis
 * déchiffrent manuellement le résultat pour vérifier que ce que produit
 * `encryptTransferPayload` est bien ce qu'un vrai backend pourrait
 * déchiffrer avec sa clé privée.
 */

let publicKeyPem: string;
let privateKey: CryptoKey;

/**
 * Convertit un ArrayBuffer en PEM (format SPKI), à l'inverse de ce que fait
 * crypto.ts côté frontend pour l'import de la clé publique.
 */
function arrayBufferToPem(buffer: ArrayBuffer): string {
  const base64 = Buffer.from(buffer).toString("base64");
  const lines = base64.match(/.{1,64}/g) ?? [];
  return `-----BEGIN PUBLIC KEY-----\n${lines.join("\n")}\n-----END PUBLIC KEY-----`;
}

/**
 * Déchiffre manuellement le résultat de encryptTransferPayload, en jouant
 * le rôle du backend : RSA-OAEP sur la clé AES, puis AES-GCM sur le payload.
 */
async function decryptTransferPayload(
  encrypted: { encrypted_key: string; iv: string; ciphertext: string },
  privKey: CryptoKey
): Promise<TransferPayload> {
  const encryptedKeyBuffer = Buffer.from(encrypted.encrypted_key, "base64");
  const ivBuffer = Buffer.from(encrypted.iv, "base64");
  const ciphertextBuffer = Buffer.from(encrypted.ciphertext, "base64");

  const rawAesKey = await webcrypto.subtle.decrypt(
    { name: "RSA-OAEP" },
    privKey,
    encryptedKeyBuffer
  );

  const aesKey = await webcrypto.subtle.importKey(
    "raw",
    rawAesKey,
    { name: "AES-GCM" },
    false,
    ["decrypt"]
  );

  const decrypted = await webcrypto.subtle.decrypt(
    { name: "AES-GCM", iv: ivBuffer },
    aesKey,
    ciphertextBuffer
  );

  return JSON.parse(new TextDecoder().decode(decrypted));
}

beforeAll(async () => {
  // Génère une paire de clés RSA-2048, comme le ferait le backend au démarrage
  const keyPair = await webcrypto.subtle.generateKey(
    {
      name: "RSA-OAEP",
      modulusLength: 2048,
      publicExponent: new Uint8Array([1, 0, 1]),
      hash: "SHA-256",
    },
    true,
    ["encrypt", "decrypt"]
  );

  privateKey = keyPair.privateKey;
  const exportedPublicKey = await webcrypto.subtle.exportKey(
    "spki",
    keyPair.publicKey
  );
  publicKeyPem = arrayBufferToPem(exportedPublicKey);
});

describe("importPublicKey", () => {
  it("importe une clé publique PEM valide sans erreur", async () => {
    const key = await importPublicKey(publicKeyPem);
    expect(key).toBeDefined();
    expect(key.type).toBe("public");
  });

  it("rejette une clé PEM malformée", async () => {
    await expect(importPublicKey("ceci-n-est-pas-une-cle-pem")).rejects.toThrow();
  });
});

describe("encryptTransferPayload", () => {
  const payload: TransferPayload = {
    iban: "FR7630006000011234567890189",
    bic: "AGRIFRPP",
    account_holder_name: "Jean Dupont",
  };

  it("round-trip : le payload déchiffré correspond exactement au payload d'origine", async () => {
    const publicKey = await importPublicKey(publicKeyPem);
    const encrypted = await encryptTransferPayload(payload, publicKey);

    const decrypted = await decryptTransferPayload(encrypted, privateKey);

    expect(decrypted).toEqual(payload);
  });

  it("fonctionne sans BIC (champ optionnel)", async () => {
    const payloadWithoutBic: TransferPayload = {
      iban: "DE89370400440532013000",
      account_holder_name: "Maria Schmidt",
    };
    const publicKey = await importPublicKey(publicKeyPem);
    const encrypted = await encryptTransferPayload(payloadWithoutBic, publicKey);

    const decrypted = await decryptTransferPayload(encrypted, privateKey);

    expect(decrypted).toEqual(payloadWithoutBic);
    expect(decrypted.bic).toBeUndefined();
  });

  it("préserve les caractères Unicode (accents) dans le titulaire du compte", async () => {
    const payloadWithAccents: TransferPayload = {
      iban: "FR7630006000011234567890189",
      account_holder_name: "François Müller-Éléonore",
    };
    const publicKey = await importPublicKey(publicKeyPem);
    const encrypted = await encryptTransferPayload(payloadWithAccents, publicKey);

    const decrypted = await decryptTransferPayload(encrypted, privateKey);

    expect(decrypted.account_holder_name).toBe("François Müller-Éléonore");
  });

  it("produit un résultat différent à chaque appel (clé AES et IV éphémères)", async () => {
    const publicKey = await importPublicKey(publicKeyPem);
    const first = await encryptTransferPayload(payload, publicKey);
    const second = await encryptTransferPayload(payload, publicKey);

    expect(first.ciphertext).not.toBe(second.ciphertext);
    expect(first.iv).not.toBe(second.iv);
    expect(first.encrypted_key).not.toBe(second.encrypted_key);
  });

  it("détecte une altération du ciphertext (intégrité AES-GCM)", async () => {
    const publicKey = await importPublicKey(publicKeyPem);
    const encrypted = await encryptTransferPayload(payload, publicKey);

    // Altère un octet du ciphertext pour simuler une donnée corrompue/interceptée
    const tamperedBuffer = Buffer.from(encrypted.ciphertext, "base64");
    tamperedBuffer[0] = tamperedBuffer[0] ^ 0xff;
    const tampered = {
      ...encrypted,
      ciphertext: tamperedBuffer.toString("base64"),
    };

    await expect(decryptTransferPayload(tampered, privateKey)).rejects.toThrow();
  });
});
