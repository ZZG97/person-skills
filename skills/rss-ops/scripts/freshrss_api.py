#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib import error, parse, request


DEFAULT_BASE_URL = "@@FRESHRSS_BASE_URL@@"
DEFAULT_DATA_DIR = Path("@@FRESHRSS_DATA_DIR@@")
DEFAULT_USER = "@@FRESHRSS_USER@@"


class RssOpsError(RuntimeError):
    pass


@dataclass
class FeedRecord:
    feed_id: int
    title: str
    feed_url: str
    site_url: str
    group: str | None = None


def parse_php_array_string(path: Path, key: str) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RssOpsError(f"cannot read FreshRSS config {path}: {exc}") from exc
    pattern = re.compile(rf"'{re.escape(key)}'\s*=>\s*'((?:\\.|[^'])*)'")
    match = pattern.search(text)
    if not match:
        raise RssOpsError(f"cannot find `{key}` in {path}")
    return match.group(1).replace("\\'", "'").replace("\\\\", "\\")


def api_paths(base_url: str) -> tuple[str, str]:
    base = base_url.rstrip("/")
    return f"{base}/api/fever.php", f"{base}/api/greader.php"


def post_form(url: str, payload: dict[str, str], headers: dict[str, str] | None = None, timeout: int = 20) -> str:
    req = request.Request(url, data=parse.urlencode(payload).encode(), method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RssOpsError(f"HTTP {exc.code} from {url}: {detail}") from exc
    except error.URLError as exc:
        raise RssOpsError(f"connection failed for {url}: {exc}") from exc


def fever_request(base_url: str, fever_key: str, **params: str) -> dict[str, Any]:
    fever_url, _ = api_paths(base_url)
    body = post_form(fever_url, {"api_key": fever_key, **params})
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RssOpsError("FreshRSS Fever endpoint did not return JSON") from exc
    if not isinstance(data, dict) or data.get("auth") != 1:
        raise RssOpsError("FreshRSS Fever authentication failed")
    return data


def user_paths(data_dir: Path, username: str) -> tuple[Path, Path, Path]:
    user_dir = data_dir / "users" / username
    return data_dir / "config.php", user_dir / "config.php", user_dir / "db.sqlite"


def load_fever_key(user_config: Path) -> str:
    key = parse_php_array_string(user_config, "feverKey")
    if not re.fullmatch(r"[0-9a-f]{32}", key):
        raise RssOpsError(f"invalid Fever key in {user_config}")
    return key


def greader_auth_token(system_config: Path, user_config: Path, username: str) -> str:
    salt = parse_php_array_string(system_config, "salt")
    password_hash = parse_php_array_string(user_config, "apiPasswordHash")
    digest = hashlib.sha1(f"{salt}{username}{password_hash}".encode()).hexdigest()
    return f"{username}/{digest}"


def greader_headers(auth_token: str) -> dict[str, str]:
    return {"Authorization": f"GoogleLogin auth={auth_token}"}


def greader_check(base_url: str, auth_token: str) -> tuple[bool, str]:
    _, greader_url = api_paths(base_url)
    req = request.Request(f"{greader_url}/check/compatibility", headers=greader_headers(auth_token))
    try:
        with request.urlopen(req, timeout=20) as resp:
            detail = resp.read().decode("utf-8", "replace").strip()
            return detail == "PASS", detail
    except error.HTTPError as exc:
        return False, exc.read().decode("utf-8", "replace").strip() or f"HTTP {exc.code}"
    except error.URLError as exc:
        return False, str(exc)


def fetch_groups(base_url: str, fever_key: str) -> list[dict[str, Any]]:
    groups = list(fever_request(base_url, fever_key, groups="1").get("groups", []))
    return sorted(groups, key=lambda item: str(item["title"]).lower())


def fetch_feeds(base_url: str, fever_key: str) -> list[FeedRecord]:
    data = fever_request(base_url, fever_key, feeds="1", groups="1")
    groups = {int(item["id"]): str(item["title"]) for item in data.get("groups", [])}
    feed_groups: dict[int, int] = {}
    for item in data.get("feeds_groups", []):
        for raw_id in str(item.get("feed_ids", "")).split(","):
            if raw_id:
                feed_groups[int(raw_id)] = int(item["group_id"])
    feeds = [
        FeedRecord(
            feed_id=int(item["id"]),
            title=str(item["title"]),
            feed_url=str(item["url"]),
            site_url=str(item["site_url"]),
            group=groups.get(feed_groups.get(int(item["id"]))),
        )
        for item in data.get("feeds", [])
    ]
    return sorted(feeds, key=lambda item: ((item.group or ""), item.title.lower(), item.feed_id))


def find_feed(db_path: Path, feed_id: int | None, title: str | None, url: str | None) -> FeedRecord:
    field, value = ("id", feed_id) if feed_id is not None else (("name", title) if title is not None else ("url", url))
    uri = f"file:{db_path}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as conn:
            rows = conn.execute(
                f"SELECT id, name, url, COALESCE(website, '') FROM feed WHERE {field} = ?", (value,)
            ).fetchall()
    except sqlite3.Error as exc:
        raise RssOpsError(f"cannot inspect FreshRSS database {db_path}: {exc}") from exc
    if not rows:
        raise RssOpsError("feed not found")
    if len(rows) != 1:
        raise RssOpsError("feed match is ambiguous")
    row = rows[0]
    return FeedRecord(int(row[0]), str(row[1]), str(row[2]), str(row[3]))


def db_delete_feed(db_path: Path, feed_id: int) -> int:
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            cursor = conn.execute("DELETE FROM feed WHERE id = ?", (feed_id,))
            return cursor.rowcount
    except sqlite3.Error as exc:
        raise RssOpsError(f"database fallback failed: {exc}") from exc


def cmd_list_groups(args: argparse.Namespace) -> int:
    _, config, _ = user_paths(args.data_dir, args.user)
    groups = fetch_groups(args.base_url, load_fever_key(config))
    if args.json:
        print(json.dumps(groups, ensure_ascii=False, indent=2))
    else:
        for group in groups:
            print(f"{group['id']}\t{group['title']}")
    return 0


def cmd_list_feeds(args: argparse.Namespace) -> int:
    _, config, _ = user_paths(args.data_dir, args.user)
    feeds = fetch_feeds(args.base_url, load_fever_key(config))
    if args.group:
        feeds = [item for item in feeds if item.group == args.group]
    if args.json:
        print(json.dumps([asdict(item) for item in feeds], ensure_ascii=False, indent=2))
        return 0
    for item in feeds:
        suffix = f"\t{item.feed_url}" if args.show_urls else ""
        print(f"{item.feed_id}\t{item.group or 'Ungrouped'}\t{item.title}{suffix}")
    return 0


def cmd_check_greader(args: argparse.Namespace) -> int:
    system, config, _ = user_paths(args.data_dir, args.user)
    ok, detail = greader_check(args.base_url, greader_auth_token(system, config, args.user))
    if args.json:
        print(json.dumps({"ok": ok, "detail": detail}, ensure_ascii=False, indent=2))
    else:
        print(f"{'PASS' if ok else 'FAIL'}\t{detail}")
    return 0 if ok else 1


def cmd_add_feed(args: argparse.Namespace) -> int:
    system, config, _ = user_paths(args.data_dir, args.user)
    fever_key = load_fever_key(config)
    found = next((item for item in fetch_feeds(args.base_url, fever_key) if item.feed_url == args.url), None)
    created = False
    reply = None
    if found is None:
        auth_token = greader_auth_token(system, config, args.user)
        ok, detail = greader_check(args.base_url, auth_token)
        if not ok:
            raise RssOpsError(f"GReader subscribe unavailable: {detail}")
        _, greader_url = api_paths(args.base_url)
        reply = post_form(
            f"{greader_url}/reader/api/0/subscription/edit",
            {"ac": "subscribe", "s": f"feed/{args.url}", "t": args.title, "a": f"user/-/label/{args.group}"},
            greader_headers(auth_token),
            timeout=60,
        ).strip()
        found = next((item for item in fetch_feeds(args.base_url, fever_key) if item.feed_url == args.url), None)
        if found is None:
            raise RssOpsError("GReader reported success but the feed was not found")
        created = True
    result = {**asdict(found), "created": created}
    if reply is not None:
        result["reply"] = reply
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{'added' if created else 'already exists'}\t{found.feed_id}\t{found.group}\t{found.title}")
    return 0


def cmd_remove_feed(args: argparse.Namespace) -> int:
    system, config, db_path = user_paths(args.data_dir, args.user)
    target = find_feed(db_path, args.id, args.title, args.url)
    auth_token = greader_auth_token(system, config, args.user)
    ok, detail = greader_check(args.base_url, auth_token)
    method: str
    reply: str | None = None
    if ok:
        _, greader_url = api_paths(args.base_url)
        reply = post_form(
            f"{greader_url}/reader/api/0/subscription/edit",
            {"ac": "unsubscribe", "s": f"feed/{target.feed_id}"},
            greader_headers(auth_token),
        ).strip()
        method = "greader"
    elif args.db_fallback:
        deleted = db_delete_feed(db_path, target.feed_id)
        if deleted != 1:
            raise RssOpsError(f"database fallback deleted {deleted} rows, expected 1")
        method = "db-fallback"
    else:
        raise RssOpsError("GReader unsubscribe unavailable; back up the database and explicitly pass --db-fallback")
    result: dict[str, Any] = {**asdict(target), "method": method}
    if reply is not None:
        result["reply"] = reply
    if method == "db-fallback":
        result["greader_detail"] = detail
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"removed via {method}\t{target.feed_id}\t{target.title}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FreshRSS management helpers for rss-ops")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--user", default=DEFAULT_USER)
    commands = parser.add_subparsers(dest="command", required=True)

    command = commands.add_parser("list-groups", help="list FreshRSS groups")
    command.add_argument("--json", action="store_true")
    command.set_defaults(func=cmd_list_groups)

    command = commands.add_parser("list-feeds", help="list FreshRSS feeds")
    command.add_argument("--group")
    command.add_argument("--show-urls", action="store_true")
    command.add_argument("--json", action="store_true")
    command.set_defaults(func=cmd_list_feeds)

    command = commands.add_parser("check-greader", help="verify GReader authentication")
    command.add_argument("--json", action="store_true")
    command.set_defaults(func=cmd_check_greader)

    command = commands.add_parser("add-feed", help="subscribe to one feed")
    command.add_argument("--url", required=True)
    command.add_argument("--title", required=True)
    command.add_argument("--group", required=True)
    command.add_argument("--json", action="store_true")
    command.set_defaults(func=cmd_add_feed)

    command = commands.add_parser("remove-feed", help="remove one exact feed")
    match = command.add_mutually_exclusive_group(required=True)
    match.add_argument("--id", type=int)
    match.add_argument("--title")
    match.add_argument("--url")
    command.add_argument("--db-fallback", action="store_true")
    command.add_argument("--json", action="store_true")
    command.set_defaults(func=cmd_remove_feed)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.func(args))
    except RssOpsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
