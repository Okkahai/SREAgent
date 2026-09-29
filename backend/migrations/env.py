from alembic import context
from sqlalchemy import create_engine

from opspilot.config import get_settings

config = context.config


def run_migrations_online() -> None:
    url = config.get_main_option("sqlalchemy.url") or get_settings().database_url
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations_online()
