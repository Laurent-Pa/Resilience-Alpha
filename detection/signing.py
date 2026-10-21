# ===================================================================
# Signature HMAC des webhooks envoyés au remediation-engine.
# Réplique resilience_common.hmac (le moteur vérifie avec le MÊME algo) :
#   X-Signature = "sha256=" + HMAC_SHA256(secret, corps_brut).hexdigest()
# Le corps SIGNÉ doit être exactement le corps ENVOYÉ (octets bruts).
# ===================================================================
import hashlib
import hmac

PREFIX = "sha256="


def signer(secret: bytes, corps: bytes) -> str:
    """Signature X-Signature du corps brut. `secret` et `corps` sont des octets."""
    return PREFIX + hmac.new(secret, corps, hashlib.sha256).hexdigest()
