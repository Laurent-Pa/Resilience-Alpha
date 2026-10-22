package fr.resilience.keycloak.face;

import java.util.List;

import org.keycloak.Config;
import org.keycloak.authentication.Authenticator;
import org.keycloak.authentication.AuthenticatorFactory;
import org.keycloak.models.AuthenticationExecutionModel.Requirement;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.KeycloakSessionFactory;
import org.keycloak.provider.ProviderConfigProperty;

public class FaceAuthenticatorFactory implements AuthenticatorFactory {

    /** Référencé par le flux `browser-face` de keycloak/realm-resilience.json. */
    public static final String ID = "face-recognition";

    private static final Requirement[] REQUIREMENTS = {Requirement.REQUIRED, Requirement.DISABLED};

    private FaceClient client;

    @Override
    public String getId() {
        return ID;
    }

    @Override
    public String getDisplayType() {
        return "Reconnaissance faciale (face-auth)";
    }

    @Override
    public String getHelpText() {
        return "Compare une capture de la caméra au visage enrôlé dans le service face-auth.";
    }

    @Override
    public String getReferenceCategory() {
        return "face";
    }

    @Override
    public Requirement[] getRequirementChoices() {
        return REQUIREMENTS;
    }

    @Override
    public boolean isConfigurable() {
        return false;
    }

    @Override
    public boolean isUserSetupAllowed() {
        return false;
    }

    @Override
    public List<ProviderConfigProperty> getConfigProperties() {
        return List.of();
    }

    @Override
    public Authenticator create(KeycloakSession session) {
        return new FaceAuthenticator(client);
    }

    @Override
    public void init(Config.Scope config) {
        client = FaceClient.fromEnv();
    }

    @Override
    public void postInit(KeycloakSessionFactory factory) {
    }

    @Override
    public void close() {
    }
}
