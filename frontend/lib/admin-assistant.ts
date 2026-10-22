/**
 * Client API de l'assistant documentaire (POST /api/admin/assistant/ask, rôle ops).
 *
 * payment-api relaie vers rag-assistant (pilier IA), qui répond à partir de
 * docs/exploitation/ en citant ses sources. Contrat : contracts/openapi-payment.json.
 * Sur le CPU du PC Hôte, une réponse prend de l'ordre d'une minute.
 */

const ADMIN_API_BASE = process.env.NEXT_PUBLIC_ADMIN_API_BASE_URL ?? "/api/admin";

/** Mêmes bornes que l'API (AssistantQuestion) : vérifiées avant l'envoi. */
export const MAX_QUESTION_LENGTH = 2000;

export interface AssistantSource {
  title: string;
  file: string; // relatif à docs/exploitation/, ex. "runbooks/RB-01-flood-http.md"
  section: string; // chemin des titres, "h1 > h2 > h3"
}

export interface AssistantAnswer {
  answer: string;
  sources: AssistantSource[];
}

/** Échec présentable tel quel à l'opérateur (`message` est en français). */
export class AssistantError extends Error {
  constructor(
    readonly code: string,
    message: string
  ) {
    super(message);
    this.name = "AssistantError";
  }
}

const MESSAGES: Record<string, string> = {
  session_expired: "Session expirée : reconnectez-vous au back-office.",
  forbidden: "Accès réservé aux comptes avec le rôle « ops ».",
  invalid_question: `Question invalide : entre 1 et ${MAX_QUESTION_LENGTH} caractères.`,
  blocked_by_waf:
    "Question bloquée par le pare-feu applicatif (WAF). Reformulez-la sans code ni caractères spéciaux.",
  gateway_timeout: "Pas de réponse dans le délai imparti. Réessayez dans un instant.",
  network: "Connexion au serveur impossible. Vérifiez le réseau puis réessayez.",
  unexpected: "Réponse inattendue du serveur. Réessayez dans un instant.",
};

function error(code: string): AssistantError {
  return new AssistantError(code, MESSAGES[code] ?? MESSAGES.unexpected);
}

/** Corps JSON s'il y en a un (les erreurs du WAF sont des pages HTML). */
async function jsonBody(res: Response): Promise<unknown> {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

function apiDetail(body: unknown): unknown {
  return body && typeof body === "object" && "detail" in body ? body.detail : undefined;
}

/** Erreur d'API au format {detail: {code, message}} (payment-api). */
function apiError(body: unknown): AssistantError | null {
  const detail = apiDetail(body);
  if (
    detail &&
    typeof detail === "object" &&
    "code" in detail &&
    "message" in detail &&
    typeof detail.code === "string" &&
    typeof detail.message === "string"
  ) {
    return new AssistantError(detail.code, detail.message);
  }
  return null;
}

function isAnswer(body: unknown): body is AssistantAnswer {
  if (!body || typeof body !== "object") return false;
  const b = body as Partial<AssistantAnswer>;
  return typeof b.answer === "string" && Array.isArray(b.sources);
}

/**
 * Pose une question. Lève AssistantError (message prêt à afficher), ou l'AbortError
 * du `signal` si l'opérateur annule.
 */
export async function askAssistant(
  question: string,
  accessToken: string | null,
  signal?: AbortSignal
): Promise<AssistantAnswer> {
  const trimmed = question.trim();
  if (trimmed.length === 0 || trimmed.length > MAX_QUESTION_LENGTH) {
    throw error("invalid_question");
  }

  let res: Response;
  try {
    res = await fetch(`${ADMIN_API_BASE}/assistant/ask`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
      body: JSON.stringify({ question: trimmed }),
      signal,
    });
  } catch (e) {
    if (signal?.aborted) throw e; // annulation volontaire : pas une panne
    throw error("network");
  }

  const body = await jsonBody(res);
  if (res.ok) {
    if (isAnswer(body)) return body;
    throw error("unexpected");
  }

  switch (res.status) {
    case 401:
      throw error("session_expired");
    case 403:
      // 403 JSON de payment-api (rôle manquant) ou page HTML de ModSecurity.
      throw apiDetail(body) === "forbidden" ? error("forbidden") : error("blocked_by_waf");
    case 422:
      throw error("invalid_question");
    default:
      // 502/503/504 de payment-api : {code, message} déjà rédigés pour l'opérateur.
      // Sinon (504 HTML du WAF, 5xx sans corps) : message générique.
      throw apiError(body) ?? error(res.status === 504 ? "gateway_timeout" : "unexpected");
  }
}

/**
 * Libellé court d'une source : le titre du document et la dernière partie du chemin de
 * titres (le titre h1 le répète déjà). Ex. "RB-01 — … › Actions de l'opérateur".
 */
export function sourceLabel(source: AssistantSource): { title: string; section: string | null } {
  const parts = source.section.split(" > ");
  const last = parts.length > 1 ? parts[parts.length - 1] : null;
  return { title: source.title, section: last };
}
