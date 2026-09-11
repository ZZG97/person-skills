#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


DEFAULT_FRESHRSS_DB = Path("@@FRESHRSS_DATA_DIR@@") / "users" / "@@FRESHRSS_USER@@" / "db.sqlite"
DEFAULT_RSS_AI_DB = Path("@@RSS_AI_DB_PATH@@")


class LookupError(RuntimeError):
    pass


def readonly_connection(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise LookupError(f"database not found: {path}")
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection
    except sqlite3.Error as exc:
        raise LookupError(f"cannot open database {path}: {exc}") from exc


def decode_json(value: str | None) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def lookup(freshrss_db: Path, rss_ai_db: Path, fragment: str, limit: int) -> list[dict[str, Any]]:
    pattern = f"%{fragment}%"
    with readonly_connection(freshrss_db) as conn:
        rows = conn.execute(
            """
            SELECT e.id, e.guid, e.title, e.link, e.date, e.is_read, e.is_favorite,
                   f.id AS feed_id, f.name AS feed_title, f.url AS feed_url
            FROM entry e
            LEFT JOIN feed f ON f.id = e.id_feed
            WHERE e.link LIKE ? OR e.guid LIKE ? OR e.title LIKE ?
            ORDER BY e.date DESC, e.id DESC
            LIMIT ?
            """,
            (pattern, pattern, pattern, limit),
        ).fetchall()

    with readonly_connection(rss_ai_db) as conn:
        results: list[dict[str, Any]] = []
        for row in rows:
            ai = conn.execute(
                """
                SELECT priority, topics_json, labels_json, confidence, reason,
                       fact_or_opinion, model, cluster_id, author_key, summary,
                       processed_at, dry_run
                FROM processed_entries
                WHERE entry_id = ? OR link = ? OR guid = ?
                ORDER BY processed_at DESC
                LIMIT 1
                """,
                (row["id"], row["link"], row["guid"]),
            ).fetchone()
            item = dict(row)
            if ai is None:
                item["ai"] = None
            else:
                metadata = dict(ai)
                metadata["topics"] = decode_json(metadata.pop("topics_json"))
                metadata["labels"] = decode_json(metadata.pop("labels_json"))
                metadata["dry_run"] = bool(metadata["dry_run"])
                item["ai"] = metadata
            results.append(item)
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only FreshRSS and Sage AI link lookup")
    parser.add_argument("--fragment", required=True, help="distinctive URL, GUID, or title fragment")
    parser.add_argument("--limit", type=int, default=10, choices=range(1, 51), metavar="1..50")
    parser.add_argument("--freshrss-db", type=Path, default=DEFAULT_FRESHRSS_DB)
    parser.add_argument("--rss-ai-db", type=Path, default=DEFAULT_RSS_AI_DB)
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        results = lookup(args.freshrss_db, args.rss_ai_db, args.fragment, args.limit)
    except (LookupError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for item in results:
            ai = item["ai"] or {}
            print(f"{item['id']}\t{item['feed_title']}\t{ai.get('priority', '-')}\t{item['title']}\t{item['link']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
