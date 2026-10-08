from logging.config import fileConfig

from sqlalchemy import Connection

from alembic import context
from app import models  # noqa: F401 -- register models with shared metadata
from app.core.config import get_settings
from app.database.base import Base
from app.database.session import create_database_engine

config = context.config
if config.config_file_name and config.get_section("loggers"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Tests can supply an isolated connection without touching development data.
    connection = config.attributes.get("connection")
    if connection is not None:
        configure_and_run(connection)
        return
    engine = create_database_engine(get_settings().database_url)
    try:
        with engine.connect() as connection:
            configure_and_run(connection)
    finally:
        engine.dispose()


def configure_and_run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
