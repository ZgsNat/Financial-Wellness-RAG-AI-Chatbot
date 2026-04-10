import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from journal.database import Base
from journal.models import journal  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    return url


async def run_migrations_online() -> None:
    engine = create_async_engine(get_url())
    async with engine.connect() as conn:
        await conn.run_sync(lambda c: context.configure(connection=c, target_metadata=target_metadata))
        async with conn.begin():
            await conn.run_sync(lambda _: context.run_migrations())
    await engine.dispose()


def run_migrations_offline() -> None:
    context.configure(url=get_url(), target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())