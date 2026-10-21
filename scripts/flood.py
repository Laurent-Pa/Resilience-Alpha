"""Générateur de charge HTTP pour la démo de remédiation (lab fictif, réseau 192.168.137.x).

Deux attaques, depuis le PC Attaquant, pour déclencher la détection `http_flood` :

  --mode get       rafale de GET (défaut). Fait monter http_requests_total mais ne sature
                   pas la base (clé servie en mémoire) : signal HighRequestRate uniquement.
  --mode transfer  rafale de virements PROBE -> PROBE_SINK avec Idempotency-Key uniques.
                   Tous ciblent les mêmes lignes -> les SELECT ... FOR UPDATE se sérialisent,
                   chaque requête garde sa connexion -> le pool (15) sature et /health/ready
                   bascule en 503 (signal DbPoolSaturated). C'est ça qui "fait tomber" l'API.

    # get (local, sans auth)
    uv run python scripts/flood.py --url http://127.0.0.1:8001/api/payments/public-key -c 150 -d 30
    # transfer (local, nécessite Keycloak + realm up)
    uv run python scripts/flood.py --mode transfer --secret-file .secrets/prober_client_secret -c 50 -d 30

TLS du WAF auto-signé : --ca <bundle.pem>, ou --insecure si tu n'as pas le bundle.
"""

import argparse
import asyncio
import time
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

import httpx

DEFAULT_URL = "https://192.168.137.1/api/payments/public-key"
DEFAULT_BASE = "http://127.0.0.1:8001"
DEFAULT_TOKEN_URL = "http://localhost:8080/auth/realms/resilience/protocol/openid-connect/token"
PROBE_SINK_IBAN = "FR7699999000019000000000247"  # seed de payment-api


def log_line(verbose: bool, outcome: str, t0: float) -> None:
    if verbose:
        print(f"{datetime.now():%H:%M:%S.%f} {outcome} {(time.monotonic() - t0) * 1000:.0f}ms")


async def get_worker(client: httpx.AsyncClient, url: str, deadline: float, tally: Counter, verbose: bool) -> None:
    while time.monotonic() < deadline:
        t0 = time.monotonic()
        try:
            r = await client.get(url)
            tally[r.status_code] += 1
            outcome = f"GET {r.status_code}"
        except Exception as e:  # réseau/TLS/timeout : on compte et on continue la rafale
            tally[type(e).__name__] += 1
            outcome = type(e).__name__
        log_line(verbose, outcome, t0)


async def transfer_worker(
    client: httpx.AsyncClient, url: str, body_base: dict, headers: dict, pem: str,
    beneficiary: dict, deadline: float, tally: Counter, verbose: bool,
) -> None:
    from resilience_common.crypto import seal  # import tardif : seulement en mode transfer

    while time.monotonic() < deadline:
        t0 = time.monotonic()
        try:
            r = await client.post(
                url,
                json={**body_base, **seal(pem, beneficiary)},
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            )
            tally[r.status_code] += 1
            outcome = f"POST {r.status_code}"
        except Exception as e:
            tally[type(e).__name__] += 1
            outcome = type(e).__name__
        log_line(verbose, outcome, t0)


async def setup_transfer(client: httpx.AsyncClient, args: argparse.Namespace) -> tuple[str, dict, dict, str, dict]:
    """Jeton client_credentials + clé publique. Renvoie (url, body_base, headers, pem, beneficiary)."""
    secret = args.client_secret or Path(args.secret_file).read_text().strip()
    tok = await client.post(
        args.token_url,
        data={"grant_type": "client_credentials", "client_id": args.client_id, "client_secret": secret},
    )
    tok.raise_for_status()
    token = tok.json()["access_token"]
    key = await client.get(f"{args.base}/api/payments/public-key")
    key.raise_for_status()
    pem = key.json()["public_key"]
    beneficiary = {"iban": args.dst_iban, "account_holder_name": args.dst_name}
    return (
        f"{args.base}/api/payments/transfer",
        {"amount": args.amount},
        {"Authorization": f"Bearer {token}"},
        pem,
        beneficiary,
    )


async def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", choices=["get", "transfer"], default="get")
    p.add_argument("--url", default=DEFAULT_URL, help="mode get : cible complète")
    p.add_argument("-c", "--concurrency", type=int, default=150)
    p.add_argument("-d", "--duration", type=float, default=60.0, help="secondes")
    p.add_argument("--ca", help="bundle CA du WAF")
    p.add_argument("--insecure", action="store_true", help="ne pas vérifier le certificat WAF")
    p.add_argument("-v", "--verbose", action="store_true", help="logguer chaque requête")
    p.add_argument("--xff", help="X-Forwarded-For simulé (IP source, ex. 8.8.8.8 routable pour block_ip)")
    # mode transfer
    p.add_argument("--base", default=DEFAULT_BASE, help="racine de l'API (mode transfer)")
    p.add_argument("--token-url", default=DEFAULT_TOKEN_URL)
    p.add_argument("--client-id", default="prober")
    p.add_argument("--client-secret", help="secret en clair (sinon --secret-file)")
    p.add_argument("--secret-file", default=".secrets/prober_client_secret")
    p.add_argument("--dst-iban", default=PROBE_SINK_IBAN)
    p.add_argument("--dst-name", default="PROBE_SINK")
    p.add_argument("--amount", default="0.01", help="montant par virement (chaîne décimale)")
    args = p.parse_args()
    assert args.concurrency > 0 and args.duration > 0, "concurrency et duration doivent être > 0"

    verify: str | bool = args.ca if args.ca else (False if args.insecure else True)
    tally: Counter = Counter()
    limits = httpx.Limits(max_connections=args.concurrency, max_keepalive_connections=args.concurrency)
    deadline = time.monotonic() + args.duration
    # --xff : en-tête par défaut sur TOUTES les requêtes -> payment-api enregistre cette IP source.
    headers_def = {"X-Forwarded-For": args.xff} if args.xff else None
    async with httpx.AsyncClient(verify=verify, limits=limits, timeout=10.0, headers=headers_def) as client:
        if args.mode == "transfer":
            try:
                url, body_base, headers, pem, beneficiary = await setup_transfer(client, args)
            except Exception as e:
                raise SystemExit(
                    f"setup transfer impossible ({type(e).__name__}: {e}).\n"
                    "Vérifie que Keycloak + le realm sont up et que le secret client est correct."
                ) from None
            make = lambda: transfer_worker(  # noqa: E731
                client, url, body_base, headers, pem, beneficiary, deadline, tally, args.verbose
            )
            print(f"flood transfer {url} -> {args.dst_iban} — {args.concurrency} workers pendant {args.duration}s")
        else:
            url = args.url
            make = lambda: get_worker(client, url, deadline, tally, args.verbose)  # noqa: E731
            print(f"flood get {url} — {args.concurrency} workers pendant {args.duration}s")
        try:
            await asyncio.gather(*(make() for _ in range(args.concurrency)))
        except KeyboardInterrupt:
            pass

    total = sum(tally.values())
    print(f"\n{total} requêtes en {args.duration:.0f}s ≈ {total / args.duration:.0f} req/s")
    for k, n in sorted(tally.items(), key=lambda kv: -kv[1]):
        print(f"  {k}: {n}")


if __name__ == "__main__":
    asyncio.run(main())
