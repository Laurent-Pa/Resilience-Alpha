"""Actions autorisées (liste fermée) et construction de leurs paramètres VALIDÉS.

build_params lève si l'action ou un paramètre sort de la liste : l'orchestrateur n'exécute
alors rien et escalade. C'est la garde de sécurité du moteur (droits élevés sur les conteneurs).
"""

from ipaddress import IPv4Address
from typing import Literal

from pydantic import BaseModel, field_validator

from remediation_engine.core.models import Incident


class BlockIpParams(BaseModel):
    ip: IPv4Address

    @field_validator("ip")
    @classmethod
    def _blockable(cls, v: IPv4Address) -> IPv4Address:
        # On accepte toute IP : l'attaquant est sur le réseau privé et src_ip vient du WAF
        # (X-Forwarded-For). Seul le loopback est refusé : bloquer 127.0.0.1 couperait le moteur.
        if v.is_loopback:
            raise ValueError("ip_not_blockable")
        return v


class RecycleParams(BaseModel):
    service: Literal["payment-api", "keycloak"]


class KillConnsParams(BaseModel):
    db_role: Literal["payment_app"]


ALLOWED: dict[str, type[BaseModel]] = {
    "block_ip": BlockIpParams,
    "recycle_service": RecycleParams,
    "kill_db_conns": KillConnsParams,
}


def build_params(action: str, inc: Incident) -> BaseModel:
    model = ALLOWED[action]  # KeyError = action hors liste
    if action == "block_ip":
        return model(ip=inc.src_ip)
    if action == "recycle_service":
        return model(service=inc.target)
    return model(db_role="payment_app")
