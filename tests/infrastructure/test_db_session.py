from sqlalchemy.engine import make_url

from upload_control_plane.config import Settings
from upload_control_plane.infrastructure.db.session import build_engine, build_session_factory


def test_default_database_url_targets_local_compose_postgres() -> None:
    settings = Settings()

    url = make_url(settings.database_url)

    assert url.drivername == "postgresql+psycopg"
    assert url.username == "upload"
    assert url.password == "upload"
    assert url.host == "localhost"
    assert url.port == 25432
    assert url.database == "upload"


def test_engine_and_session_factory_use_settings_database_url() -> None:
    settings = Settings(database_url="postgresql+psycopg://user:pass@example.test:15432/app")

    engine = build_engine(settings, echo=False)
    session_factory = build_session_factory(engine)

    assert str(engine.url) == "postgresql+psycopg://user:***@example.test:15432/app"
    assert session_factory.kw["autoflush"] is False
    assert session_factory.kw["expire_on_commit"] is False
