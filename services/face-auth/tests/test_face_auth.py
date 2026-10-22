"""face-auth : verrouillage, chiffrement des empreintes, routes internes (Keycloak)."""

import base64
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import numpy as np
import pytest
from cryptography.exceptions import InvalidTag

from face_auth import lockout
from face_auth.crypto import TemplateCipher
from face_auth.engine import FaceError
from face_auth.main import create_app
from face_auth.settings import Settings

TOKEN = "kc-face-token"
KEY_HEX = "00" * 32
ISSUER = "https://kc.test/realms/resilience"
INTERNAL = {"Authorization": f"Bearer {TOKEN}"}


class FakeEngine:
    """`face:<x>` -> empreinte propre à x ; `noface` -> aucun visage ; `two` -> deux visages."""

    def embed(self, image: bytes, *, single: bool = False) -> np.ndarray:
        if image == b"noface":
            raise FaceError("no_face")
        if image == b"two" and single:
            raise FaceError("multiple_faces")
        rng = np.random.default_rng(abs(hash(image)) % 2**32)
        v = rng.standard_normal(128).astype(np.float32)
        return v / np.linalg.norm(v)


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _app(**kw):
    settings = Settings(face_service_token=TOKEN, biometric_key=KEY_HEX, **kw)
    return create_app(settings, engine=FakeEngine())


def _client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _enroll(app, username: str, image: bytes) -> None:
    await app.state.biometrics.enroll(username, image, by="test")


async def _verify(c: httpx.AsyncClient, username: str, image: bytes) -> dict:
    r = await c.post(
        "/internal/verify", json={"username": username, "image": b64(image)}, headers=INTERNAL
    )
    assert r.status_code == 200, r.text
    return r.json()


# --- Règle de verrouillage -----------------------------------------------------------------


def test_lockout_one_retry_then_locked_5_minutes():
    t0 = datetime(2026, 10, 22, tzinfo=UTC)
    s = lockout.after_failure(lockout.LockState(), t0, max_failures=2, lock_s=300)
    assert not s.is_locked(t0) and lockout.attempts_left(s, 2) == 1
    s = lockout.after_failure(s, t0, max_failures=2, lock_s=300)
    assert s.is_locked(t0 + timedelta(seconds=299))
    assert not s.is_locked(t0 + timedelta(seconds=300))
    assert s.failures == 0  # « etc. » : après le verrou, de nouveau 1 essai + 1 recommencement


# --- Chiffrement ---------------------------------------------------------------------------


def test_template_bound_to_username():
    cipher = TemplateCipher.from_hex(KEY_HEX)
    v = FakeEngine().embed(b"face:a")
    blob = cipher.seal("operator", v)
    assert np.allclose(cipher.open("operator", blob), v)
    with pytest.raises(InvalidTag):
        cipher.open("alice", blob)  # empreinte recopiée sur une autre ligne


def test_missing_secrets_refuse_start():
    with pytest.raises(RuntimeError):
        create_app(Settings(biometric_key=KEY_HEX), engine=FakeEngine())
    with pytest.raises(RuntimeError):
        create_app(Settings(face_service_token=TOKEN), engine=FakeEngine())


# --- Routes internes (authenticator Keycloak) ---------------------------------------------


async def test_internal_requires_service_token():
    async with _client(_app()) as c:
        body = {"username": "operator", "image": b64(b"face:op")}
        assert (await c.post("/internal/verify", json=body)).status_code == 401
        bad = {"Authorization": "Bearer nope"}
        assert (await c.post("/internal/verify", json=body, headers=bad)).status_code == 401


async def test_match_resets_counter():
    app = _app()
    await _enroll(app, "operator", b"face:op")
    async with _client(app) as c:
        assert (await _verify(c, "operator", b"face:intrus"))["attempts_left"] == 1
        r = await _verify(c, "Operator", b"face:op")  # identifiant normalisé
        assert r["match"] is True and r["outcome"] == "match"
        assert (await _verify(c, "operator", b"face:intrus"))["attempts_left"] == 1


async def test_two_failures_lock_then_nothing_is_evaluated():
    app = _app()
    await _enroll(app, "operator", b"face:op")
    async with _client(app) as c:
        first = await _verify(c, "operator", b"face:intrus")
        assert first == {
            "match": False,
            "outcome": "no_match",
            "attempts_left": 1,
            "locked_until": None,
        }
        second = await _verify(c, "operator", b"face:intrus")
        assert second["outcome"] == "no_match" and second["locked_until"] is not None
        # Verrouillé : même le bon visage est refusé, sans évaluation.
        third = await _verify(c, "operator", b"face:op")
        assert third["outcome"] == "locked" and third["match"] is False
        st = (await c.get("/internal/users/operator/status", headers=INTERNAL)).json()
        assert st["locked_until"] is not None and st["attempts_left"] == 0


async def test_unreadable_capture_does_not_count():
    app = _app()
    await _enroll(app, "operator", b"face:op")
    async with _client(app) as c:
        for _ in range(3):
            assert (await _verify(c, "operator", b"noface"))["outcome"] == "no_face"
        assert (await _verify(c, "operator", b"face:op"))["match"] is True


async def test_not_enrolled_counts_as_failure():
    async with _client(_app()) as c:
        assert (await _verify(c, "ghost", b"face:x"))["outcome"] == "not_enrolled"
        assert (await _verify(c, "ghost", b"face:x"))["locked_until"] is not None


async def test_rejects_invalid_payloads():
    async with _client(_app()) as c:
        body = {"username": "operator", "image": "%%%"}
        assert (await c.post("/internal/verify", json=body, headers=INTERNAL)).status_code == 422
        body = {"username": "bad name!", "image": b64(b"face:x")}
        assert (await c.post("/internal/verify", json=body, headers=INTERNAL)).status_code == 422


# --- Moteur réel (modèles ONNX présents : image Docker, ou FACE_MODELS_DIR en local) -------

MODELS = Path(os.environ.get("FACE_MODELS_DIR", "/app/models"))


@pytest.mark.skipif(
    not (MODELS / "face_detection_yunet_2023mar.onnx").exists(), reason="modèles absents"
)
def test_real_engine_rejects_non_faces():
    import cv2

    from face_auth.engine import FaceEngine

    engine = FaceEngine(MODELS)
    with pytest.raises(FaceError, match="invalid_image"):
        engine.embed(b"pas une image")
    _, blank = cv2.imencode(".jpg", np.full((480, 640, 3), 127, np.uint8))
    with pytest.raises(FaceError, match="no_face"):
        engine.embed(blank.tobytes())
