import os

import pytest

from app import create_app
from app.config import Config
from app.extensions import database


class LoadTestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    # Point at a throwaway Postgres so the concurrency proof exercises real
    # row-level locking; SQLite serializes writes and can't show contention.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://localhost/qr_attendance_test",
    )
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_size": int(os.environ.get("DB_POOL_SIZE", "20")),
        "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", "40")),
    }
    RATELIMIT_ENABLED = False


@pytest.fixture(scope="session")
def app():
    application = create_app(LoadTestConfig)
    yield application
    with application.app_context():
        database.drop_all()


@pytest.fixture(autouse=True)
def clean_schema(app):
    # Each test starts on an empty schema so counts can't leak across tests.
    with app.app_context():
        database.drop_all()
        database.create_all()
    yield
