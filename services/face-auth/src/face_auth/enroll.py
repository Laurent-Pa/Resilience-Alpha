"""Enrôlement en ligne de commande : amorce le premier opérateur.

Le back-office exige déjà le visage pour s'y connecter : le tout premier enrôlement se
fait donc hors back-office, depuis le conteneur, avec une photo du titulaire :

    docker compose cp photo.jpg face-auth:/tmp/photo.jpg
    docker compose exec face-auth python -m face_auth.enroll operator /tmp/photo.jpg

Les suivants passent par la page « Biométrie » du back-office.
"""

import argparse
import asyncio
from pathlib import Path

from face_auth.engine import FaceError
from face_auth.main import make_biometrics
from face_auth.service import normalize_username
from face_auth.settings import Settings


async def _run(username: str, image: bytes) -> None:
    bio = make_biometrics(Settings.load())
    await bio.store.open()
    try:
        await bio.enroll(normalize_username(username), image, by="cli")
        await bio.unlock(normalize_username(username), by="cli")
    finally:
        await bio.store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("username")
    parser.add_argument("image", type=Path, help="JPEG/PNG avec un seul visage, de face")
    args = parser.parse_args()
    try:
        asyncio.run(_run(args.username, args.image.read_bytes()))
    except FaceError as exc:
        raise SystemExit(f"Échec : {exc.code}") from exc
    print(f"{args.username} enrôlé.")


if __name__ == "__main__":
    main()
