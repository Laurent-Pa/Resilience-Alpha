"""IBAN : normalisation, validation (ISO 13616, clé mod 97) et génération d'IBAN français.

Les IBAN générés utilisent un code banque fictif : aucune donnée bancaire réelle.
"""

import re

FAKE_BANK_CODE = "99999"
FAKE_BRANCH_CODE = "00001"

_IBAN_RE = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$")


def normalize(raw: str) -> str:
    """Retire espaces et tirets, passe en majuscules (« fr76 9999 … » → « FR769999… »)."""
    return re.sub(r"[\s-]", "", raw).upper()


def _to_digits(s: str) -> str:
    # A=10, B=11, … Z=35
    return "".join(str(int(c, 36)) for c in s)


def is_valid(iban: str) -> bool:
    """`iban` doit déjà être normalisé."""
    if not _IBAN_RE.match(iban):
        return False
    rearranged = iban[4:] + iban[:4]
    return int(_to_digits(rearranged)) % 97 == 1


def rib_key(bank: str, branch: str, account: str) -> str:
    """Clé RIB française sur un numéro de compte numérique."""
    return f"{97 - (89 * int(bank) + 15 * int(branch) + 3 * int(account)) % 97:02d}"


def make_fr(account_number: int, bank: str = FAKE_BANK_CODE, branch: str = FAKE_BRANCH_CODE) -> str:
    account = f"{account_number % 10**11:011d}"
    bban = bank + branch + account + rib_key(bank, branch, account)
    check = 98 - int(_to_digits(bban + "FR00")) % 97
    return f"FR{check:02d}{bban}"


def mask(iban: str) -> str:
    """Seule forme persistée ou affichée : pays + 4 derniers caractères (« FR****8995 »)."""
    return f"{iban[:2]}****{iban[-4:]}"


def format_groups(iban: str) -> str:
    """Affichage par blocs de 4 : FR76 9999 9000 01…"""
    return " ".join(iban[i : i + 4] for i in range(0, len(iban), 4))
