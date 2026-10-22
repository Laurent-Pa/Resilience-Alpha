package fr.resilience.keycloak.face;

import java.io.IOException;

import jakarta.ws.rs.core.MultivaluedMap;
import jakarta.ws.rs.core.Response;
import org.jboss.logging.Logger;
import org.keycloak.authentication.AuthenticationFlowContext;
import org.keycloak.authentication.AuthenticationFlowError;
import org.keycloak.authentication.Authenticator;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.RealmModel;
import org.keycloak.models.UserModel;

/**
 * Étape « caméra » du flux de connexion, placée après le formulaire d'identifiant et avant
 * celui du mot de passe (la condition « rôle ops » est portée par le flux, pas ici).
 *
 * Le navigateur capture une image (getUserMedia), la poste ici ; face-auth la compare à la
 * référence enrôlée et tient le compteur d'échecs (1 nouvel essai, puis verrou de 5 min).
 * Non reconnu : la caméra s'éteint et l'utilisateur repart de l'identifiant vide.
 * face-auth injoignable : refus (fail-closed), jamais de passage sans visage.
 */
public class FaceAuthenticator implements Authenticator {

    private static final Logger LOG = Logger.getLogger(FaceAuthenticator.class);
    static final String TEMPLATE = "face-auth.ftl";

    private final FaceClient client;

    FaceAuthenticator(FaceClient client) {
        this.client = client;
    }

    @Override
    public void authenticate(AuthenticationFlowContext context) {
        String username = context.getUser().getUsername();
        try {
            FaceClient.Verdict status = client.status(username);
            if ("locked".equals(status.outcome())) {
                context.challenge(page(context, "locked", null, status));
                return;
            }
            context.challenge(page(context, "capture", null, status));
        } catch (IOException | InterruptedException e) {
            unavailable(context, e);
        }
    }

    @Override
    public void action(AuthenticationFlowContext context) {
        MultivaluedMap<String, String> form = context.getHttpRequest().getDecodedFormParameters();
        if (form.containsKey("restart")) {
            // Retour à l'identifiant vide (caméra déjà éteinte côté navigateur).
            context.resetFlow();
            return;
        }
        String username = context.getUser().getUsername();
        String image = form.getFirst("image");
        if (image == null || image.isBlank()) {
            context.challenge(page(context, "capture", "Aucune image reçue, recommencez.", null));
            return;
        }
        FaceClient.Verdict verdict;
        try {
            verdict = client.verify(username, image);
        } catch (IOException | InterruptedException e) {
            unavailable(context, e);
            return;
        }
        switch (verdict.outcome()) {
            case "match" -> context.success();
            case "no_face", "invalid_image" -> context.challenge(page(context, "capture",
                    "Aucun visage détecté. Placez-vous face à la caméra et recommencez.", verdict));
            case "locked" -> context.challenge(page(context, "locked", null, verdict));
            default -> {
                // no_match, not_enrolled : même réponse, on ne révèle pas qui est enrôlé.
                context.getEvent().detail("reason", "face_not_recognized");
                String mode = verdict.lockedUntil() != null ? "locked" : "rejected";
                context.failureChallenge(AuthenticationFlowError.INVALID_CREDENTIALS,
                        page(context, mode, null, verdict));
            }
        }
    }

    private void unavailable(AuthenticationFlowContext context, Exception e) {
        if (e instanceof InterruptedException) {
            Thread.currentThread().interrupt();
        }
        LOG.errorf("face-auth injoignable : %s", e.toString());
        context.failureChallenge(AuthenticationFlowError.INTERNAL_ERROR, page(context, "unavailable", null, null));
    }

    private Response page(AuthenticationFlowContext context, String mode, String message, FaceClient.Verdict v) {
        return context.form()
                .setAttribute("faceMode", mode)
                .setAttribute("faceMessage", message == null ? "" : message)
                .setAttribute("faceAttemptsLeft", v == null ? 0 : v.attemptsLeft())
                .setAttribute("faceLockedUntil", v == null || v.lockedUntil() == null ? "" : v.lockedUntil())
                .createForm(TEMPLATE);
    }

    @Override
    public boolean requiresUser() {
        return true;
    }

    @Override
    public boolean configuredFor(KeycloakSession session, RealmModel realm, UserModel user) {
        // L'enrôlement vit dans face-auth : un ops non enrôlé passe par l'étape et échoue.
        return true;
    }

    @Override
    public void setRequiredActions(KeycloakSession session, RealmModel realm, UserModel user) {
    }

    @Override
    public void close() {
    }
}
