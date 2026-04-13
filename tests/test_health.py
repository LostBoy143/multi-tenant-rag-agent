import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_check(monkeypatch):
    """Verify that the health check endpoint returns 200 OK."""
    async def healthy_dependency():
        return None

    monkeypatch.setattr("app.main._check_qdrant", healthy_dependency)
    monkeypatch.setattr("app.main._check_database", healthy_dependency)
    monkeypatch.setattr("app.main._check_redis", healthy_dependency)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "qdrant" in data
    assert "database" in data
    assert "redis" in data
