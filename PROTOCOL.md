# Urja Meter Ops — Protocol Notes

## Evidence status

This document records observations from normal, authorized portal use. It separates observed behavior from unresolved assumptions. Exact response schemas, login details, and export pagination semantics remain to be verified.

## Observed routes

| Purpose | Route | Observation |
|---|---|---|
| Meter search | `GET /portal/meters/search?q=&page=1` | Meter list/search; paginated. |
| Meter geo/network data | `GET /portal/meters/{meter_id}/geo` | Per-meter route; exact response fields need inspection. |
| Meter energy | `GET /portal/meters/{meter_id}/energy` | Per-meter consumption-related route; units/time range need inspection. |
| Transformer list | `GET /portal/dts?page=1` | Transformer listing; pagination details need confirmation. |
| Key endpoint | `GET /portal/keys` | JSON includes `data.signingSecret`; the actual value is intentionally not recorded. |
| Export | `GET /portal/export?page=1` | In the observed request, returned all meter data and a total record count. |

## Authentication

The portal requires login. During investigation, the login flow was described as exposing the email and password in the login URL. Verify whether the credentials are actually in the URL or in a POST request body: these have different security implications. Login method/path, field names, redirects, cookies, and session-expiry behavior still need to be recorded.

If credentials genuinely appear in a URL, report it to the portal owner. URLs can be retained in browser history and logs. The API should use the normal authorized login flow, not bypass authentication.

## Export and signing secret

`/portal/keys` returns JSON with a `data.signingSecret` field. The secret value is deliberately excluded from this document and must not be committed to source control.

The observed `/portal/export?page=1` request returned all meter data and a total record count. The request was reported to have only the `page` query parameter.

Unresolved:
- Does `page=2` return the same dataset, a subset, or an error?
- Does export depend on session cookies, a signature, or another request context?
- What does `signingSecret` do, and is `/portal/keys` needed in the normal export workflow?
- What is the complete export schema?

Do not infer or implement a signing scheme before establishing the normal request flow. Do not store real secret values in source code or documentation.

## Search behavior

The portal search bar was observed to have no debounce. Successive keystrokes may trigger separate requests. The actual traffic and performance impact have not been benchmarked.

Debouncing belongs in the client UI; the API should handle explicit requests without adding artificial debounce delays. If a UI is built, use client-side debounce and stale-response protection.

## Pagination

Meter search and transformer listing accept a `page` parameter. Export's semantics are unverified: one `page=1` request returned all data. The starter preserves the parameter without assuming that the export is truly paginated.

## Current client strategy

The starter uses a persistent `httpx.AsyncClient` for session cookies and maps the observed routes to API methods. Login configuration is environment-driven because the actual login details are not yet confirmed. It does not disable TLS verification and does not use the `signingSecret`.

## Next investigation steps

1. Record the login method/path, field names, redirect chain, cookies, and session behavior.
2. Capture redacted sample responses for search, geo, energy, transformers, and export.
3. Compare export pages 1 and 2 using record IDs and counts.
4. Establish whether `/portal/keys` is required in the normal export workflow without attempting to forge or bypass security.
5. Record representative error responses and session expiry behavior.
