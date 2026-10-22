"""Machine d'états : seules les transitions listées sont permises ; les autres lèvent."""

from remediation_engine.core.models import (
    DETECTED,
    ESCALATED,
    EXECUTING,
    RECOVERED,
    TRIAGED,
    VERIFYING,
)

TRANSITIONS: dict[str, set[str]] = {
    DETECTED: {TRIAGED, ESCALATED},
    TRIAGED: {EXECUTING, ESCALATED},
    EXECUTING: {VERIFYING, ESCALATED},
    VERIFYING: {RECOVERED, EXECUTING, ESCALATED},
}


class IllegalTransition(Exception):
    pass


def assert_transition(frm: str, to: str) -> None:
    if to not in TRANSITIONS.get(frm, set()):
        raise IllegalTransition(f"{frm} -> {to}")
