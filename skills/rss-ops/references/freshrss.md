# FreshRSS operations

Use the bundled helper; it reads runtime credentials from the FreshRSS data
directory and never prints them.

```bash
python3 scripts/freshrss_api.py check-greader --json
python3 scripts/freshrss_api.py list-groups
python3 scripts/freshrss_api.py list-feeds --show-urls
python3 scripts/freshrss_api.py list-feeds --group 'Group name' --json
```

## Add one feed

Resolve the final feed URL first. For an RSSHub route, request it directly and
check for XML before subscribing.

```bash
python3 scripts/freshrss_api.py add-feed \
  --url 'http://host.docker.internal:1200/example/route' \
  --title 'Readable title' \
  --group 'Group name' \
  --json
```

FreshRSS runs in a container in many installations, so a loopback RSSHub URL
that works on the host may need `host.docker.internal` in the subscribed URL.
Use the topology of the actual installation; do not blindly rewrite URLs.

## Remove one feed

List feeds first and resolve exactly one target. Then remove by ID when
possible:

```bash
python3 scripts/freshrss_api.py remove-feed --id 123 --json
```

If GReader unsubscribe is unavailable, stop and explain the fallback. Only
after an immediate database backup may you run:

```bash
python3 scripts/freshrss_api.py remove-feed --id 123 --db-fallback --json
```

Re-list after either operation. If direct SQLite inspection is needed, open
`@@FRESHRSS_DATA_DIR@@/users/@@FRESHRSS_USER@@/db.sqlite` read-only whenever
possible.
