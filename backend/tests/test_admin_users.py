import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.routers.admin import router
from app.routers.deps import get_admin_user


class _Result:
    def __init__(self, *, one=None, count=None):
        self._one = one
        self._count = count

    def scalar_one_or_none(self):
        return self._one

    def scalar_one(self):
        return self._count


class _QueuedSession:
    def __init__(self):
        self.results = []

    def queue(self, *results):
        self.results.extend(results)

    async def execute(self, _query):
        assert self.results, "unexpected database query"
        return self.results.pop(0)


def _user(*, is_admin=False, is_active=True):
    return SimpleNamespace(
        id=uuid.uuid4(),
        email="user@example.com",
        is_admin=is_admin,
        is_active=is_active,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def db():
    return _QueuedSession()


@pytest.fixture
def client(db):
    app = FastAPI()
    app.include_router(router)

    async def _db():
        yield db

    async def _admin():
        return _user(is_admin=True)

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_admin_user] = _admin
    return TestClient(app)


def test_demoting_last_admin_is_rejected(client, db):
    target = _user(is_admin=True)
    db.queue(_Result(one=target), _Result(count=0))

    response = client.patch(f"/api/admin/users/{target.id}", json={"is_admin": False})

    assert response.status_code == 409
    assert target.is_admin is True


def test_deactivating_last_admin_is_rejected(client, db):
    target = _user(is_admin=True)
    db.queue(_Result(one=target), _Result(count=0))

    response = client.patch(f"/api/admin/users/{target.id}", json={"is_active": False})

    assert response.status_code == 409
    assert target.is_active is True


def test_demoting_admin_with_remaining_admin_is_allowed(client, db):
    target = _user(is_admin=True)
    db.queue(_Result(one=target), _Result(count=1))

    response = client.patch(f"/api/admin/users/{target.id}", json={"is_admin": False})

    assert response.status_code == 200
    assert target.is_admin is False


def test_patching_regular_user_skips_admin_count(client, db):
    target = _user(is_admin=False)
    db.queue(_Result(one=target))

    response = client.patch(f"/api/admin/users/{target.id}", json={"is_active": False})

    assert response.status_code == 200
    assert target.is_active is False
