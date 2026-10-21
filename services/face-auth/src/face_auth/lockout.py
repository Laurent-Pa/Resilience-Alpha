"""Règle de verrouillage, pure (sans I/O).

`max_failures` échecs consécutifs verrouillent l'identifiant `lock_s` secondes ; le compteur
repart alors de zéro (« recommencer 1 fois puis bloqué 5 minutes, etc. »). Un succès remet
le compteur à zéro. Pendant le verrou, aucune tentative n'est évaluée ni comptée.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta


@dataclass(frozen=True)
class LockState:
    failures: int = 0
    locked_until: datetime | None = None

    def is_locked(self, now: datetime) -> bool:
        return self.locked_until is not None and now < self.locked_until


def after_failure(state: LockState, now: datetime, max_failures: int, lock_s: float) -> LockState:
    failures = state.failures + 1
    if failures >= max_failures:
        return LockState(failures=0, locked_until=now + timedelta(seconds=lock_s))
    return replace(state, failures=failures)


def after_success() -> LockState:
    return LockState()


def attempts_left(state: LockState, max_failures: int) -> int:
    return max_failures - state.failures
