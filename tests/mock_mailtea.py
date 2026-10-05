"""A tiny stand-in for the Mailtea API.

Lets this example's tests run with no credentials and no network. Every request
is recorded on the server object, which is what the assertions read.

    with mock_mailtea() as server:
        client = Mailtea("mt_pat_test", base_url=server.url)
        ...
        assert server.last["path"] == "/v1/emails"
"""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import urlparse

EMAIL_ID = "txemail_00000000000000000000000000000000"


class _Handler(BaseHTTPRequestHandler):
    # Silence the default stderr access log; test output stays readable.
    def log_message(self, *args: Any) -> None:  # noqa: D102
        pass

    def _read(self) -> Any:
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        try:
            return json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return raw

    def _send(self, status: int, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle(self, method: str) -> None:
        path = urlparse(self.path).path
        body = self._read()
        self.server.requests.append(  # type: ignore[attr-defined]
            {
                "method": method,
                "path": path,
                "authorization": self.headers.get("authorization"),
                "body": body,
            }
        )

        # Auth first, like the real API — an example that forgets the key must
        # fail its test rather than appear to send.
        if not (self.headers.get("authorization") or "").startswith("Bearer "):
            return self._send(401, {"error": "Unauthorized"})

        route = f"{method} {path}"
        if route == "POST /v1/emails":
            return self._send(200, {"id": EMAIL_ID})
        if route == "POST /v1/emails/batch":
            items = body if isinstance(body, list) else []
            return self._send(
                200,
                {"data": [{"id": f"txemail_{i:032d}"} for i, _ in enumerate(items)]},
            )
        if method == "GET" and path.startswith("/v1/emails/") and path.count("/") == 3:
            return self._send(
                200,
                {
                    "object": "email",
                    "id": path.rsplit("/", 1)[-1],
                    "last_event": "delivered",
                    "subject": "Mock email",
                    "created_at": "2026-01-01T00:00:00.000Z",
                },
            )
        if route == "GET /v1/emails":
            return self._send(
                200,
                {"object": "list", "data": [], "total": 0, "limit": 20, "offset": 0, "has_more": False},
            )
        if method == "PATCH" and path.startswith("/v1/emails/"):
            return self._send(200, {"object": "email", "id": path.rsplit("/", 1)[-1]})
        # Cancel is POST /v1/emails/:id/cancel. There is no DELETE on emails —
        # the real API does not define one.
        if method == "POST" and path.startswith("/v1/emails/") and path.endswith("/cancel"):
            return self._send(200, {"object": "email", "id": path.split("/")[3]})
        if route == "POST /v1/contacts":
            return self._send(200, {"id": "con_00000000000000000000000000000000"})
        if route == "GET /v1/contacts":
            return self._send(
                200,
                {"object": "list", "data": [], "total": 0, "limit": 20, "offset": 0, "has_more": False},
            )
        if route == "POST /v1/topics":
            name = body.get("name") if isinstance(body, dict) else "Topic"
            return self._send(200, {"id": "top_00000000000000000000000000000000", "name": name})
        if route == "POST /v1/posts":
            return self._send(200, {"id": "post_00000000000000000000000000000000"})
        if method == "POST" and path.startswith("/v1/posts/") and path.endswith("/send"):
            return self._send(200, {"id": path.split("/")[3], "status": "sending"})

        return self._send(404, {"error": "Not Found", "path": path})

    def do_GET(self) -> None:  # noqa: N802
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._handle("POST")

    def do_PATCH(self) -> None:  # noqa: N802
        self._handle("PATCH")

    def do_DELETE(self) -> None:  # noqa: N802
        self._handle("DELETE")


class MockMailtea:
    def __init__(self, server: ThreadingHTTPServer) -> None:
        self._server = server
        host, port = server.server_address[:2]
        self.url = f"http://{host}:{port}"

    @property
    def requests(self) -> List[Dict[str, Any]]:
        return self._server.requests  # type: ignore[attr-defined]

    @property
    def last(self) -> Optional[Dict[str, Any]]:
        return self.requests[-1] if self.requests else None


@contextmanager
def mock_mailtea() -> Iterator[MockMailtea]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.requests = []  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield MockMailtea(server)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
