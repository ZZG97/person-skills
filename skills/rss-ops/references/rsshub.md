# RSSHub operations

Local endpoint: `@@RSSHUB_BASE_URL@@`

Deployment directory: `@@RSSHUB_DEPLOY_DIR@@`

## Diagnose in order

1. Request the exact route on the host with `curl --fail --silent --show-error`.
2. Confirm the response is RSS/Atom XML, not a login, CAPTCHA, or verification
   page.
3. Inspect the deployment's compose/config files to identify the relevant
   environment variable without printing secret values.
4. Inspect only the relevant container logs and route errors.
5. If authentication is stale, renew it with an isolated profile through
   `use-agent-chrome`, then update the local runtime configuration.
6. Restart only the RSSHub deployment if required, then request the route again.

## Boundaries

- Do not expose RSSHub, FreshRSS data, browser CDP, or workspace directories to
  the public Internet for debugging.
- Do not commit `.env`, cookies, tokens, copied browser profiles, or generated
  feed inventories.
- A source returning HTTP 200 can still be invalid. Verify the content type and
  first feed elements.
- Treat a route implementation change as source code work: inspect the current
  RSSHub version and route before editing or patching.
