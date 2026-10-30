# How the Urja Ops portal works

I explored the portal by logging in through the browser and checking the requests it made in the Network tab. The portal is a web interface over a set of JSON endpoints. The API in this project uses those same read-only endpoints instead of scraping the pages.

## What data is available

- **Meters:** the portal can search and list meters through `/portal/meters/search`, using `q` for the search text and `page` for the page number.
- **Meter location/network details:** `/portal/meters/{meter_id}/geo` returns the geo-related data for an individual meter.
- **Meter energy data:** `/portal/meters/{meter_id}/energy` returns energy-related data for an individual meter.
- **Transformers:** `/portal/dts` provides the transformer/DT listing and accepts a page number.
- **Meter export:** `/portal/export?page=1` returned meter data along with a total record count when I inspected it.

The portal also has a `/portal/keys` endpoint. Its response includes a `signingSecret` field. I did not use or copy this value because its purpose was not clear from the requests I inspected.

## How I accessed the data

After opening the portal and signing in, I used the browser's Developer Tools **Network** tab to inspect the requests made while using the meter search, meter details, transformer listing and export features. This revealed the endpoint paths and query parameters listed above. The project calls these endpoints directly and passes the JSON responses back through its own FastAPI routes.

One other things I noticed was the search functionality, it sends an api request after every word or within a very small time. this increase the api calls and puts unnecessary pressure on the DB and can be easily solved by Debouncing

## Login and access

The portal requires a login. The browser login flow uses the fields `email` and `password`. After login, the browser receives a session cookie named `__Secure-better-auth.session_token`; requests to protected endpoints use that session to identify the logged-in user.

During my investigation, a direct login request was rejected with `403` unless it included the browser's `Origin` and `Referer` headers. This suggests the portal checks the context of the login request as well as the credentials. The project uses a persistent HTTP client so it can retain session cookies, but its live login flow still needs to be tested against the portal.

## What is not confirmed yet

I have not fully confirmed the exact response fields for every endpoint. The purpose of the `signingSecret` field is also unknown.
