"""Poste une alerte signée HMAC au remediation-engine (test d'intégration manuel).

    # moteur local sur :8003, secret dans WEBHOOK_HMAC_SECRET
    python scripts/fake_alert.py
    python scripts/fake_alert.py --target payment-api --src-ip 203.0.113.66

Puis observer la machine d'états en SSE :  curl -N "http://127.0.0.1:8003/events?token=<jwt_ops>"
"""

import argparse
import hashlib
import hmac
import json
import os
import urllib.request
from datetime import UTC, datetime


def sign(secret: bytes, body: bytes) -> str:
    return "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", default=os.getenv("REMEDIATION_URL", "http://127.0.0.1:8003/alerts"))
    p.add_argument("--secret", default=os.getenv("WEBHOOK_HMAC_SECRET", "devsecret"))
    p.add_argument("--type", default="anomaly")
    p.add_argument("--target", default="payment-api")
    p.add_argument("--src-ip", default="8.8.8.8")  # routable : block_ip l'accepte (démo locale)
    args = p.parse_args()

    body = json.dumps(
        {
            "source": "ml",
            "type": args.type,
            "target": args.target,
            "src_ip": args.src_ip,
            "score": 0.93,
            "at": datetime.now(UTC).isoformat(),
        }
    ).encode()
    req = urllib.request.Request(  # noqa: S310 (URL de labo, fournie par l'utilisateur)
        args.url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Signature": sign(args.secret.strip().encode(), body),
        },
    )
    with urllib.request.urlopen(req, timeout=5) as r:  # noqa: S310
        print(r.status, r.read().decode())


if __name__ == "__main__":
    main()
