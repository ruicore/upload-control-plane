from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from upload_control_plane.config import Settings


def build_engine(settings: Settings, *, echo: bool | None = None) -> Engine:
    return create_engine(
        settings.database_url,
        echo=settings.database_echo if echo is None else echo,
        pool_pre_ping=settings.database_pool_pre_ping,
    )


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
