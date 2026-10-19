"""Vérification des JWT Keycloak et contrôle des rôles.

On valide l'émetteur PUBLIC mais on récupère le JWKS en INTERNE. Le JWKS est mis en
cache : pendant une panne de Keycloak, les jetons déjà émis restent vérifiables.

Le vérificateur est lu dans `request.app.state.token_verifier`, ce qui permet aux tests
d'en injecter un pointant vers un JWKS local.
"""

from dataclasses import dataclass
from uuid import UUID

import jwt
import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool
from structlog.contextvars import bind_contextvars

log = structlog.get_logger()


@dataclass(frozen=True)
class Claims:
    sub: UUID
    roles: frozenset[str]
    username: str | None = None


class InvalidToken(Exception):
    pass


class JwksUnavailable(Exception):
    pass


class TokenVerifier:
    def __init__(self, issuer: str, jwks_url: str, audience: str, *, leeway_s: int = 10) -> None:
        self.issuer = issuer
        self.audience = audience
        self.leeway_s = leeway_s
        self._jwks = jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=300, timeout=2)

    def decode(self, token: str) -> Claims:
        """Bloquant (récupération JWKS possible) : appeler via un threadpool."""
        try:
            key = self._jwks.get_signing_key_from_jwt(token).key
            payload = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
                leeway=self.leeway_s,
                options={"require": ["exp", "iat", "sub"]},
            )
            return Claims(
                sub=UUID(payload["sub"]),
                roles=frozenset(payload.get("realm_access", {}).get("roles", [])),
                username=payload.get("preferred_username"),
            )
        except jwt.PyJWKClientConnectionError as exc:
            raise JwksUnavailable(str(exc)) from exc
        except (jwt.PyJWTError, ValueError, KeyError) as exc:
            raise InvalidToken(str(exc)) from exc


_bearer = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"}
    )


async def verify_token(request: Request, token: str) -> Claims:
    """Vérifie un jeton brut (utile aussi pour un jeton passé en query, cf. SSE)."""
    verifier: TokenVerifier = request.app.state.token_verifier
    try:
        claims = await run_in_threadpool(verifier.decode, token)
    except JwksUnavailable as exc:
        log.error("auth.jwks_unavailable", error=str(exc))
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "jwks_unavailable") from exc
    except InvalidToken as exc:
        log.warning("auth.rejected", reason=str(exc))
        raise _unauthorized("invalid_token") from exc
    bind_contextvars(user_id=str(claims.sub))
    return claims


async def current_claims(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Claims:
    if credentials is None:
        raise _unauthorized("missing_token")
    return await verify_token(request, credentials.credentials)


def require_role(*roles: str):
    """Dépendance FastAPI : exige au moins un des rôles realm listés."""
    allowed = frozenset(roles)

    async def dependency(claims: Claims = Depends(current_claims)) -> Claims:
        if not claims.roles & allowed:
            log.warning("auth.forbidden", required=sorted(allowed), roles=sorted(claims.roles))
            raise HTTPException(status.HTTP_403_FORBIDDEN, "forbidden")
        return claims

    return dependency
