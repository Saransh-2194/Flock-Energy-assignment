# Flock Meter API

A read-only API facade over the legacy Urja Meter Ops portal. This is a **starter implementation**, not yet a verified production integration: the route mapping reflects the investigation so far, while login details and upstream response schemas still need verification.

## Architecture

```text
API consumer -> FastAPI routes -> PortalClient (httpx session) -> Urja Meter Ops
```

## Project structure

```text
.
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── main.py
│   └── portal_client.py
├── tests/
├── .env.example
├── .gitignore
├── openapi.json
├── PROTOCOL.md
├── REFLECTION.md
└── requirements.txt
```

## Setup

Python 3.11+ recommended.

### 1. Create a virtual environment

Windows PowerShell:
```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

macOS/Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure credentials

Copy `.env.example` to `.env`, then verify the login path and field names against the portal's normal login request in DevTools. Set your own authorized credentials in `.env`.

PowerShell: `Copy-Item .env.example .env`
macOS/Linux: `cp .env.example .env`

**Never commit `.env`, credentials, cookies, tokens, or signing-secret values.** The client deliberately does not call `/portal/keys` or use `signingSecret`; establish whether it is actually required before implementing that flow.

### 4. Run the API

```bash
uvicorn app.main:app --reload
```

- Base URL: `http://127.0.0.1:8000`
- Interactive documentation: `http://127.0.0.1:8000/docs`
- Runtime-generated OpenAPI: `http://127.0.0.1:8000/openapi.json`

### 5. Example requests

```bash
curl http://127.0.0.1:8000/api/v1/health
curl "http://127.0.0.1:8000/api/v1/meters?q=J100000&page=1"
curl http://127.0.0.1:8000/api/v1/meters/J100000/geo
curl http://127.0.0.1:8000/api/v1/meters/J100000/energy
curl "http://127.0.0.1:8000/api/v1/transformers?page=1"
curl "http://127.0.0.1:8000/api/v1/export/meters?page=1"
```

The health endpoint checks only that the API process is running, not upstream connectivity.

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/health` | Process health |
| GET | `/api/v1/meters?q=&page=1` | Meter search |
| GET | `/api/v1/meters/{meter_id}/geo` | Geographic/network information |
| GET | `/api/v1/meters/{meter_id}/energy` | Energy/consumption information |
| GET | `/api/v1/transformers?page=1` | Transformer listing |
| GET | `/api/v1/export/meters?page=1` | Bulk export route |

Responses are currently passed through from upstream JSON because exact schemas have not yet been captured. Before submission, inspect redacted examples and define stable response models rather than guessing field names.

## Design decisions and trade-offs

- **FastAPI + httpx:** rapid implementation, async HTTP, validation, and generated API documentation. Express is a reasonable alternative for a JavaScript-focused team.
- **Direct HTTP before browser automation:** the observed routes appear directly requestable. Browser automation is a fallback if the normal session flow cannot be reproduced, at the cost of a browser runtime and more brittle UI coupling.
- **Bulk export as a candidate primary source:** `page=1` was observed to return all meter data and a total record count. Page 2 behavior is unknown, so the code does not assume standard pagination.
- **No database or cache initially:** reduces operational complexity while dataset size, query patterns, and freshness requirements are unknown. A local index/cache can be added after measuring needs.
- **Read-only API:** matches the assignment and reduces risk.
- **Secrets via environment:** no credentials or signing secrets in source control.
- **Pass-through JSON initially:** preserves upstream fields but is not yet a stable normalized contract.
- **Upstream failures become 502:** clients receive a gateway error rather than an upstream traceback. Retry policy and detailed session-expiry handling remain future work.

## Known limitations / intentionally skipped

- Login path and field names in `.env.example` are provisional and must be checked.
- Login success detection is basic and may need adaptation to actual redirects/session behavior.
- Response schemas for all routes are not yet documented.
- Export pagination semantics are unverified.
- `/portal/keys` signing-secret purpose is unresolved and not used.
- No retries, caching, persistent storage, rate limiting, metrics, or frontend.
- Automated test coverage is not yet implemented.

## Validation checklist

1. Verify login method, path, form fields, redirects, cookies, and session expiry.
2. Compare each API response with the portal's corresponding response.
3. Compare export page 1 and page 2 by record IDs and counts.
4. Add tests for success, upstream timeout, expired session, invalid input, and unexpected content types.
5. Replace pass-through responses with explicit schemas where justified.
6. Confirm generated OpenAPI matches the implementation.
7. Inspect Git history and working tree to ensure no secrets are committed.

## Supporting documents

- Protocol investigation: [`PROTOCOL.md`](PROTOCOL.md)
- Reflection draft: [`REFLECTION.md`](REFLECTION.md)
- OpenAPI snapshot: [`openapi.json`](openapi.json)

Update the reflection after running and testing the service. Do not claim tests or findings that have not actually occurred.
