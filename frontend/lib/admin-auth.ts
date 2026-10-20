/**
 * Authentification Keycloak pour le back-office (client public `web-ops`,
 * Authorization Code + PKCE). Même realm que le front paiement (lib/auth.ts),
 * mais client dédié : web-ops exige le rôle realm `ops` (vérifié aussi, et
 * réellement, côté API — ceci ne sert qu'à l'affichage côté client).
 */

import { UserManager } from "oidc-client-ts";

let manager: UserManager | null = null;

// Instancié à la demande : window n'existe pas pendant le rendu serveur.
export function adminUserManager(): UserManager {
  manager ??= new UserManager({
    authority:
      process.env.NEXT_PUBLIC_OIDC_AUTHORITY ??
      "https://192.168.137.1/auth/realms/resilience",
    client_id: process.env.NEXT_PUBLIC_ADMIN_OIDC_CLIENT_ID ?? "web-ops",
    redirect_uri: `${window.location.origin}/admin/callback`,
    post_logout_redirect_uri: `${window.location.origin}/admin/login`,
    automaticSilentRenew: true,
  });
  return manager;
}

/**
 * Décode les rôles realm portés par le jeton d'accès (base64url, sans
 * vérification de signature : la vérification réelle a lieu côté API à
 * chaque appel — ceci ne sert qu'à décider quoi afficher côté client).
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
export function adminLogin(returnTo = window.location.pathname): Promise<void> {
  return adminUserManager().signinRedirect({ state: returnTo });
}

/** Ferme aussi la session Keycloak, puis renvoie vers l'écran de connexion admin. */
export function adminLogout(): Promise<void> {
  return adminUserManager().signoutRedirect();
}
