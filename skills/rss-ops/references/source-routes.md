# Source routes

Choose the least fragile feed source in this order:

1. Official RSS/Atom feed.
2. Stable platform feed or documented API.
3. Existing RSSHub route.
4. A new or patched RSSHub route.
5. Browser-backed extraction only when the above are unavailable.

Before adding a route, verify one real response locally and preserve query
parameters that define the intended scope. Use readable FreshRSS titles and
groups; do not encode machine details into titles.

## Zhihu followees

The canonical local inventory for this installation is:

`@@ZHIHU_FOLLOWEES_FILE@@`

Mutable reconciliation state belongs under:

`@@RSS_OPS_STATE_DIR@@`

Do not place either file inside the installed Skill or public repository. When
expanding followee subscriptions:

1. Read and validate the inventory JSON.
2. List the current FreshRSS subscriptions.
3. Normalize account identifiers and calculate the exact missing set.
4. Probe a sample RSSHub route before a bulk operation.
5. Present the planned additions and count.
6. Add sequentially or in small batches; re-list and persist only reconciliation
   state, never credentials.

If the inventory is stale, refresh it through `use-agent-chrome` with an
explicit isolated profile. Do not silently use a person's daily browser.
