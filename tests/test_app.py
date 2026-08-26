"""Tests for the send/status routes, run against the bundled mock Mailtea API.

No API key, no network: the mock records every request it receives and the
assertions read those recordings back.
"""

from __future__ import annotations

import socket

import pytest
from fastapi.testclient import TestClient
from mailtea import Mailtea
from mock_mailtea import mock_mailtea

from app.main import app, get_mailtea, get_sender

SENDER = "Mailtea Examples <examples@yourdomain.com>"


def closed_port() -> int:
    """A port with nothing listening on it: bound to claim a free one, then
    released. Connecting to it is refused, with no network and no waiting."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
def mailtea_api():
    """A running mock API, with the app's client pointed at it."""
    with mock_mailtea() as server:
        app.dependency_overrides[get_mailtea] = lambda: Mailtea("mt_pat_test", base_url=server.url)
        app.dependency_overrides[get_sender] = lambda: SENDER
        try:
            yield server
        finally:
            app.dependency_overrides.clear()


@pytest.fixture
def client(mailtea_api):
    with TestClient(app) as test_client:
        yield test_client


def test_send_forwards_the_email_to_mailtea(client, mailtea_api):
    response = client.post(
        "/send",
        json={
            "to": "reader@mailtea.example",
            "subject": "Hello from FastAPI",
            "html": "<p>Sent with Mailtea.</p>",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"id": "txemail_00000000000000000000000000000000"}

    sent = mailtea_api.last
    assert sent["method"] == "POST"
    assert sent["path"] == "/v1/emails"
    assert sent["authorization"].startswith("Bearer ")
    assert sent["body"] == {
        "from": SENDER,
        "to": "reader@mailtea.example",
        "subject": "Hello from FastAPI",
        "html": "<p>Sent with Mailtea.</p>",
    }


def test_send_accepts_several_recipients(client, mailtea_api):
    response = client.post(
        "/send",
        json={
            "to": ["a@mailtea.example", "b@mailtea.example"],
            "subject": "Hello",
            "text": "Sent with Mailtea.",
        },
    )

    assert response.status_code == 200
    assert mailtea_api.last["body"]["to"] == ["a@mailtea.example", "b@mailtea.example"]
    # An omitted html is left out of the payload, not sent as null.
    assert "html" not in mailtea_api.last["body"]


@pytest.mark.parametrize(
    "body",
    [
        {"to": "not-an-address", "subject": "Hi", "text": "Hi"},
        {"to": "reader@mailtea.example", "subject": "Hi"},  # no html and no text
        {"to": "reader@mailtea.example", "subject": "", "text": "Hi"},
    ],
)
def test_invalid_requests_are_rejected_before_any_send(client, mailtea_api, body):
    assert client.post("/send", json=body).status_code == 422
    assert mailtea_api.requests == []


def test_get_email_reports_delivery_status(client, mailtea_api):
    email_id = "txemail_00000000000000000000000000000000"

    response = client.get(f"/emails/{email_id}")

    assert response.status_code == 200
    assert response.json()["id"] == email_id
    assert response.json()["status"] == "delivered"
    assert mailtea_api.last["path"] == f"/v1/emails/{email_id}"
    assert mailtea_api.last["authorization"].startswith("Bearer ")


def test_mailtea_error_keeps_its_status_code(mailtea_api):
    # Point the client one path deeper than the mock serves, so Mailtea answers
    # 404 — the app must pass that through instead of turning it into a 500.
    app.dependency_overrides[get_mailtea] = lambda: Mailtea(
        "mt_pat_test", base_url=f"{mailtea_api.url}/wrong-base"
    )

    with TestClient(app) as test_client:
        response = test_client.post(
            "/send",
            json={"to": "reader@mailtea.example", "subject": "Hi", "text": "Hi"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Not Found"


def test_unreachable_mailtea_is_a_502(mailtea_api):
    # Nothing answers on this port, so the request never reaches Mailtea. The
    # SDK's transport raises the socket error rather than a MailteaError, and
    # the route has to report that as a bad gateway — the failure is ours, not
    # the caller's, and it is not a 500 with a traceback.
    app.dependency_overrides[get_mailtea] = lambda: Mailtea(
        "mt_pat_test", base_url=f"http://127.0.0.1:{closed_port()}"
    )

    with TestClient(app) as test_client:
        response = test_client.post(
            "/send",
            json={"to": "reader@mailtea.example", "subject": "Hi", "text": "Hi"},
        )

    assert response.status_code == 502
    assert "Could not reach Mailtea" in response.json()["detail"]
    assert mailtea_api.requests == []
