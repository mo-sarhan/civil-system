"""Shared pytest fixtures.

Every test runs against ``civil_registry_test``. The schema is created once
per session by running the Alembic migrations, then each test truncates the
data tables so cases stay independent.
"""

from __future__ import annotations

import os
import pathlib
import sys
from collections.abc import Iterator

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("ENVIRONMENT", "testing")
os.environ["ENVIRONMENT"] = "testing"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres@127.0.0.1:5433/civil_registry_test",
)
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("IMPORT_STORAGE_DIR", str(BACKEND_ROOT / ".test-uploads"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from alembic import command  # noqa: E402
from alembic.config import Config as AlembicConfig  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402

TEST_PASSWORD = "Test#Pass1234"


def _alembic_config() -> AlembicConfig:
    config = AlembicConfig(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.sync_database_url)
    return config


@pytest.fixture(scope="session", autouse=True)
def _database() -> Iterator[None]:
    """Create the schema once for the whole test session."""
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    command.upgrade(_alembic_config(), "head")
    yield


@pytest.fixture(autouse=True)
def _reset_login_throttle() -> Iterator[None]:
    """The in-process login limiter would otherwise leak between tests."""
    from app.services.auth_service import login_throttle

    login_throttle.clear()
    yield
    login_throttle.clear()


@pytest.fixture(autouse=True)
def _clean_tables() -> Iterator[None]:
    """Empty every data table before each test."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE person, marriage, audit_log, import_job, "
                "import_mapping_template, users RESTART IDENTITY CASCADE"
            )
        )
    yield


@pytest.fixture
def db() -> Iterator[object]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def make_user(username: str, role: str, *, must_change_password: bool = False) -> User:
    """Insert a user with a known password; returns the detached row."""
    session = SessionLocal()
    try:
        user = User(
            username=username,
            full_name=f"مستخدم {username}",
            role=role,
            password_hash=hash_password(TEST_PASSWORD),
            must_change_password=must_change_password,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)
        return user
    finally:
        session.close()


@pytest.fixture
def users() -> dict[str, User]:
    return {
        "admin": make_user("admin", "admin"),
        "editor": make_user("editor", "editor"),
        "viewer": make_user("viewer", "viewer"),
    }


@pytest.fixture
def sample_family(db) -> dict[str, int]:
    """Load ``sample_civil_registry.sql`` and return ``{sample_id: person_id}``.

    The shipped sample is parsed with the production parser, so the fixture
    doubles as a check that the sample file stays importable.
    """
    from scripts.seed import parse_sample_sql

    persons, marriages = parse_sample_sql(BACKEND_ROOT.parent / "sample_civil_registry.sql")
    assert len(persons) == 14, f"expected 14 sample people, parsed {len(persons)}"
    assert len(marriages) == 5, f"expected 5 sample marriages, parsed {len(marriages)}"

    from app.models.marriage import Marriage
    from app.models.person import Person
    from app.utils.arabic import normalize_name, parse_full_name

    id_map: dict[str, int] = {}
    rows: dict[int, Person] = {}
    for record in persons:
        parts = parse_full_name(record["full_name"])
        person = Person(
            national_id=record["national_id"],
            full_name=record["full_name"],
            full_name_normalized=normalize_name(record["full_name"]),
            first_name=parts["first_name"],
            father_name=parts["father_name"],
            grandfather_name=parts["grandfather_name"],
            family_name=parts["family_name"],
            gender=record["gender"],
            birth_date=record["birth_date"],
            death_date=record["death_date"],
            birth_place=record["birth_place"],
        )
        db.add(person)
        db.flush()
        rows[record["id"]] = person
        id_map[str(record["id"])] = person.id

    for record in persons:
        person = rows[record["id"]]
        if record["father_id"]:
            person.father_id = rows[record["father_id"]].id
        if record["mother_id"]:
            person.mother_id = rows[record["mother_id"]].id

    for record in marriages:
        husband = rows[record["husband_id"]]
        # An ended marriage is widowed when the husband has died.
        status = "married"
        if record["end_date"] is not None:
            status = "widowed" if husband.death_date is not None else "divorced"
        db.add(
            Marriage(
                husband_id=husband.id,
                wife_id=rows[record["wife_id"]].id,
                start_date=record["start_date"],
                end_date=record["end_date"],
                status=status,
            )
        )

    db.commit()
    return id_map


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth(client: TestClient, users: dict[str, User]):
    """Return a helper that logs a role in and yields its auth header."""

    def _login(role: str) -> dict[str, str]:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": users[role].username, "password": TEST_PASSWORD},
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _login
