# Reflection

## What assumptions did you make?

I assumed the portal could be integrated through authenticated HTTP requests because the browser's Network panel showed the routes used to load its data. I also assumed the export endpoint could be useful for retrieving meter data in bulk. The first export request returned meter data along with a total record count, but I have not confirmed what the secretSigning key does.

## Which part was most difficult, and how did you get unstuck?

The main challenge was separating observed behavior from assumptions about the portal's internals. Inspecting the browser Network panel revealed routes for meter search, geographic information, energy data, transformer listings, and export. The next step is to capture redacted response samples and verify login and export behavior before finalizing the integration.

## If you had another day, what would you improve?

I would verify authentication and session expiry, compare export pages, and define explicit response models. Based on measured dataset size and freshness requirements, I would evaluate a local index and caching. I would also add structured logging without recording credentials or tokens.

## What mistake did you make while solving this?

One thing I could have done better was trying to build the API before fully understanding the portal's request and authentication flow. This meant some parts of the integration were based on assumptions and needed revisiting. Inspecting the Network panel helped me understand the actual requests, and I used those findings to guide the implementation. For example i spent a good chunk of my time debugging why my the upstream was throwing login error 403 and finally figured how the authentication works on the site.

## If you were reviewing your own submission, what would you criticise?

The starter passes upstream JSON through instead of enforcing a stable normalized schema. Login configuration and success detection must be validated against the actual portal. Export pagination and the signing-secret purpose remain unresolved, and the test coverage can be improved and more checks for unexpected upstream responses can be added. These are known limitations, not claims of production readiness.
