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

/**
 * Décode les rôles realm portés par le jeton d'accès (base64url, sans
 * vérification de signature : ceci ne sert qu'à décider quoi afficher côté
 * client, par ex. le lien "Administration" pour les comptes avec le rôle ops).
 */
export function rolesFromAccessToken(accessToken: string): string[] {
  try {
    const payload = accessToken.split(".")[1];
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    const claims = JSON.parse(json) as { realm_access?: { roles?: string[] } };
    return claims.realm_access?.roles ?? [];
  } catch {
    return [];
  }
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
