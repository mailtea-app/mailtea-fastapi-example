# Mailtea + FastAPI Example

This example shows how to use [Mailtea](https://mailtea.app) with FastAPI to
expose a small JSON email service: `POST /send` validates a request and sends
it, and `GET /emails/{id}` reports what happened to the message afterwards.

## Prerequisites

To get the most out of this guide, you'll need to:

- [Create an API key](https://studio.mailtea.app/api-keys)
- [Verify your domain](https://docs.mailtea.app/docs/documentation/domains)

## Instructions

1. Install dependencies:
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and add your API key:
   ```bash
   cp .env.example .env
   ```
   Set `MAILTEA_FROM` to an address on a domain you have verified.
3. Run it:
   ```bash
   uvicorn app.main:app --reload
   ```

Send an email:

```bash
curl -X POST http://127.0.0.1:8000/send \
  -H 'content-type: application/json' \
  -d '{"to":"reader@theirdomain.com","subject":"Hello","html":"<p>Sent with Mailtea.</p>"}'
```

```json
{ "id": "txemail_..." }
```

Then check what became of it:

```bash
curl http://127.0.0.1:8000/emails/txemail_...
```

```json
{ "id": "txemail_...", "status": "delivered", "subject": "Hello", "created_at": "..." }
```

The interactive docs FastAPI generates from these routes are at
http://127.0.0.1:8000/docs.

## What this example covers

- Sending with the Python SDK (`mailtea.emails.send`) from a FastAPI route
- Building the client in a `Depends` provider, so no credentials are needed to
  import the app and the tests can swap in a client pointed at a mock
- Validating the request with Pydantic — including "html, text, or both" —
  so a malformed payload is a 422 before anything is sent
- Keeping the verified From address in server config instead of the request
  body, so callers cannot send as anyone on your domain
- Looking up delivery status with `mailtea.emails.get`
- Mapping `MailteaError` onto the caller's response: Mailtea's own status code
  is passed through (a rejected address stays a 422, a rate limit stays a 429),
  and a Mailtea the service could not reach at all becomes a 502
- Pointing the SDK at a local or self-hosted Mailtea with `MAILTEA_API_BASE_URL`

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests run against a bundled mock Mailtea server, so they need no API key
and make no network calls.

## Learn more

- [Documentation](https://docs.mailtea.app)
- [API reference](https://docs.mailtea.app/docs/api-reference)
- [Node.js SDK](https://github.com/mailtea-app/mailtea-node) ·
  [Python SDK](https://github.com/mailtea-app/mailtea-python) ·
  [MCP server](https://github.com/mailtea-app/mailtea-mcp)
