/**
 * Authentification Keycloak (client public `web-pay`, Authorization Code + PKCE).
 * Le jeton est stocké en sessionStorage par oidc-client-ts et renouvelé
 * automatiquement par refresh token (durée de vie des jetons : 5 min).
 */

import { UserManager } from "oidc-client-ts";

let manager: UserManager | null = null;

// Instancié à la demande : window n'existe pas pendant le rendu serveur.
export function userManager(): UserManager {
  manager ??= new UserManager({
    authority:
      process.env.NEXT_PUBLIC_OIDC_AUTHORITY ??
      "https://192.168.137.1/auth/realms/resilience",
    client_id: process.env.NEXT_PUBLIC_OIDC_CLIENT_ID ?? "web-pay",
    redirect_uri: `${window.location.origin}/callback`,
    post_logout_redirect_uri: window.location.origin,
    automaticSilentRenew: true,
  });
  return manager;
}

/** Jeton d'accès valide, ou null si l'utilisateur doit se (re)connecter. */
export async function getAccessToken(): Promise<string | null> {
  const user = await userManager().getUser();
  return user && !user.expired ? user.access_token : null;
}

/** Redirige vers Keycloak ; on revient ensuite sur `returnTo`. */
export function login(returnTo = window.location.pathname): Promise<void> {
  return userManager().signinRedirect({ state: returnTo });
}

/** Ferme aussi la session Keycloak (sinon le login suivant serait automatique), puis renvoie vers l'écran de connexion. */
export function logout(): Promise<void> {
  return userManager().signoutRedirect({
    post_logout_redirect_uri: `${window.location.origin}/login`,
  });
}
