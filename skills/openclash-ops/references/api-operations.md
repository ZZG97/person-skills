# Mihomo controller operations

The controller secret authorizes both inspection and mutation. There is no
separate read-only token, so workflow discipline is the access-control boundary.

## Read-oriented endpoints

| Endpoint | Purpose | Handling |
|---|---|---|
| `GET /version` | Authenticate and identify the running core | Safe first check |
| `GET /configs` | Runtime ports and global options | Select only relevant fields |
| `GET /proxies` | Groups, current selections, candidates, delay history | Avoid huge raw dumps |
| `GET /providers/proxies` | Provider freshness and node health | Do not print provider URLs |
| `GET /rules` | Ordered rule matchers and target groups | Filter around the domain/ruleset |
| `GET /connections` | Effective runtime chains and matched rule | Contains LAN metadata; report narrowly |
| `GET /proxies/:name/delay` | Test a node against a chosen URL and optional expected status | Causes outbound traffic and may update health history |

Use the bundled helper so the Bearer secret is delivered to curl through stdin,
not embedded in the shell command or repository.

## Selector mutation

`PUT /proxies/:group` with `{"name":"node"}` changes a Selector group. The
helper validates that the group is a Selector and the node is one of its
candidates, then requires `--yes`:

~~~bash
openclash-api.sh select --yes 'GROUP' 'NODE'
~~~

The running configuration commonly persists selector choices when
`profile.store-selected` is enabled, but verify current state after the change
and again after any later core reload when persistence matters.

## Operations intentionally not wrapped

The helper omits config reloads, provider updates, mode changes, connection
closure, cache manipulation, and restart operations. They have wider impact and
need case-specific evidence, rollback planning, and explicit authorization.

## HTTP interpretation

- `200`: successful query or delay result.
- `204`: successful selector mutation with no response body.
- `401`: missing or incorrect controller secret.
- `503`/`504` from a delay check: node test error or timeout, not controller
  authentication failure.

Differentiate the controller's HTTP response from the status returned by the
destination URL inside a delay test.

For a strict service check, pass the destination's known healthy response code:

~~~bash
openclash-api.sh delay NODE https://api.openai.com/v1/models 7000 401
~~~

The fourth argument becomes Mihomo's `expected` query parameter. Omitting it is
appropriate for a neutral connectivity check, but it is insufficient for
services that return a block page or region error with a valid HTTP response.
