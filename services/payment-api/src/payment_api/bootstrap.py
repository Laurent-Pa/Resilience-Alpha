"""Démarrage : migrations Alembic puis seed. Lancé avant uvicorn dans le conteneur.

python -m payment_api.bootstrap
"""

import asyncio
from pathlib import Path

import structlog
from alembic import command
from alembic.config import Config

from payment_api.crypto import pseudonymizer_from
from payment_api.db import make_engine, make_sessionmaker
from payment_api.seed import seed
from payment_api.settings import Settings
from resilience_common.logging import configure_logging

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

log = structlog.get_logger()


def run_migrations(settings: Settings) -> None:
    cfg = Config(str(ALEMBIC_INI))
    cfg.attributes["url"] = settings.db_url()
    command.upgrade(cfg, "head")


async def run_seed(settings: Settings) -> None:
    engine = make_engine(settings)
    try:
        async with make_sessionmaker(engine)() as s:
            await seed(s, pseudonymizer_from(settings))
    finally:
        await engine.dispose()


def main() -> None:
    settings = Settings.load()
    configure_logging(settings.service_name, settings.log_level)
    run_migrations(settings)
    log.info("migrations.done")
    if settings.seed_on_start:
        asyncio.run(run_seed(settings))


if __name__ == "__main__":
    main()
