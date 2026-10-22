import { afterEach, describe, expect, it, vi } from "vitest";
import { AssistantError, MAX_QUESTION_LENGTH, askAssistant, sourceLabel } from "./admin-assistant";

const ANSWER = {
  answer: "Le moteur bloque l'IP source puis vérifie la reprise.",
  sources: [
    {
      title: "RB-01 — Flood HTTP",
      file: "runbooks/RB-01-flood-http.md",
      section: "RB-01 — Flood HTTP > Actions de l'opérateur",
    },
  ],
};

function respond(status: number, body: unknown, contentType = "application/json") {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(typeof body === "string" ? body : JSON.stringify(body), {
      status,
      headers: { "Content-Type": contentType },
    })
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function failure(promise: Promise<unknown>): Promise<AssistantError> {
  const e = await promise.catch((err: unknown) => err);
  expect(e).toBeInstanceOf(AssistantError);
  return e as AssistantError;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("askAssistant", () => {
  it("envoie la question (rognée) avec le jeton, et renvoie réponse et sources", async () => {
    const fetchMock = respond(200, ANSWER);
    await expect(askAssistant("  Que faire ?  ", "tok")).resolves.toEqual(ANSWER);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/admin/assistant/ask");
    expect(init.method).toBe("POST");
    expect(init.headers.Authorization).toBe("Bearer tok");
    expect(JSON.parse(init.body)).toEqual({ question: "Que faire ?" });
  });

  it("refuse une question vide ou trop longue sans appeler l'API", async () => {
    const fetchMock = respond(200, ANSWER);
    expect((await failure(askAssistant("   ", "tok"))).code).toBe("invalid_question");
    const tooLong = "x".repeat(MAX_QUESTION_LENGTH + 1);
    expect((await failure(askAssistant(tooLong, "tok"))).code).toBe("invalid_question");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("reprend le code et le message rédigés par payment-api (503, 504, 502)", async () => {
    const detail = { code: "assistant_timeout", message: "L'assistant n'a pas répondu à temps." };
    respond(504, { detail });
    const e = await failure(askAssistant("Q ?", "tok"));
    expect([e.code, e.message]).toEqual([detail.code, detail.message]);
  });

  it("traduit un 504 HTML du WAF en délai dépassé", async () => {
    respond(504, "<html>504 Gateway Time-out</html>", "text/html");
    expect((await failure(askAssistant("Q ?", "tok"))).code).toBe("gateway_timeout");
  });

  it("distingue le 403 de rôle (payment-api) du 403 de ModSecurity", async () => {
    respond(403, { detail: "forbidden" });
    expect((await failure(askAssistant("Q ?", "tok"))).code).toBe("forbidden");

    respond(403, "<html>403 Forbidden</html>", "text/html");
    expect((await failure(askAssistant("Q ?", "tok"))).code).toBe("blocked_by_waf");
  });

  it("signale une session expirée sur 401", async () => {
    respond(401, { detail: "invalid_token" });
    expect((await failure(askAssistant("Q ?", "tok"))).code).toBe("session_expired");
  });

  it("rejette une réponse 200 hors contrat", async () => {
    respond(200, { answer: "sans sources" });
    expect((await failure(askAssistant("Q ?", "tok"))).code).toBe("unexpected");
  });

  it("signale une panne réseau, mais laisse passer une annulation volontaire", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    expect((await failure(askAssistant("Q ?", "tok"))).code).toBe("network");

    const controller = new AbortController();
    const abortError = new DOMException("Aborted", "AbortError");
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => {
      controller.abort();
      return Promise.reject(abortError);
    }));
    await expect(askAssistant("Q ?", "tok", controller.signal)).rejects.toBe(abortError);
  });
});

describe("sourceLabel", () => {
  it("garde le titre et la dernière partie du chemin de titres", () => {
    expect(sourceLabel(ANSWER.sources[0])).toEqual({
      title: "RB-01 — Flood HTTP",
      section: "Actions de l'opérateur",
    });
  });

  it("n'ajoute pas de section quand le fragment est le document entier", () => {
    expect(sourceLabel({ title: "Index", file: "README.md", section: "Index" }).section).toBeNull();
  });
});
