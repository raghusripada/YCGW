import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line forms part of the logger configuration
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import Base from your application's models
# IMPORTANT: Update this import path to match your project structure
from enableai_hub.core.database import Base, DATABASE_URL

# Import all your models here so Base.metadata is populated
from enableai_hub.auth.models import User, OAuth2Client, OAuth2AuthorizationCode, OAuth2Token, UserExternalToken, APIKey
from enableai_hub.tools.models import ToolDefinition

# Set target_metadata to your Base.metadata
target_metadata = Base.metadata

# Use the DATABASE_URL from your application for consistency
# This ensures Alembic uses the same database URL as your app.
# You might need to adjust how DATABASE_URL is obtained if it's not directly importable
# or if you use a settings management system (e.g., Pydantic AppSettings).
# For this example, we assume DATABASE_URL is accessible.
# If config.get_main_option("sqlalchemy.url") is already set correctly in alembic.ini,
# this explicit setting might not be strictly necessary but ensures clarity.
effective_db_url = config.get_main_option("sqlalchemy.url", DATABASE_URL)
if effective_db_url == "driver://user:pass@localhost/dbname": # Default placeholder
    print("WARNING: alembic.ini sqlalchemy.url is using the default placeholder.")
    print(f"Attempting to use DATABASE_URL from core.database: {DATABASE_URL}")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
else:
    # Ensure the URL in alembic.ini is used if it's not the placeholder
    # Or, consistently override with DATABASE_URL if preferred.
    # For this setup, we'll prioritize alembic.ini if it's changed from placeholder.
    # However, for async, we need to ensure it's an asyncpg URL.
    if not effective_db_url.startswith("postgresql+asyncpg://"):
        print(f"Warning: sqlalchemy.url in alembic.ini ('{effective_db_url}') is not an asyncpg URL.")
        print(f"Overriding with DATABASE_URL from core.database for async: {DATABASE_URL}")
        config.set_main_option("sqlalchemy.url", DATABASE_URL)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata
        # Include other context options if needed for your models/migrations
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online_async() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online_async())
