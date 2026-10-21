"""Routes appelées par l'authenticator Keycloak (réseau interne, jamais routées par le WAF).

Authentification par jeton partagé (`Authorization: Bearer <face_service_token>`) :
Keycloak n'a pas de JWT à présenter à ce stade, l'utilisateur n'est pas encore connecté.
"""

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from face_auth.lockout import attempts_left
from face_auth.schemas import StatusOut, VerifyIn, VerifyOut
from face_auth.service import Biometrics, InvalidUsername, normalize_username

_bearer = HTTPBearer(auto_error=False)


def require_service_token(
    request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)
) -> None:
    expected: bytes = request.app.state.service_token
    if credentials is None or not hmac.compare_digest(credentials.credentials.encode(), expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_service_token")


router = APIRouter(prefix="/internal", dependencies=[Depends(require_service_token)])


def _username(value: str) -> str:
    try:
        return normalize_username(value)
    except InvalidUsername as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_username") from exc


@router.get("/users/{username}/status")
async def user_status(username: str, request: Request) -> StatusOut:
    bio: Biometrics = request.app.state.biometrics
    state = await bio.status(_username(username))
    return StatusOut(
        locked_until=state.locked_until,
        attempts_left=0 if state.locked_until else attempts_left(state, bio.max_failures),
    )


@router.post("/verify")
async def verify(body: VerifyIn, request: Request) -> VerifyOut:
    bio: Biometrics = request.app.state.biometrics
    verdict = await bio.verify(_username(body.username), body.raw())
    return VerifyOut(
        match=verdict.match,
        outcome=verdict.outcome,
        attempts_left=verdict.attempts_left,
        locked_until=verdict.locked_until,
    )
