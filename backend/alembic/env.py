import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
try:
    fileConfig(config.config_file_name)
except Exception:
    # ignore logging configuration errors in test environments
    pass

# Import the project's metadata
from app.infrastructure.database.base import Base  # noqa: E402

target_metadata = Base.metadata


def get_database_url():
    # Prefer environment variable (DATABASE_URL) used by the application.
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    # Fallback to alembic.ini sqlalchemy.url if provided
    try:
        return config.get_main_option("sqlalchemy.url")
    except Exception:
        return None


def run_migrations_offline():
    url = get_database_url()
    if not url:
        raise RuntimeError("DATABASE_URL must be set for offline migrations")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    url = get_database_url()
    if not url:
        raise RuntimeError("DATABASE_URL must be set for online migrations")

    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        url=url,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
