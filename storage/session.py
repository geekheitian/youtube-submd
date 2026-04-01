from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from storage.models import Base


_engine = None
_SessionMaker = None


def init_storage(database_url: str) -> None:
    global _engine, _SessionMaker
    _engine = create_engine(database_url, pool_pre_ping=True, pool_size=5)
    _SessionMaker = sessionmaker(bind=_engine)
    Base.metadata.create_all(_engine)


def get_session() -> Generator[Session, None, None]:
    if _SessionMaker is None:
        raise RuntimeError("Storage not initialized. Call init_storage first.")
    session = _SessionMaker()
    try:
        yield session
    finally:
        session.close()
