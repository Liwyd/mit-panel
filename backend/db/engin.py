from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from pathlib import Path

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