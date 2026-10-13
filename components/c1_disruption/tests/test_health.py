from fastapi.testclient import TestClient

from components.c1_disruption.app.main import app
from shared.config import settings


def test_health():
    r = TestClient(app).get("/health", headers={"X-API-Key": settings.api_key})
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "component": "c1_disruption"}
