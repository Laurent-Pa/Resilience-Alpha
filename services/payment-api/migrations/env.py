import asyncio

from alembic import context
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from payment_api.models import SCHEMA, Base

config = context.config


def database_url():
    # Fourni par payment_api.bootstrap.run_migrations ; sinon, lu depuis la configuration.
    url = config.attributes.get("url")
    if url is None:
        from payment_api.settings import Settings

        url = Settings.load().db_url()
    return url


def do_run_migrations(connection) -> None:
    connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
    connection.commit()
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        version_table_schema=SCHEMA,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(database_url(), poolclass=NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    raise SystemExit("Le mode offline n'est pas supporté.")
asyncio.run(run_async_migrations())
