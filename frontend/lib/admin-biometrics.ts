/**
 * Client API des habilitations biométriques (service face-auth, /api/biometrics, rôle ops).
 *
 * La reconnaissance faciale à la connexion se passe dans Keycloak (étape caméra entre
 * l'identifiant et le mot de passe) ; ce module ne sert qu'à gérer les enrôlements.
 * Les images envoyées ne sont jamais conservées : face-auth n'en garde qu'une empreinte chiffrée.
 */

const BIOMETRICS_API_BASE =
  process.env.NEXT_PUBLIC_BIOMETRICS_API_BASE_URL ?? "/api/biometrics";

export interface BiometricUser {
  username: string;
  enrolled: boolean;
  enrolled_at: string | null;
  enrolled_by: string | null;
  failures: number; // échecs consécutifs en cours
  locked_until: string | null; // non-null seulement si le verrou est actif
}

export type AttemptOutcome =
  | "match"
  | "no_match"
  | "not_enrolled"
  | "locked"
  | "no_face"
  | "invalid_image";

export interface BiometricAttempt {
  username: string;
  at: string;
  outcome: AttemptOutcome;
  score: number | null; // similarité cosinus, null si rien n'a été comparé
}

/** Erreur métier de l'API (`detail.code`), ex. no_face, multiple_faces, invalid_username. */
export class BiometricsError extends Error {
  constructor(
    readonly status: number,
    readonly code: string | null,
    message: string
  ) {
    super(message);
  }
}

async function call<T>(path: string, accessToken: string | null, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BIOMETRICS_API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = body?.detail;
    const code = typeof detail?.code === "string" ? detail.code : null;
    const message = typeof detail?.message === "string" ? detail.message : `HTTP ${res.status}`;
    throw new BiometricsError(res.status, code, message);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

const user = (username: string) => `/users/${encodeURIComponent(username)}`;

export function fetchBiometricUsers(accessToken: string | null): Promise<BiometricUser[]> {
  return call("/users", accessToken);
}

export function fetchBiometricAttempts(
  accessToken: string | null,
  limit = 20
): Promise<BiometricAttempt[]> {
  return call(`/attempts?limit=${limit}`, accessToken);
}

/** `image` : data URL JPEG (canvas.toDataURL), un seul visage. */
export function enrollFace(
  username: string,
  image: string,
  accessToken: string | null
): Promise<BiometricUser> {
  return call(`${user(username)}/face`, accessToken, {
    method: "PUT",
    body: JSON.stringify({ image }),
  });
}

export function revokeFace(username: string, accessToken: string | null): Promise<void> {
  return call(`${user(username)}/face`, accessToken, { method: "DELETE" });
}

export function unlockUser(username: string, accessToken: string | null): Promise<void> {
  return call(`${user(username)}/unlock`, accessToken, { method: "POST" });
}

export const OUTCOME_LABELS: Record<AttemptOutcome, string> = {
  match: "reconnu",
  no_match: "non reconnu",
  not_enrolled: "non enrôlé",
  locked: "bloqué",
  no_face: "aucun visage",
  invalid_image: "image illisible",
};
