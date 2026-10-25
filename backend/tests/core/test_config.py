import pytest

from app.core import config
from app.core.config import resolve_database_url


@pytest.fixture(autouse=True)
def no_dotenv(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: False)


def test_explicit_argument_wins_over_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///env.db")

    assert resolve_database_url("sqlite:///explicit.db") == "sqlite:///explicit.db"


def test_database_url_environment_variable_is_used(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///env.db")

    assert resolve_database_url() == "sqlite:///env.db"


def test_url_is_built_from_postgres_variables(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_USER", "user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("POSTGRES_HOST", "db.example")
    monkeypatch.setenv("DB_PORT", "5433")
    monkeypatch.setenv("POSTGRES_DB", "taskly")

    assert (
        resolve_database_url()
        == "postgresql+psycopg://user:secret@db.example:5433/taskly"
    )


def test_missing_postgres_variable_raises_key_error(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_USER", raising=False)

    with pytest.raises(KeyError):
        resolve_database_url()
