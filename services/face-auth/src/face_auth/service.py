"""Cas d'usage : vérifier un visage à la connexion, enrôler, révoquer, déverrouiller.

Issues d'une vérification (`outcome`) :
- `match`        : reconnu, compteur remis à zéro ;
- `no_match`     : visage différent de la référence, compte comme un échec ;
- `not_enrolled` : aucune référence, compte comme un échec (même réponse vue de Keycloak
                   qu'un `no_match` : on ne révèle pas qui est enrôlé) ;
- `locked`       : identifiant verrouillé, rien n'est évalué ;
- `no_face` / `invalid_image` : capture inexploitable, ne compte pas (l'utilisateur
                   recadre et recommence ; aucune de ces issues ne peut ouvrir l'accès).
"""

import asyncio
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

import structlog
from prometheus_client import Counter
from starlette.concurrency import run_in_threadpool

from face_auth import lockout
from face_auth.crypto import TemplateCipher
from face_auth.engine import Engine, FaceError, similarity
from face_auth.store import Attempt, Enrollment, Store, now

log = structlog.get_logger()

VERIFICATIONS = Counter("face_verifications_total", "Vérifications faciales", ["outcome"])
ENROLLMENTS = Counter("face_enrollments_total", "Opérations d'enrôlement", ["action"])

USERNAME_RE = re.compile(r"^[a-z0-9._@-]{1,255}$")
COUNTED = {"no_match", "not_enrolled"}


class InvalidUsername(ValueError):
    pass


def normalize_username(username: str) -> str:
    """Keycloak stocke les identifiants en minuscules."""
    value = username.strip().lower()
    if not USERNAME_RE.match(value):
        raise InvalidUsername(username)
    return value


@dataclass(frozen=True)
class Verdict:
    outcome: str
    attempts_left: int
    locked_until: datetime | None
    score: float | None = None

    @property
    def match(self) -> bool:
        return self.outcome == "match"


class Biometrics:
    def __init__(
        self,
        store: Store,
        engine: Engine,
        cipher: TemplateCipher,
        *,
        threshold: float,
        max_failures: int,
        lock_s: float,
    ) -> None:
        self.store = store
        self.engine = engine
        self.cipher = cipher
        self.threshold = threshold
        self.max_failures = max_failures
        self.lock_s = lock_s
        # Une vérification à la fois par identifiant : deux captures simultanées ne
        # doivent pas lire le même compteur d'échecs et s'offrir chacune un essai.
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def status(self, username: str) -> lockout.LockState:
        state = await self.store.get_lock(username)
        return state if state.is_locked(now()) else lockout.LockState(failures=state.failures)

    async def verify(self, username: str, image: bytes) -> Verdict:
        async with self._locks[username]:
            verdict = await self._verify(username, image)
        VERIFICATIONS.labels(verdict.outcome).inc()
        await self.store.add_attempt(Attempt(username, now(), verdict.outcome, verdict.score))
        log.info(
            "face.verify",
            username=username,
            outcome=verdict.outcome,
            score=verdict.score,
            attempts_left=verdict.attempts_left,
        )
        return verdict

    async def _verify(self, username: str, image: bytes) -> Verdict:
        at = now()
        state = await self.store.get_lock(username)
        if state.is_locked(at):
            return Verdict("locked", 0, state.locked_until)

        def unchanged(outcome: str, score: float | None = None) -> Verdict:
            left = lockout.attempts_left(state, self.max_failures)
            return Verdict(outcome, left, None, score)

        enrollment = await self.store.get_enrollment(username)
        score: float | None = None
        if enrollment is None:
            outcome = "not_enrolled"
        else:
            try:
                probe = await run_in_threadpool(self.engine.embed, image)
            except FaceError as exc:
                return unchanged(exc.code)
            reference = self.cipher.open(username, enrollment.template)
            score = round(similarity(probe, reference), 4)
            outcome = "match" if score >= self.threshold else "no_match"

        if outcome == "match":
            await self.store.set_lock(username, lockout.after_success())
            return Verdict("match", self.max_failures, None, score)
        state = lockout.after_failure(state, at, self.max_failures, self.lock_s)
        await self.store.set_lock(username, state)
        if state.locked_until:
            log.warning("face.locked", username=username, locked_until=state.locked_until)
            return Verdict(outcome, 0, state.locked_until, score)
        return Verdict(outcome, lockout.attempts_left(state, self.max_failures), None, score)

    async def enroll(self, username: str, image: bytes, by: str) -> Enrollment:
        """Lève FaceError si l'image ne contient pas exactement un visage."""
        embedding = await run_in_threadpool(self.engine.embed, image, single=True)
        enrollment = Enrollment(username, self.cipher.seal(username, embedding), now(), by)
        await self.store.save_enrollment(enrollment)
        ENROLLMENTS.labels("enroll").inc()
        log.info("face.enrolled", username=username, enrolled_by=by)
        return enrollment

    async def unlock(self, username: str, by: str) -> None:
        await self.store.set_lock(username, lockout.LockState())
        log.info("face.unlocked", username=username, unlocked_by=by)
