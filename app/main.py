"""A FastAPI service that sends email through Mailtea.

POST /send validates a request with Pydantic and hands it to the Mailtea API.
GET /emails/{id} reports what happened to a message after it left.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Annotated, Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from mailtea import Mailtea, MailteaError
from pydantic import BaseModel, EmailStr, Field, model_validator

load_dotenv()

app = FastAPI(title="Mailtea + FastAPI Example")


@lru_cache
def get_mailtea() -> Mailtea:
    """One client for the process, built on first use so that importing this
    module needs no credentials — tests override this dependency instead."""
    # The client reads the optional MAILTEA_API_BASE_URL override itself.
    # Unset, it uses https://api.mailtea.app.
    return Mailtea(os.environ["MAILTEA_API_KEY"])


def get_sender() -> str:
    """The verified From address is server configuration, not something the
    caller gets to pick — otherwise anyone with access to this endpoint could
    send as anyone on your domain."""
    address = os.getenv("MAILTEA_FROM")
    if not address:
        raise HTTPException(status_code=500, detail="MAILTEA_FROM is not configured.")
    return address


MailteaClient = Annotated[Mailtea, Depends(get_mailtea)]
Sender = Annotated[str, Depends(get_sender)]


class SendRequest(BaseModel):
    """What callers of POST /send may set. Anything not listed here (the From
    address, tags, headers) stays under this service's control."""

    to: EmailStr | list[EmailStr]
    subject: str = Field(min_length=1, max_length=200)
    html: str | None = None
    text: str | None = None

    @model_validator(mode="after")
    def require_content(self) -> SendRequest:
        if not self.html and not self.text:
            raise ValueError("Provide html, text, or both.")
        return self


class SendResponse(BaseModel):
    id: str


class EmailStatus(BaseModel):
    id: str
    # The SDK exposes the raw `last_event` wire field under this friendlier name.
    status: str | None = None
    subject: str | None = None
    created_at: str | None = None


def as_http_error(error: MailteaError | OSError) -> HTTPException:
    """Keep Mailtea's own status instead of collapsing every failure into a
    500: a rejected address stays a 422 for our caller, a rate limit stays a
    429. Anything that never reached Mailtea becomes a 502.

    That second case arrives in two shapes. A client-side failure raises
    MailteaError with status 0, but a request that never got an answer at all
    — DNS, a refused connection, TLS, a timeout — is the socket error itself:
    the SDK's standard-library transport lets it through unchanged, so a route
    that catches only MailteaError turns an unreachable Mailtea into a 500 with
    a traceback.
    """
    if isinstance(error, OSError):
        return HTTPException(status_code=502, detail=f"Could not reach Mailtea: {error}")
    status = error.status if 400 <= error.status <= 599 else 502
    return HTTPException(status_code=status, detail=error.message)


# Plain `def`, not `async def`: the SDK's HTTP call is blocking, so FastAPI
# runs these in its threadpool rather than stalling the event loop.
@app.post("/send", response_model=SendResponse)
def send_email(body: SendRequest, mailtea: MailteaClient, sender: Sender) -> SendResponse:
    payload: dict[str, Any] = {
        "from": sender,
        # exclude_none keeps an omitted html/text out of the payload entirely
        # rather than sending an explicit null.
        **body.model_dump(exclude_none=True),
    }
    try:
        sent = mailtea.emails.send(payload)
    except (MailteaError, OSError) as error:
        raise as_http_error(error) from error
    return SendResponse(id=sent["id"])


@app.get("/emails/{email_id}", response_model=EmailStatus)
def get_email(email_id: str, mailtea: MailteaClient) -> EmailStatus:
    try:
        email = mailtea.emails.get(email_id)
    except (MailteaError, OSError) as error:
        raise as_http_error(error) from error
    return EmailStatus(**email)
