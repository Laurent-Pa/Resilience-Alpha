"""BIC (ISO 9362) : normalisation, validation, comparaison."""

import re

# BIC fictif de la banque. Un « 0 » en 8e position désigne un BIC de test SWIFT :
# il ne peut correspondre à aucun établissement réel.
DEFAULT_BIC = "RSALFRP0XXX"

_BIC_RE = re.compile(r"^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$")


def normalize(raw: str) -> str:
    return re.sub(r"\s", "", raw).upper()


def is_valid(bic: str) -> bool:
    return bool(_BIC_RE.match(bic))


def same_institution(a: str, b: str) -> bool:
    """BIC8 et BIC11 en « XXX » (agence principale) désignent le même établissement."""
    branch_a, branch_b = a[8:] or "XXX", b[8:] or "XXX"
    return a[:8] == b[:8] and (branch_a == branch_b or "XXX" in (branch_a, branch_b))
