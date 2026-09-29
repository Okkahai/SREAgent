from sqlalchemy import create_engine, text


def check_database(url: str) -> None:
    """Raise if Postgres is unreachable."""
    engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 2})
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    finally:
        engine.dispose()
