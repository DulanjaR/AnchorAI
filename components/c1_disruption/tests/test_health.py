from fastapi.testclient import TestClient

from components.c1_disruption.app.main import app


def test_health():
    r = TestClient(app).get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "component": "c1_disruption"}
