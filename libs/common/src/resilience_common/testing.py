"""Outils de test : clé RSA, jetons signés et JWKS servi en local.

Ne pas importer depuis le code de production.
"""

import json
import threading
import time
import uuid
from collections.abc import Iterable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm


class RsaKey:
    def __init__(self, kid: str | None = None) -> None:
        self.kid = kid or uuid.uuid4().hex
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def public_jwk(self) -> dict:
        jwk = RSAAlgorithm.to_jwk(self.private_key.public_key(), as_dict=True)
        return {**jwk, "kid": self.kid, "use": "sig", "alg": "RS256"}


def make_token(
    key: RsaKey,
    *,
    sub: uuid.UUID | str,
    roles: Iterable[str] = (),
    issuer: str,
    audience: str | list[str],
    expires_in: int = 300,
    **extra: object,
) -> str:
    now = int(time.time())
    payload = {
        "sub": str(sub),
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + expires_in,
        "realm_access": {"roles": list(roles)},
        **extra,
    }
    return jwt.encode(payload, key.private_key, algorithm="RS256", headers={"kid": key.kid})


class JwksServer:
    """Serveur HTTP local qui renvoie le JWKS des clés fournies, quel que soit le chemin."""

    def __init__(self, keys: Iterable[RsaKey]) -> None:
        body = json.dumps({"keys": [k.public_jwk() for k in keys]}).encode()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: object) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/certs"

    def __enter__(self) -> "JwksServer":
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._server.shutdown()
        self._server.server_close()
