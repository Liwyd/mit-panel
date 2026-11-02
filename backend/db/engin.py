from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from pathlib import Path
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

BASE_DIR = Path(__file__).resolve().parent

DATABASE_URL = f"sqlite:///{BASE_DIR.parent.parent}/data/mitpanel.db"
engin = create_engine(url=DATABASE_URL, connect_args={"check_same_thread": False})

Base = declarative_base()

sessionLocal = sessionmaker(bind=engin, autoflush=False)


def get_db():
    db = sessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_inbound_group_schema() -> None:
    """Add the optional group column/tables without rewriting live admin rows."""
    inspector = inspect(engin)
    if "admins" in inspector.get_table_names() and "inbound_group_id" not in {
        column["name"] for column in inspector.get_columns("admins")
    }:
        try:
            with engin.begin() as connection:
                connection.execute(text("ALTER TABLE admins ADD COLUMN inbound_group_id INTEGER"))
        except OperationalError:
            # Concurrent app workers can both inspect before either applies
            # this additive change. Suppress only if the other worker added it.
            current = inspect(engin)
            if "inbound_group_id" not in {c["name"] for c in current.get_columns("admins")}:
                raise
    from backend.db.model import AdminInboundGroups, InboundGroups

    try:
        Base.metadata.create_all(
            bind=engin,
            tables=[InboundGroups.__table__, AdminInboundGroups.__table__],
            checkfirst=True,
        )
    except OperationalError:
        # CREATE TABLE IF NOT EXISTS is safe under concurrent startup too; the
        # metadata check/create sequence can still race between two workers.
        tables = set(inspect(engin).get_table_names())
        if not {InboundGroups.__tablename__, AdminInboundGroups.__tablename__} <= tables:
            raise
