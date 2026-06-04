import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.deps import get_current_user
from app.routers.tags import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)

    async def _user():
        return SimpleNamespace(id=uuid.uuid4())

    app.dependency_overrides[get_current_user] = _user
    return TestClient(app)


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/api/tags", {"name": "legacy"}),
        ("put", f"/api/tags/{uuid.uuid4()}", {"name": "legacy"}),
        ("delete", f"/api/tags/{uuid.uuid4()}", None),
        ("post", f"/api/tags/{uuid.uuid4()}/holdings/{uuid.uuid4()}", None),
        ("delete", f"/api/tags/{uuid.uuid4()}/holdings/{uuid.uuid4()}", None),
        ("post", f"/api/tags/{uuid.uuid4()}/share", {"requires_auth": False}),
        ("delete", f"/api/tags/{uuid.uuid4()}/share", None),
    ],
)
def test_legacy_tag_mutations_are_disabled(client, method, path, body):
    response = client.request(method.upper(), path, json=body)

    assert response.status_code == 410
    assert response.json()["detail"] == "Legacy tag writes are disabled; use group management"
