# Persistent service fallback groups

Use this workflow when a subscription template already defines the main policy
groups but a specific service needs a stable, independently tested failover
chain. The controller API cannot create such a group; use OpenClash's overwrite
module so subscription conversion and refresh remain upstream-owned.

## Preconditions and authorization

- Confirm the service's supported regions from an authoritative current source.
- Screen candidates against the actual service with a known expected status.
- Obtain explicit authorization for SSH edits and a core reload.
- Use the rendered dedicated SSH identity with `BatchMode=yes` and
  `IdentitiesOnly=yes`. Never store or reuse the router password.
- Record the active source config, runtime config, OpenClash version, and core
  command line before editing.

## Backup first

Create a timestamped, mode-`0700` directory under `/etc/openclash/backup/` and
copy the active source YAML, runtime YAML, custom overwrite script, and relevant
UCI config into it with mode `0600`. Report the exact rollback directory.

Do not print provider contents or subscription URLs. Inspect only names, paths,
group structure, and the candidate labels needed for the change.

## Build the overwrite module

Register a file-type `config_overwrite` module scoped to the active source
config. A robust service group has:

- one filtered provider per fallback member;
- each filter anchored to exactly one node label;
- a `fallback` group whose `use` list expresses the desired order;
- the service endpoint as `url`, its known response as `expected-status`, and
  finite `interval`, `timeout`, and `max-failed-times` values;
- the new fallback group prepended to the existing service Selector.

Separate single-node providers are deliberate. Provider-native node order may
not match failover priority, while a fallback group's `use` order is stable.

OpenClash runtime generation can rewrite file-provider paths from
`./providers/...` to `./proxy_provider/...`. Point overwrite-added providers at
the runtime cache path used by the active config, then verify their proxy counts
through the controller.

OpenClash YAML modules are shell-expanded by some releases. If a regex contains
shell metacharacters such as `|`, single-quote the YAML scalar so the parser does
not drop or split it. Validate the generated runtime config; do not assume a
syntactically valid module produced the intended group.

## Validate, reload, and verify

1. Validate a staged or generated config with the exact installed core binary.
   If `external-ui` is outside the core home, a one-shot `-t` may need
   `SAFE_PATHS` set to that configured directory; otherwise a safe-path rejection
   is not evidence of invalid YAML. Do not broaden `SAFE_PATHS` beyond the exact
   declared UI directory.
2. Reload OpenClash through its supported init/UCI path; do not restart the
   router unless separately necessary and authorized.
3. Wait for `/version`, then confirm each added provider has exactly one node,
   all nodes are alive, and the fallback `all` order matches the design.
4. Select the new group only in the narrow service Selector.
5. Confirm `profile.store-selected` and the active history/cache path if the
   selection must survive a reload.
6. Send 5–10 real requests through the normal transparent path and inspect a new
   connection chain: service Selector -> fallback group -> final node.
7. Recheck after one additional reload when subscription-refresh persistence is
   part of the requirement.

Rollback is the backed-up source/runtime config plus removal or disabling of the
specific overwrite UCI section. Never replace the whole OpenClash configuration
tree or disturb unrelated user modules.
