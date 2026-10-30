# Flock Meter API

A read-only REST API built with FastAPI to make data from the legacy Urja Meter Ops portal easier to access programmatically.

The portal does not provide a documented public API, so I explored its network requests and built a separate API that communicates with the portal's existing endpoints

## How it works

The API uses an HTTP client to log in to the portal and maintain the authenticated session. Once logged in, it makes requests to the portal's endpoints and exposes the returned data through cleaner API routes.

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

### 1. Clone the repository

Windows PowerShell:
```powershell
git clone https://github.com/Saransh-2194/Flock-Energy-assignment
cd flock-energy-api
```
### 2. Create a virtual environment

Windows PowerShell:
```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure credentials

Copy `.env.example` to `.env`, then verify the login path and field names against the portal's normal login request in DevTools. Set your own authorized credentials in `.env`.

PowerShell: `Copy-Item .env.example .env`
macOS/Linux: `cp .env.example .env`


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


## Authentication

The portal requires login before its data endpoints can be accessed. During my investigation, I found that the login request sends the email and password in its request payload. After successful login, the portal uses a session cookie for subsequent requests.

The API client is designed to perform this login and reuse the authenticated session when requesting portal data. Credentials are supplied through environment variables rather than being hardcoded.

More details about the portal's requests and authentication are available in [`PROTOCOL.md`](PROTOCOL.md).


## Design decisions and trade-offs

- **FastAPI + httpx:** rapid implementation, async HTTP, validation, and generated API documentation. Express is a reasonable alternative for a JavaScript-focused team.
- **Direct HTTP before browser automation:** the observed routes appear directly requestable. Browser automation is a fallback if the normal session flow cannot be reproduced, at the cost of a browser runtime and more brittle UI coupling.
- **No database or cache initially:** reduces operational complexity while dataset size, query patterns, and freshness requirements are unknown. A local index/cache can be added after measuring needs.
- **Read-only API:** matches the assignment and reduces risk.
- **Secrets via environment:** no credentials or signing secrets in source control.
- **Pass-through JSON initially:** preserves upstream fields but is not yet a stable normalized contract.
- **Upstream failures become 502:** clients receive a gateway error rather than an upstream traceback. Retry policy and detailed session-expiry handling remain future work.

## Known limitations / intentionally skipped

- Login success detection is basic and may need adaptation to actual redirects/session behavior.
- Response schemas for all routes are not yet documented.
- `/portal/keys` signing-secret purpose is unresolved and not used.
- No retries, caching, persistent storage, rate limiting, metrics, or frontend.
- Improve handling of unexpected upstream responses.

## Supporting documents

- Protocol investigation: [`PROTOCOL.md`](PROTOCOL.md)
- Reflection draft: [`REFLECTION.md`](REFLECTION.md)
- OpenAPI snapshot: [`openapi.json`](openapi.json)
