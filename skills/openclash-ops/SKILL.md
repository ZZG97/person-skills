---
name: openclash-ops
description: "Diagnose and safely operate an OpenClash/Mihomo transparent proxy on a managed home or office network. Use whenever the user mentions OpenClash, Mihomo, transparent proxy, intermittent disconnects, TLS handshake EOF/reset, fake-IP, DNS hijacking, proxy nodes, policy groups, the controller API, or asks to inspect or switch proxy routes. Covers layered network diagnosis, API snapshots, rule and connection tracing, service-specific node testing, and explicitly authorized selector changes; do not use for unrelated application debugging or general cloud network administration."
---

# OpenClash Ops

Treat the transparent proxy as one layer in the network, not as the default
explanation for every failure. Establish which layer breaks, then use the
controller API to trace the affected service from rule to policy group to node.

## Managed controller

- API: `@@OPENCLASH_API_URL@@`
- macOS Keychain service: `@@OPENCLASH_KEYCHAIN_SERVICE@@`
- macOS Keychain account: `@@OPENCLASH_KEYCHAIN_ACCOUNT@@`
- Router SSH: `@@OPENCLASH_SSH_USER@@@@@OPENCLASH_SSH_HOST@@`
- Dedicated SSH key: `@@OPENCLASH_SSH_KEY_PATH@@`
- Helper: `scripts/openclash-api.sh`

These are rendered machine-local values. Read the API secret at runtime from
`OPENCLASH_API_SECRET` or macOS Keychain. Never copy a secret into a command,
Skill, report, memory file, repository, or generated artifact.

## Route the request

- For intermittent connection, DNS, fake-IP, TLS, or node-quality diagnosis,
  read [diagnostics.md](references/diagnostics.md).
- For endpoint semantics and safe API operations, read
  [api-operations.md](references/api-operations.md).
- For a persistent service-specific fallback group, read
  [fallback-groups.md](references/fallback-groups.md).
- For a new machine, controller, or credential setup, read
  [initialization.md](references/initialization.md).

## Default workflow

1. Interpret words such as “看看”, “排查”, or “研究” as read-only diagnosis.
   Do not turn them into a node switch, cache clear, reload, or restart.
2. Split the path into client link, router/WAN, DNS and fake-IP, transparent
   capture, rule match, policy group, outbound node, and destination service.
3. Verify the controller with `openclash-api.sh version`, then take a compact
   `snapshot`. Do not dump full configs or provider data when a summary answers
   the question.
4. Trace the affected domain through `/rules` or an active `/connections`
   record. Record the matched rule, outer selector, nested automatic group, and
   final node.
5. Compare the same node against a neutral control URL and the failing service.
   A Cloudflare or Google health check does not prove that OpenAI or another
   destination accepts the node's egress IP.
6. For services with a known response code, require that code during delay
   checks. OpenAI `/v1/models` without credentials must return `401`; accepting
   any HTTP status can misclassify an unsupported-region response as healthy.
7. Test enough candidates to distinguish one bad node from a broken group or
   provider. Prefer 3–5 repeated service-specific checks for a proposed node.
8. Explain the evidence and proposed minimal change before mutating anything.
9. After explicit user authorization, change the narrowest outer service
   selector directly to a verified node. Avoid changing a shared country group
   when that would affect unrelated traffic.
10. Verify the selected state and run 5–10 real end-to-end requests. Report the
   prior selection, new selection, success rate, latency, and rollback value.

## Mutation boundary

The controller secret grants full control and has no read-only scope. Default to
GET operations and delay tests. A selector change requires a direct user request
such as “切到这个节点” or an affirmative response to the exact proposed change.

Do not reload the configuration, restart OpenClash or the router, clear fake-IP
state, update providers, close connections, or alter rules without separate
evidence and authorization. Never restart an application merely because its
upstream proxy path is failing.

The controller API can select an existing group but cannot add a durable policy
group. Creating one requires SSH access to OpenWrt/OpenClash, a backup, core
validation, and an OpenClash overwrite module so subscription refreshes do not
erase it. Treat that as a wider mutation and follow `fallback-groups.md`.

## Security boundary

- Keep the controller on loopback or a trusted LAN. Never add WAN forwarding,
  a public tunnel, Funnel, or broad reverse proxy exposure.
- Do not weaken or remove the controller secret for convenience.
- Avoid printing full provider configurations because subscription URLs can
  contain credentials.
- Do not place credentials in `skill-kit.local.json`; it stores identifiers and
  paths only.
- Never store the router password. Use the dedicated key above with
  `BatchMode=yes` and `IdentitiesOnly=yes`; do not print or copy the private key.
- If a secret was pasted into chat or logs, recommend rotation after the active
  incident is stable.

## Report shape

Lead with the affected layer and confidence. Then give compact evidence,
current impact, and the smallest next action. Clearly separate observed facts
from inferences and name any controller view or credential that remains blocked.
