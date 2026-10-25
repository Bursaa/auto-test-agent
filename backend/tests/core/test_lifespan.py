import asyncio
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI

from app.core import lifespan as lifespan_module


@pytest.fixture
def wiring(monkeypatch):
    engine = MagicMock()
    session_factory = MagicMock()
    create_engine = MagicMock(return_value=engine)
    initialize = MagicMock()
    monkeypatch.setattr(lifespan_module, "create_database_engine", create_engine)
    monkeypatch.setattr(lifespan_module, "create_session_factory", MagicMock(return_value=session_factory))
    monkeypatch.setattr(lifespan_module, "initialize", initialize)
    app = FastAPI()
    app.state.database_url = "postgresql+psycopg://user:pw@localhost/taskly"
    return app, engine, session_factory, create_engine, initialize


def test_lifespan_initializes_database_and_disposes_engine(wiring):
    app, engine, session_factory, create_engine, initialize = wiring

    async def run():
        async with lifespan_module.lifespan(app):
            assert app.state.session_factory is session_factory
            engine.dispose.assert_not_called()

    asyncio.run(run())

    create_engine.assert_called_once_with(app.state.database_url)
    initialize.assert_called_once_with(engine)
    engine.dispose.assert_called_once_with()


def test_lifespan_disposes_engine_when_initialization_fails(wiring):
    app, engine, _, _, initialize = wiring
    initialize.side_effect = RuntimeError("database unavailable")

    async def run():
        async with lifespan_module.lifespan(app):
            pass

    with pytest.raises(RuntimeError, match="database unavailable"):
        asyncio.run(run())

    engine.dispose.assert_called_once_with()
    assert not hasattr(app.state, "session_factory")
