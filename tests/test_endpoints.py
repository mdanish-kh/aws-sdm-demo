from fastapi.testclient import TestClient

import app.main as main


EXTERNAL_ID = "c4ca4238a0b923820dcc509a6f75849b"


class FakeConnection:
    async def fetchrow(self, query: str, external_id: str):
        assert external_id == EXTERNAL_ID
        return {"id": 1, "external_id": EXTERNAL_ID}


class FakeAcquire:
    async def __aenter__(self):
        return FakeConnection()

    async def __aexit__(self, exc_type, exc_value, traceback):
        return None


class FakePool:
    def acquire(self):
        return FakeAcquire()


async def fake_get_pool(request):
    return FakePool()


def test_root():
    with TestClient(main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_hello():
    with TestClient(main.app) as client:
        response = client.get("/endpoint1")

    assert response.status_code == 200
    assert response.json() == {"message": "Hello, World!"}


def test_large_payload_is_exactly_two_mib():
    with TestClient(main.app) as client:
        response = client.get("/endpoint2")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert len(response.content) == 2 * 1024 * 1024


def test_table_scan(monkeypatch):
    monkeypatch.setattr(main, "get_pool", fake_get_pool)
    with TestClient(main.app) as client:
        response = client.get(f"/endpoint3/{EXTERNAL_ID}")

    assert response.status_code == 200
    assert response.json()["id"] == 1


def test_indexed_lookup(monkeypatch):
    monkeypatch.setattr(main, "get_pool", fake_get_pool)
    with TestClient(main.app) as client:
        response = client.get(f"/endpoint4/{EXTERNAL_ID}")

    assert response.status_code == 200
    assert response.json()["id"] == 1


def test_old_routes_are_not_available():
    with TestClient(main.app) as client:
        responses = [
            client.get("/hello"),
            client.get("/large-payload"),
            client.get(f"/db/scan/{EXTERNAL_ID}"),
            client.get(f"/db/indexed/{EXTERNAL_ID}"),
        ]

    assert all(response.status_code == 404 for response in responses)
