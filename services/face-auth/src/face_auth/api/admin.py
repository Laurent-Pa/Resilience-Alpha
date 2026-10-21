"""Gestion des habilitations biométriques depuis le back-office (rôle ops).

Routées par le WAF sous /api/biometrics. Aucune image n'est renvoyée ni conservée :
l'API ne manipule que des empreintes chiffrées, jamais exposées.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from face_auth.engine import FaceError
from face_auth.schemas import AttemptOut, ImageIn, UserOut
from face_auth.service import Biometrics, InvalidUsername, normalize_username
from face_auth.store import now
from resilience_common.auth import Claims, require_role

router = APIRouter(prefix="/biometrics", tags=["biometrics"])

_ops = require_role("ops")


def _bio(request: Request) -> Biometrics:
    return request.app.state.biometrics


def _username(value: str) -> str:
    try:
        return normalize_username(value)
    except InvalidUsername as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"code": "invalid_username", "message": "Identifiant invalide."},
        ) from exc


def _actor(claims: Claims) -> str:
    return claims.username or str(claims.sub)


@router.get("/users")
async def list_users(request: Request, _: Claims = Depends(_ops)) -> list[UserOut]:
    """Utilisateurs enrôlés, plus ceux qui ont un compteur d'échecs ou un verrou en cours."""
    bio = _bio(request)
    enrollments = {e.username: e for e in await bio.store.list_enrollments()}
    locks = await bio.store.list_locks()
    at = now()
    out = []
    for username in sorted(enrollments.keys() | locks.keys()):
        e = enrollments.get(username)
        lock = locks.get(username)
        locked = lock is not None and lock.is_locked(at)
        if e is None and not locked and not (lock and lock.failures):
            continue
        out.append(
            UserOut(
                username=username,
                enrolled=e is not None,
                enrolled_at=e.enrolled_at if e else None,
                enrolled_by=e.enrolled_by if e else None,
                failures=lock.failures if lock else 0,
                locked_until=lock.locked_until if locked and lock else None,
            )
        )
    return out


@router.put("/users/{username}/face", status_code=status.HTTP_201_CREATED)
async def enroll(
    username: str, body: ImageIn, request: Request, claims: Claims = Depends(_ops)
) -> UserOut:
    """Enregistre (ou remplace) la référence faciale. L'image doit contenir un seul visage."""
    try:
        e = await _bio(request).enroll(_username(username), body.raw(), by=_actor(claims))
    except FaceError as exc:
        messages = {
            "invalid_image": "Image illisible.",
            "no_face": "Aucun visage détecté.",
            "multiple_faces": "Plusieurs visages détectés : un seul attendu.",
        }
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"code": exc.code, "message": messages[exc.code]},
        ) from exc
    return UserOut(
        username=e.username,
        enrolled=True,
        enrolled_at=e.enrolled_at,
        enrolled_by=e.enrolled_by,
        failures=0,
        locked_until=None,
    )


@router.delete("/users/{username}/face", status_code=status.HTTP_204_NO_CONTENT)
async def revoke(username: str, request: Request, claims: Claims = Depends(_ops)) -> Response:
    if not await _bio(request).revoke(_username(username), by=_actor(claims)):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, {"code": "not_enrolled", "message": "Aucun enrôlement."}
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/users/{username}/unlock", status_code=status.HTTP_204_NO_CONTENT)
async def unlock(username: str, request: Request, claims: Claims = Depends(_ops)) -> Response:
    await _bio(request).unlock(_username(username), by=_actor(claims))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/attempts")
async def attempts(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    _: Claims = Depends(_ops),
) -> list[AttemptOut]:
    rows = await _bio(request).store.recent_attempts(limit)
    return [
        AttemptOut(username=a.username, at=a.at, outcome=a.outcome, score=a.score) for a in rows
    ]
