from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware import OriginValidationMiddleware


def _client(allowed_origins: list[str] | None = None) -> TestClient:
    app = FastAPI()
    app.add_middleware(
        OriginValidationMiddleware,
        allowed_origins=allowed_origins or ["http://localhost:3000"],
    )

    @app.post("/mutate")
    async def mutate():
        return {"ok": True}

    @app.get("/read")
    async def read():
        return {"ok": True}

    return TestClient(app)


def test_rejects_mutation_with_unknown_origin():
    response = _client().post("/mutate", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403


def test_allows_mutation_with_allowed_origin():
    response = _client().post("/mutate", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200


def test_allows_get_with_unknown_origin():
    response = _client().get("/read", headers={"Origin": "https://evil.example"})
    assert response.status_code == 200


def test_allows_mutation_without_browser_headers():
    response = _client().post("/mutate")
    assert response.status_code == 200


def test_rejects_mutation_with_unknown_referer_when_origin_missing():
    response = _client().post("/mutate", headers={"Referer": "https://evil.example/page"})
    assert response.status_code == 403


def test_allows_mutation_with_allowed_referer_when_origin_missing():
    response = _client().post(
        "/mutate",
        headers={"Referer": "http://localhost:3000/dashboard"},
    )
    assert response.status_code == 200
