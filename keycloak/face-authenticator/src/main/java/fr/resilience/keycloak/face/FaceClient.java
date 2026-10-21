package fr.resilience.keycloak.face;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Map;

import org.keycloak.util.JsonSerialization;

/**
 * Client des routes /internal du service face-auth (réseau Docker interne).
 *
 * Configuration par l'environnement de Keycloak :
 * FACE_AUTH_URL (défaut http://face-auth:8000) et FACE_AUTH_TOKEN_FILE
 * (défaut /run/secrets/face_service_token), jeton partagé avec face-auth.
 */
final class FaceClient {

    /** Réponse de face-auth. outcome : match | no_match | not_enrolled | locked | no_face | invalid_image. */
    record Verdict(String outcome, int attemptsLeft, String lockedUntil) {
        boolean match() {
            return "match".equals(outcome);
        }
    }

    private static final Duration TIMEOUT = Duration.ofSeconds(5);

    // HTTP/1.1 explicite : sinon tentative d'upgrade h2c, que uvicorn refuse (bruit dans les logs).
    private final HttpClient http = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(TIMEOUT)
            .build();
    private final String baseUrl;
    private final Path tokenFile;

    FaceClient(String baseUrl, Path tokenFile) {
        this.baseUrl = baseUrl.replaceAll("/+$", "");
        this.tokenFile = tokenFile;
    }

    static FaceClient fromEnv() {
        String url = System.getenv().getOrDefault("FACE_AUTH_URL", "http://face-auth:8000");
        String file = System.getenv().getOrDefault("FACE_AUTH_TOKEN_FILE", "/run/secrets/face_service_token");
        return new FaceClient(url, Path.of(file));
    }

    /** État du verrou avant d'allumer la caméra (outcome "locked" ou "ready"). */
    Verdict status(String username) throws IOException, InterruptedException {
        String path = "/internal/users/" + URLEncoder.encode(username, StandardCharsets.UTF_8) + "/status";
        Map<String, Object> body = send(request(path).GET().build());
        Object locked = body.get("locked_until");
        return new Verdict(locked == null ? "ready" : "locked", toInt(body.get("attempts_left")),
                locked == null ? null : locked.toString());
    }

    Verdict verify(String username, String image) throws IOException, InterruptedException {
        String json = JsonSerialization.writeValueAsString(Map.of("username", username, "image", image));
        Map<String, Object> body = send(request("/internal/verify")
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(json))
                .build());
        Object locked = body.get("locked_until");
        return new Verdict(String.valueOf(body.get("outcome")), toInt(body.get("attempts_left")),
                locked == null ? null : locked.toString());
    }

    private HttpRequest.Builder request(String path) throws IOException {
        // Relu à chaque appel : une rotation du secret (Vault) ne demande pas de redémarrer Keycloak.
        String token = Files.readString(tokenFile).strip();
        return HttpRequest.newBuilder(URI.create(baseUrl + path))
                .timeout(TIMEOUT)
                .header("Authorization", "Bearer " + token);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> send(HttpRequest req) throws IOException, InterruptedException {
        HttpResponse<String> res = http.send(req, HttpResponse.BodyHandlers.ofString());
        if (res.statusCode() != 200) {
            throw new IOException("face-auth HTTP " + res.statusCode());
        }
        return JsonSerialization.readValue(res.body(), Map.class);
    }

    private static int toInt(Object value) {
        return value instanceof Number n ? n.intValue() : 0;
    }
}
