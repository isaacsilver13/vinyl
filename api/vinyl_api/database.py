import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

DB_URL = os.environ.get("VINYL_API_DATABASE_URL", "sqlite:///./vinyl_api_dev.db")
_is_sqlite = "sqlite" in DB_URL

engine = create_engine(DB_URL, connect_args={"check_same_thread": False} if _is_sqlite else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


def init_db():
    # import models to register them with Base before creating tables
    from . import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
