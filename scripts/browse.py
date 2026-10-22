"""Trafic NORMAL simulé, pour la collecte de la détection (detection/collect.py).

Le pendant bienveillant de flood.py : les clients seedés (alice, bob, carol) se connectent comme
un navigateur (Authorization Code + PKCE sur `web-pay`, formulaires Keycloak), consultent leur
compte et leur historique, et se font des virements aléatoires entre eux, avec une pause
aléatoire entre deux actions. Le modèle apprend ainsi un « normal » qui contient de la
navigation, pas seulement la sonde (sinon un simple clic ressemble à une attaque).
Les montants circulent entre les trois comptes : rien à nettoyer, le ledger reste équilibré.

    # PC Hôte, via le WAF (lancer pendant `docker compose exec detection python collect.py 15`)
    uv run python scripts/browse.py --base https://<PUBLIC_HOST> --ca certs/lab-ca.pem -d 960
"""

import argparse
import asyncio
import base64
import hashlib
import html
import random
import re
import secrets
import time
import uuid
from collections import Counter
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from resilience_common.crypto import seal

# IBAN fictifs du seed de payment-api (seed.py).
USERS = {
    "alice": "FR7699999000011000000001132",
    "bob": "FR7699999000011000000002102",
    "carol": "FR7699999000011000000003169",
}
TOKEN_TTL_S = 240  # jetons Keycloak de 5 min : on se reconnecte avant l'expiration
# Poids des actions : on consulte bien plus souvent qu'on ne vire.
ACTIONS = {"account": 4, "history": 3, "public_key": 1, "transfer": 1}
FORM_ACTION = re.compile(r'<form[^>]*\baction="([^"]+)"')


def form_action(page: httpx.Response) -> str:
    m = FORM_ACTION.search(page.text)
    if not m:
        raise RuntimeError(f"formulaire Keycloak introuvable (HTTP {page.status_code})")
    return html.unescape(m.group(1))


async def login(args: argparse.Namespace, verify, username: str, password: str) -> str:
    """Connexion navigateur : identifiant, puis mot de passe (flux browser-face), puis code."""
    realm = f"{args.auth}/realms/resilience/protocol/openid-connect"
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    params = {
        "client_id": "web-pay",
        "response_type": "code",
        "scope": "openid",
        "redirect_uri": args.redirect_uri,
        "state": secrets.token_urlsafe(16),
        "code_challenge": challenge.rstrip(b"=").decode(),
        "code_challenge_method": "S256",
    }
    # Client dédié : chaque utilisateur a ses propres cookies de session Keycloak.
    async with httpx.AsyncClient(verify=verify, timeout=10.0) as kc:
        page = await kc.get(f"{realm}/auth?{urlencode(params)}")
        page = await kc.post(form_action(page), data={"username": username})
        page = await kc.post(form_action(page), data={"password": password})
        code = parse_qs(urlparse(page.headers.get("location", "")).query).get("code")
        if page.status_code != 302 or not code:
            raise RuntimeError(f"connexion de {username} refusée (HTTP {page.status_code})")
        tok = await kc.post(
            f"{realm}/token",
            data={
                "grant_type": "authorization_code",
                "client_id": "web-pay",
                "code": code[0],
                "redirect_uri": args.redirect_uri,
                "code_verifier": verifier,
            },
        )
        tok.raise_for_status()
        return tok.json()["access_token"]


async def user(client, args, verify, username, password, deadline, tally) -> None:
    names, weights = zip(*ACTIONS.items(), strict=True)
    others = [u for u in USERS if u != username]
    token, logged_at, pem = None, 0.0, None
    while time.monotonic() < deadline:
        await asyncio.sleep(random.uniform(args.min_wait, args.max_wait))  # noqa: S311
        action = random.choices(names, weights)[0]  # noqa: S311
        try:
            if time.monotonic() - logged_at > TOKEN_TTL_S:
                token, logged_at = await login(args, verify, username, password), time.monotonic()
                tally[f"login {username}"] += 1
            headers = {"Authorization": f"Bearer {token}"}
            if action == "account":
                r = await client.get(f"{args.base}/api/accounts/me", headers=headers)
            elif action == "history":
                r = await client.get(f"{args.base}/api/payments?limit=20", headers=headers)
            elif action == "public_key" or pem is None:
                action = "public_key"
                r = await client.get(f"{args.base}/api/payments/public-key")
                pem = r.json()["public_key"] if r.status_code == 200 else None
            else:
                dst = random.choice(others)  # noqa: S311
                amount = Decimal(random.randint(100, 3000)) / 100  # 1,00 € à 30,00 €  # noqa: S311
                beneficiary = {"iban": USERS[dst], "account_holder_name": dst.capitalize()}
                r = await client.post(
                    f"{args.base}/api/payments/transfer",
                    json={"amount": str(amount), **seal(pem, beneficiary)},
                    headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
                )
                if r.status_code == 400:  # decryption_failed : clé publique changée
                    pem = None
            outcome = f"{action} {r.status_code}"
        except Exception as e:  # réseau/TLS/login : on compte et on continue, comme un navigateur
            outcome = f"{action} {type(e).__name__}: {e}"
            logged_at = 0.0  # reconnexion à la prochaine action
        tally[outcome.split(":")[0]] += 1
        if args.verbose:
            print(f"{time.strftime('%H:%M:%S')} {username:5} {outcome}")


async def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--base", required=True, help="racine publique, ex. https://10.0.3.34")
    p.add_argument("--auth", help="racine Keycloak (défaut : <base>/auth)")
    p.add_argument("--redirect-uri", help="redirect autorisée pour web-pay (défaut : <base>/)")
    p.add_argument("--password-file", default=".secrets/test_users_password")
    p.add_argument("-d", "--duration", type=float, default=900.0, help="secondes")
    p.add_argument("--min-wait", type=float, default=2.0, help="pause min entre 2 actions (s)")
    p.add_argument("--max-wait", type=float, default=15.0, help="pause max entre 2 actions (s)")
    p.add_argument("--ca", help="bundle CA du WAF")
    p.add_argument("--insecure", action="store_true", help="ne pas vérifier le certificat WAF")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    assert 0 <= args.min_wait <= args.max_wait, "paramètres invalides"
    args.base = args.base.rstrip("/")
    args.auth = (args.auth or f"{args.base}/auth").rstrip("/")
    args.redirect_uri = args.redirect_uri or f"{args.base}/"
    # Lecture unique d'un petit fichier avant le trafic : le blocage est négligeable.
    password = Path(args.password_file).read_text().strip()  # noqa: ASYNC240

    verify: str | bool = args.ca if args.ca else (not args.insecure)
    tally: Counter = Counter()
    print(
        f"navigation simulée : {', '.join(USERS)} pendant {args.duration:.0f}s, "
        f"pause {args.min_wait}-{args.max_wait}s"
    )
    deadline = time.monotonic() + args.duration
    async with httpx.AsyncClient(verify=verify, timeout=10.0) as client:
        await asyncio.gather(
            *(user(client, args, verify, u, password, deadline, tally) for u in USERS)
        )

    total = sum(n for k, n in tally.items() if not k.startswith("login"))
    print(f"\n{total} actions en {args.duration:.0f}s ≈ {total / args.duration:.2f} req/s")
    for k, n in sorted(tally.items()):
        print(f"  {k}: {n}")


if __name__ == "__main__":
    asyncio.run(main())
