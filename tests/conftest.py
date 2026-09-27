"""Test bootstrap.

`backend.config.env` validates its settings the moment it is imported and
every backend package pulls it in transitively, so the required keys are
placed in the environment before any `backend` module is loaded.  Real values
are never read: environment variables outrank the project's `.env` file.
"""

import os

os.environ.setdefault("ADMIN_USERNAME", "test-superadmin")
os.environ.setdefault("ADMIN_PASSWORD", "test-password")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("BOT_API_KEY", "test-bot-key")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.bot.panel_client as panel_client_module
import backend.db.engin as engin_module
from backend.db import crud
from backend.db.engin import Base
from backend.db.model import Panels


@pytest.fixture()
def db_session():
    """The session every test writes through — an in-memory database."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(autouse=True)
def _isolate_from_live_database(db_session, monkeypatch):
    """Redirect every module that opens the database on its own.

    `backend.db.engin` hardcodes `data/mitpanel.db`, the file this application
    serves production traffic from.  Patching the module globals here (rather
    than trusting each test to remember) means a test can never reach it.
    """
    factory = sessionmaker(bind=db_session.get_bind(), autoflush=False)
    monkeypatch.setattr(engin_module, "sessionLocal", factory)
    monkeypatch.setattr(panel_client_module, "sessionLocal", factory)
    yield


@pytest.fixture()
def marzban_panel(db_session) -> Panels:
    """A Marzban panel row the provisioning paths look up by name."""
    db_session.add(
        Panels(
            panel_type="marzban",
            name="panel-one",
            url="http://marzban.test:8000",
            username="sudo",
            password="sudo-pass",
        )
    )
    db_session.commit()
    return db_session.query(Panels).filter_by(name="panel-one").one()


@pytest.fixture()
def panel_client():
    """`backend.bot.panel_client` with the session redirected (done in the
    autouse fixture, re-exported here so tests can name what they use)."""
    return panel_client_module


@pytest.fixture()
def admin_row(db_session):
    def _get(username: str):
        db_session.expire_all()
        return crud.get_admin_by_username(db_session, username)

    return _get
