# Specific-link lookup

Use exact or distinctive URL fragments to join the FreshRSS article with Sage
AI metadata:

```bash
python3 scripts/rss_lookup.py --fragment 'distinctive-url-fragment' --json
```

The command is read-only. It searches FreshRSS title/link/date/feed fields and
then matches `processed_entries` by entry ID, link, or GUID. It reports the
priority, topics, labels, confidence, reason, summary, and processing time when
available.

If multiple rows match, narrow the fragment rather than guessing. If the item
exists in FreshRSS but lacks AI metadata, use `sage-rss` to inspect ingestion or
refresh state. Do not edit either SQLite database to manufacture a match.
