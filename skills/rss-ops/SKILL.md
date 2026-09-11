---
name: rss-ops
description: "Operate a local FreshRSS and RSSHub stack: list/add/remove subscriptions, diagnose feeds and routes, inspect RSSHub deployment or cookie failures, manage Zhihu source inventory, and look up a specific RSS article with its Sage AI classification. Use when the user asks to add/remove/list RSS subscriptions, debug RSSHub, renew source cookies, inspect a subscribed article by URL, or migrate/initialize RSS operations. Do not use for ordinary daily RSS reading, digest generation, ranking, classification, or refresh; use the host-provided sage-rss Skill for those."
---

# RSS Ops

Keep machine operations separate from the agent-facing RSS reader. Use
`sage-rss` for daily reading, ranking, classification, and refresh. Use this
Skill only when changing or diagnosing the underlying RSS stack.

## Fixed local topology

- FreshRSS: `@@FRESHRSS_BASE_URL@@`
- FreshRSS data: `@@FRESHRSS_DATA_DIR@@`
- FreshRSS user: `@@FRESHRSS_USER@@`
- RSSHub: `@@RSSHUB_BASE_URL@@`
- RSSHub deployment: `@@RSSHUB_DEPLOY_DIR@@`
- Sage RSS AI DB: `@@RSS_AI_DB_PATH@@`
- Zhihu inventory: `@@ZHIHU_FOLLOWEES_FILE@@`
- Mutable operations state: `@@RSS_OPS_STATE_DIR@@`

These values are rendered for this installation. Do not copy rendered files
back to the source repository and do not store credentials in this Skill.

## Route the request

- List, add, or remove FreshRSS subscriptions: read
  [FreshRSS operations](references/freshrss.md).
- Diagnose a broken RSSHub route, deployment, or cookie: read
  [RSSHub operations](references/rsshub.md).
- Add or expand a source, including Zhihu followees: read
  [source routes](references/source-routes.md).
- Find a specific subscribed item and its AI label/reason: read
  [link lookup](references/link-lookup.md).
- Set this Skill up on another machine or Agent Home: read
  [initialization](references/initialization.md).

## Safety rules

1. Inspect before mutating. List the exact current feed or route first.
2. Adding one clearly named feed is an in-scope mutation. For bulk additions,
   show the planned count and grouping before applying.
3. Removal must use an exact feed ID, title, or URL. State the resolved target
   before removing it.
4. Prefer FreshRSS APIs. Database deletion is an explicit fallback only; back
   up the user database immediately before using `--db-fallback`.
5. Never print FreshRSS salts, API password hashes, Fever keys, cookies, or
   rendered secret values. This Skill reads local credentials only at runtime.
6. Cookie renewal may use `use-agent-chrome`; write cookies only to the local
   RSSHub runtime configuration and never to this repository.
7. Do not revive the legacy skill-local fetch/digest pipeline or its `data/`
   files. The host App owns ingestion state now.

## Verify completion

After a mutation, re-list the exact feed and confirm its ID, URL, and group.
For an RSSHub-backed source, also request the route locally and confirm it
returns feed content rather than an HTML or verification page.
