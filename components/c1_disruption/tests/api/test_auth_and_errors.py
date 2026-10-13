"""New with the port: the team API key (shared.auth), the API prefix setting and
the error shape for errors raised by FastAPI itself."""
import pytest
from fastapi.testclient import TestClient

from components.c1_disruption.app.main import create_app
from components.c1_disruption.tests.api.client import API_KEY_HEADERS, setup

ROUTES = [
    ("GET", "/health"),
    ("GET", "/api/me/settings"),
    ("GET", "/api/protected-blocks"),
    ("GET", "/api/tasks"),
    ("POST", "/api/disruptions"),
    ("GET", "/api/mvds/x"),
    ("GET", "/api/reviews/2026-10-07"),
]


@pytest.mark.parametrize(("method", "path"), ROUTES)
@pytest.mark.parametrize("key", [None, "wrong-key"])
def test_every_route_needs_the_team_api_key(method, path, key):
    headers = {"X-User-Id": "u1"} | ({"X-API-Key": key} if key else {})
    res = setup().client.request(method, path, headers=headers)
    assert res.status_code == 401
    assert res.json() == {"error": {"code": "INVALID_API_KEY", "message": "Invalid API key"}}


def test_the_api_key_is_checked_before_the_user():
    res = setup().client.get("/api/tasks")
    assert res.json()["error"]["code"] == "INVALID_API_KEY"


def test_health_with_the_api_key():
    res = setup().client.get("/health", headers=API_KEY_HEADERS)
    assert res.json() == {"status": "ok", "component": "c1_disruption"}


def test_the_api_prefix_is_one_setting():
    client = TestClient(create_app(api_prefix="/c1/api"))
    headers = {**API_KEY_HEADERS, "X-User-Id": "u1"}
    assert client.get("/c1/api/tasks", headers=headers).status_code == 200
    assert client.get("/api/tasks", headers=headers).status_code == 404


def test_wrong_method_uses_the_error_shape():
    res = setup().call("PUT", "/api/tasks")
    assert res.status_code == 405
    assert res.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


@pytest.mark.parametrize("body", [[1, 2], "text", 3])
def test_a_body_that_is_not_an_object_is_refused(body):
    res = setup().call("POST", "/api/tasks", body=body)
    assert res.status_code == 400
    assert res.json() == {"error": {"code": "INVALID_INPUT", "message": "Request body must be a JSON object"}}


def test_missing_body_is_refused():
    res = setup().call("POST", "/api/tasks")
    assert res.status_code == 400
    assert res.json()["error"]["message"] == "Request body must be a JSON object"


@pytest.mark.parametrize(
    ("over", "message"),
    [
        ({"estimatedHours": "2"}, "'estimatedHours' must be a positive number"),
        ({"estimatedHours": True}, "'estimatedHours' must be a positive number"),
        ({"delegable": "yes"}, "'delegable' must be true or false"),
        ({"title": "   "}, "'title' must be a non-empty string"),
        ({"plannedDate": "2026-02-30"}, "'plannedDate' must be a date YYYY-MM-DD"),
        ({"deadline": "2026-10-07T9:00"}, "'deadline' must be a date-time YYYY-MM-DDTHH:MM"),
    ],
)
def test_strict_types_like_the_node_api(over, message):
    # Pydantic would otherwise coerce "2" → 2 or "yes" → True.
    body = {"title": "A", "type": "Analog", "priority": "High", "estimatedHours": 2,
            "deadline": "2026-10-07T23:59", "plannedDate": "2026-10-07", **over}
    res = setup().call("POST", "/api/tasks", body=body)
    assert res.status_code == 400
    assert res.json()["error"]["message"] == message


def test_severity_accepts_a_whole_float_like_json_does():
    body = {"date": "2026-10-07", "type": "power_outage", "start": "09:00", "timeLostMinutes": 60.0,
            "severity": 2.0, "confirmed": True}
    res = setup().call("POST", "/api/disruptions", body=body)
    assert res.status_code == 201
    assert (res.json()["severity"], res.json()["timeLostMinutes"]) == (2, 60)


def test_nested_item_errors_name_the_field():
    ctx = setup(now="2026-10-07T18:00")
    res = ctx.call("POST", "/api/reviews/2026-10-07", body={"items": [{"taskId": "a", "outcome": "maybe"}]})
    assert res.status_code == 400
    assert res.json()["error"]["message"] == "'outcome' must be one of: done, partial, not_done"
    res = ctx.call("POST", "/api/reviews/2026-10-07", body={"items": ["x"]})
    assert res.json()["error"]["message"] == "Each item must be an object"
