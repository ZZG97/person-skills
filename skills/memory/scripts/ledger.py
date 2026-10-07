#!/usr/bin/env python3
"""Memory's ledger engine: a local record of the matters a person is tracking.

The program is deterministic. It owns the data files, validation, follow-up scheduling,
rendered views and run bookkeeping. Agents decide what a conversation means and write
through `apply-updates`; nothing here reads a messaging platform or calls an agent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

VERSION = "0.2.0"
CONFIG_ENV = "PLEDGER_CONFIG"
DATA_ENV = "PLEDGER_DATA_DIR"
SHIM_NAME = "pledger"
SKILL_DIR = Path(__file__).resolve().parents[1]

VALID_DISPOSITIONS = {"active", "waiting", "observe", "transferred", "closed"}
OPEN_DISPOSITIONS = {"active", "waiting", "observe"}
TODO_DISPOSITIONS = {"active", "waiting"}
TERMINAL_DISPOSITIONS = {"closed", "transferred"}

VALID_EVENT_TYPES = {
    "baseline",
    "user_decision",
    "user_report",
    "agent_report",
    "observation",
    "gap",
    "correction",
    "notification",
    "followup_check",
}
# Events that may change an item's current state (disposition, plan, title).
AUTHORITATIVE_EVENT_TYPES = {"user_decision", "user_report", "agent_report", "observation", "correction", "followup_check"}

VALID_PARTICIPANT_ROLES = {"", "requester", "owner", "executor", "reviewer", "informed"}
DEFAULT_CATEGORY = "general"
MAX_CATEGORY_CHARS = 32

# Follow-up: every open item says how it moves forward, so it does not sink until someone
# mentions it again. check = an agent verifies it, chase = waiting on someone the user has to
# nudge (agents never send the nudge), decide = the user must choose, none = nothing to follow.
VALID_FOLLOWUP_MODES = {"check", "chase", "decide", "none"}
CHECKED_MODES = ["check", "chase"]
VALID_FOLLOWUP_ALLOW = {"read_only", "needs_approval"}
VALID_FOLLOWUP_RESULTS = {"progressed", "no_change", "done", "blocked"}
FOLLOWUP_DEFAULT_INTERVAL_DAYS = {"check": 1, "chase": 2, "decide": 1, "none": 1}
FOLLOWUP_MAX_INTERVAL_DAYS = 7
FOLLOWUP_ESCALATE_AFTER_BLOCKED = 3
FOLLOWUP_STALE_DAYS = 4
FOLLOWUP_URGENT_DAYS = 1
FOLLOWUP_OVERDUE_GRACE_DAYS = 1
FOLLOWUP_SETTABLE_FIELDS = {
    "mode", "who", "how", "done_when", "next_check_at", "due_at", "allow",
    "interval_days", "waiting_on", "waiting_since", "chase_draft", "note",
}
FOLLOWUP_PROGRAM_FIELDS = {"no_change_streak", "blocked_streak", "last_checked_at", "last_result", "set_at"}
# Waiting on the user (decide) or on someone else (chase) is what "waiting" means.
FOLLOWUP_MODE_STATUS = {"decide": "waiting", "chase": "waiting"}

MAX_ACTION_CHARS = 200
MAX_TITLE_CHARS = 40
INDEX_NEXT_CHARS = 80
VAGUE_OWNERS = {"tbd", "todo", "?", "？", "unknown", "someone", "somebody", "n/a", "待定", "未知", "相关方", "某人"}
OWNER_SEPARATOR = re.compile(r"\s*(?:/|、|,|，|;|；|\sand\s|\s和\s)\s*")
SELF_NAMES = {"me", "myself", "user", "我", "本人", "用户"}

JOBS = ("followup", "digest")
JOB_STALE_HOURS = {"followup": 74, "digest": 74}
RUN_STALLED_HOURS = 3
REPLACE_FLAGS = ("replace_facts", "replace_gaps", "replace_participants", "replace_external_refs", "replace_next_actions")


class LedgerError(RuntimeError):
    def __init__(self, code: str, message: str, details: Any | None = None):
        super().__init__(message)
        self.code = code
        self.details = details


# ---------------------------------------------------------------------------
# Time and files


def now_local() -> datetime:
    return datetime.now().astimezone().replace(microsecond=0)


def iso_now() -> str:
    return now_local().isoformat()


def iso_time(value: datetime) -> str:
    return value.astimezone().replace(microsecond=0).isoformat()


def parse_time(value: Any, field: str = "time") -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise LedgerError("invalid_time", f"{field} is missing or invalid")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d %H:%M")
        except ValueError as exc:
            raise LedgerError("invalid_time", f"{field} is not an ISO time: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=now_local().tzinfo)
    return parsed.astimezone()


def parse_time_or_min(value: Any) -> datetime:
    try:
        return parse_time(value)
    except LedgerError:
        return datetime.fromtimestamp(0, tz=timezone.utc).astimezone()


def read_json(path: Path, *, required: bool = True) -> dict[str, Any]:
    if not path.exists():
        if required:
            raise LedgerError("missing_file", f"JSON file does not exist: {path}")
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LedgerError("invalid_json", f"cannot read JSON file: {path}") from exc
    if not isinstance(value, dict):
        raise LedgerError("invalid_json", f"expected a JSON object: {path}")
    return value


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    write_text_atomic(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def require_str(obj: dict[str, Any], key: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise LedgerError("invalid_update", f"{key} must be a non-empty string")
    return value


def emit(result: dict[str, Any]) -> dict[str, Any]:
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def now_arg(args: argparse.Namespace) -> datetime:
    return parse_time(args.now, "--now") if getattr(args, "now", None) else now_local()


# ---------------------------------------------------------------------------
# Validation


def validate_evidence_ref(ref: Any) -> None:
    if not isinstance(ref, dict):
        raise LedgerError("invalid_update", "evidence refs must be objects")
    require_str(ref, "type")
    require_str(ref, "ref")
    ref.setdefault("note", "")
    if not isinstance(ref["note"], str):
        raise LedgerError("invalid_update", "evidence note must be a string")


def validate_category(item_id: str, category: Any) -> None:
    if not isinstance(category, str) or not category.strip() or len(category) > MAX_CATEGORY_CHARS:
        raise LedgerError("invalid_item", f"category for {item_id} must be a short non-empty string")


def validate_followup(item: dict[str, Any]) -> None:
    followup = item.get("followup")
    if followup is None:
        return
    item_id = item.get("item_id")
    if not isinstance(followup, dict):
        raise LedgerError("invalid_item", f"followup must be an object for {item_id}")
    mode = followup.get("mode", "none")
    if mode not in VALID_FOLLOWUP_MODES:
        raise LedgerError("invalid_item", f"invalid followup.mode {mode!r} for {item_id}; use one of {sorted(VALID_FOLLOWUP_MODES)}")
    if followup.get("allow", "read_only") not in VALID_FOLLOWUP_ALLOW:
        raise LedgerError("invalid_item", f"invalid followup.allow for {item_id}; use one of {sorted(VALID_FOLLOWUP_ALLOW)}")
    if mode == "check" and not (str(followup.get("how") or "").strip() and str(followup.get("done_when") or "").strip()):
        raise LedgerError("invalid_item", f"followup mode check needs a concrete how and done_when for {item_id}")
    if mode == "chase" and not str(followup.get("waiting_on") or "").strip():
        raise LedgerError("invalid_item", f"followup mode chase needs waiting_on for {item_id}")
    for key in ("next_check_at", "due_at", "waiting_since", "last_checked_at", "set_at"):
        if followup.get(key):
            parse_time(followup[key], f"followup.{key}")
    interval = followup.get("interval_days")
    if interval is not None and (isinstance(interval, bool) or not isinstance(interval, int) or not 1 <= interval <= FOLLOWUP_MAX_INTERVAL_DAYS):
        raise LedgerError("invalid_item", f"followup.interval_days must be 1..{FOLLOWUP_MAX_INTERVAL_DAYS} for {item_id}")
    if followup.get("last_result") and followup["last_result"] not in VALID_FOLLOWUP_RESULTS:
        raise LedgerError("invalid_item", f"invalid followup.last_result for {item_id}")


def validate_item(item: dict[str, Any]) -> None:
    item_id = require_str(item, "item_id")
    require_str(item, "title")
    disposition = item.get("disposition")
    if not isinstance(disposition, dict) or disposition.get("status") not in VALID_DISPOSITIONS:
        raise LedgerError("invalid_item", f"invalid disposition for {item_id}; status must be one of {sorted(VALID_DISPOSITIONS)}")
    for key in ("external_refs", "facts", "next_actions", "events", "gaps", "participants"):
        if not isinstance(item.get(key), list):
            raise LedgerError("invalid_item", f"{key} must be a list for {item_id}")
    validate_category(item_id, item.setdefault("category", DEFAULT_CATEGORY))
    for person in item["participants"]:
        if not isinstance(person, dict) or not person.get("name"):
            raise LedgerError("invalid_item", f"participants need a name for {item_id}")
        person.setdefault("role_in_item", "")
        if person["role_in_item"] not in VALID_PARTICIPANT_ROLES:
            raise LedgerError("invalid_item", f"invalid role_in_item {person['role_in_item']!r} for {item_id}; use one of {sorted(VALID_PARTICIPANT_ROLES)}")
    validate_followup(item)
    seen: set[str] = set()
    for event in item["events"]:
        if not isinstance(event, dict):
            raise LedgerError("invalid_item", f"events must be objects for {item_id}")
        for key in ("event_key", "type", "observed_at", "summary"):
            require_str(event, key)
        if event["type"] not in VALID_EVENT_TYPES:
            raise LedgerError("invalid_item", f"invalid event type {event['type']!r} for {item_id}; use one of {sorted(VALID_EVENT_TYPES)}")
        if event["event_key"] in seen:
            raise LedgerError("invalid_item", f"duplicate event_key {event['event_key']} in {item_id}")
        seen.add(event["event_key"])
        for ref in event.get("evidence", []):
            validate_evidence_ref(ref)


def owner_problem(owner: Any) -> str:
    """Why an action owner names nobody concrete, or "" if every listed owner can be asked directly."""
    text = str(owner or "").strip()
    if not text:
        return "owner is empty"
    vague = [part for part in OWNER_SEPARATOR.split(text) if not part or part.lower() in VAGUE_OWNERS]
    if vague:
        return f"owner {text!r} contains a placeholder ({', '.join(repr(v) for v in vague)}); name a person, or record a gap"
    return ""


def action_problems(action: Any) -> list[str]:
    if not isinstance(action, dict):
        return ["next_action must be an object"]
    problems = []
    text = str(action.get("action") or "").strip()
    if not text:
        problems.append("action is empty")
    elif len(text) > MAX_ACTION_CHARS:
        problems.append(f"action has {len(text)} chars, over {MAX_ACTION_CHARS}; move detail into preconditions or an event")
    owner = owner_problem(action.get("owner"))
    if owner:
        problems.append(owner)
    if action.get("due"):
        try:
            parse_time(action["due"], "due")
        except LedgerError:
            problems.append(f"due {action['due']!r} is not an ISO time such as 2026-09-30 or 2026-09-30T18:00:00+08:00")
    return problems


def validate_incoming_next_actions(item_id: str, actions: Any) -> None:
    if not isinstance(actions, list):
        raise LedgerError("invalid_update", f"next_actions must be a list for {item_id}")
    for action in actions:
        problems = action_problems(action)
        if problems:
            raise LedgerError("invalid_update", f"next_action for {item_id}: {'; '.join(problems)}", action)


def check_mode_status(item: dict[str, Any], incoming: dict[str, Any]) -> None:
    """Reject a write that newly pairs decide/chase with a non-waiting status."""
    touched_mode = isinstance(incoming.get("followup"), dict) and "mode" in incoming["followup"]
    touched_status = isinstance(incoming.get("disposition"), dict) and "status" in incoming["disposition"]
    if not (touched_mode or touched_status):
        return
    status = item["disposition"]["status"]
    mode = (item.get("followup") or {}).get("mode", "none")
    expected = FOLLOWUP_MODE_STATUS.get(mode)
    if expected and status in OPEN_DISPOSITIONS and status != expected:
        raise LedgerError(
            "invalid_update",
            f"{item['item_id']}: followup.mode={mode} means waiting on someone, so disposition.status must be {expected} "
            f"(now {status}); send the disposition and an event in the same update",
        )


# ---------------------------------------------------------------------------
# Events and current-state ordering


def event_effective_time(event: dict[str, Any]) -> datetime:
    for key in ("effective_at", "occurred_at"):
        if event.get(key):
            return parse_time_or_min(event[key])
    return parse_time_or_min(event.get("observed_at"))


def latest_event_time(item: dict[str, Any]) -> datetime:
    times = [parse_time_or_min(item["current_event_time"])] if item.get("current_event_time") else []
    if item.get("disposition", {}).get("decided_at"):
        times.append(parse_time_or_min(item["disposition"]["decided_at"]))
    times += [event_effective_time(e) for e in item.get("events", []) if isinstance(e, dict)]
    return max(times) if times else datetime.fromtimestamp(0, tz=timezone.utc).astimezone()


def update_effective_time(update: dict[str, Any]) -> datetime:
    if update.get("effective_at"):
        return parse_time_or_min(update["effective_at"])
    disposition = update.get("disposition")
    if isinstance(disposition, dict) and disposition.get("decided_at"):
        return parse_time_or_min(disposition["decided_at"])
    times = [event_effective_time(e) for e in update.get("events", []) if isinstance(e, dict)]
    return max(times) if times else now_local()


def update_event_keys(update: dict[str, Any]) -> list[str]:
    return [str(e["event_key"]) for e in update.get("events", []) if isinstance(e, dict) and e.get("event_key")]


def can_update_current(item_exists: bool, item: dict[str, Any], incoming: dict[str, Any], existing_keys: set[str]) -> bool:
    """Current state only moves forward: a replayed or older update must not undo a newer decision."""
    if not item_exists or incoming.get("force_current"):
        return True
    types = {str(e.get("type")) for e in incoming.get("events", []) if isinstance(e, dict)}
    if not types & AUTHORITATIVE_EVENT_TYPES:
        return False
    keys = update_event_keys(incoming)
    if keys and all(key in existing_keys for key in keys):
        return False
    incoming_time, current_time = update_effective_time(incoming), latest_event_time(item)
    if incoming_time != current_time:
        return incoming_time > current_time
    current_keys = set(item.get("current_event_keys") or [])
    return not (keys and set(keys) <= current_keys)


def merge_unique(existing: list[Any], incoming: list[Any], key_fields: tuple[str, ...]) -> list[Any]:
    result = list(existing)
    seen = {tuple(str(x.get(f, "")) for f in key_fields) for x in result if isinstance(x, dict)}
    for entry in incoming:
        if not isinstance(entry, dict):
            continue
        key = tuple(str(entry.get(f, "")) for f in key_fields)
        if key not in seen:
            seen.add(key)
            result.append(entry)
    return result


def merge_participants(people: list[Any]) -> list[dict[str, Any]]:
    """One row per name; later mentions fill in or update the role and note."""
    merged: dict[str, dict[str, Any]] = {}
    for person in people:
        if not isinstance(person, dict) or not person.get("name"):
            continue
        current = merged.setdefault(str(person["name"]), {"name": person["name"], "role_in_item": ""})
        current.update({k: v for k, v in person.items() if v not in (None, "")})
    return list(merged.values())


# ---------------------------------------------------------------------------
# Follow-up


def followup_interval(followup: dict[str, Any]) -> int:
    return int(followup.get("interval_days") or FOLLOWUP_DEFAULT_INTERVAL_DAYS.get(followup.get("mode", "none"), 1))


def cap_by_due(next_at: datetime, followup: dict[str, Any], base: datetime) -> datetime:
    if followup.get("due_at"):
        due = parse_time_or_min(followup["due_at"])
        if base < due < next_at:
            return due
    return next_at


def apply_followup_setting(item: dict[str, Any], incoming: Any, when: datetime) -> None:
    if not isinstance(incoming, dict):
        raise LedgerError("invalid_update", f"followup must be an object for {item['item_id']}")
    forbidden = set(incoming) & FOLLOWUP_PROGRAM_FIELDS
    if forbidden:
        raise LedgerError("invalid_update", f"followup fields {sorted(forbidden)} are derived from followup_result; do not set them")
    unknown = set(incoming) - FOLLOWUP_SETTABLE_FIELDS
    if unknown:
        raise LedgerError("invalid_update", f"unknown followup fields {sorted(unknown)}; use {sorted(FOLLOWUP_SETTABLE_FIELDS)}")
    current = dict(item.get("followup") or {})
    mode_changed = "mode" in incoming and incoming["mode"] != current.get("mode")
    if any(incoming.get(k) != current.get(k) for k in ("mode", "how", "done_when", "waiting_on") if k in incoming):
        current["set_at"] = iso_time(when)
    current.update(incoming)
    current.setdefault("mode", "none")
    current.setdefault("allow", "read_only")
    if mode_changed:
        current["no_change_streak"] = 0
        current["blocked_streak"] = 0
        if "next_check_at" not in incoming:
            current["next_check_at"] = ""
        if current["mode"] == "chase" and "waiting_since" not in incoming:
            current["waiting_since"] = iso_time(when)
    if current["mode"] == "none":
        current["next_check_at"] = ""
    elif not current.get("next_check_at"):
        current["next_check_at"] = iso_time(cap_by_due(when + timedelta(days=followup_interval(current)), current, when))
    item["followup"] = current


def apply_followup_result(item: dict[str, Any], incoming: Any, existing_keys: set[str]) -> None:
    """Record one follow-up check; the program, not the agent, decides when to look next."""
    if not isinstance(incoming, dict):
        raise LedgerError("invalid_update", f"followup_result must be an object for {item['item_id']}")
    result = incoming.get("result")
    if result not in VALID_FOLLOWUP_RESULTS:
        raise LedgerError("invalid_update", f"followup_result.result must be one of {sorted(VALID_FOLLOWUP_RESULTS)}")
    summary = require_str(incoming, "summary")
    checked = parse_time(incoming.get("checked_at") or iso_now(), "followup_result.checked_at")
    key = f"followup:{item['item_id']}:{iso_time(checked)}"
    if key in existing_keys:
        return  # replay of an already recorded check
    evidence = incoming.get("evidence", [])
    if not isinstance(evidence, list):
        raise LedgerError("invalid_update", "followup_result.evidence must be a list")
    for ref in evidence:
        validate_evidence_ref(ref)
    followup = dict(item.get("followup") or {"mode": "none", "allow": "read_only"})
    item["events"].append({
        "event_key": key,
        "type": "followup_check",
        "observed_at": iso_time(checked),
        "summary": f"[{result}] {summary}",
        "followup_result": result,
        "actor": {"name": str(incoming.get("actor") or followup.get("who") or "agent")},
        "evidence": evidence,
    })
    existing_keys.add(key)
    interval = followup_interval(followup)
    followup["last_checked_at"] = iso_time(checked)
    followup["last_result"] = result
    days = interval
    if result == "progressed":
        followup["no_change_streak"] = 0
        followup["blocked_streak"] = 0
    elif result == "no_change":
        followup["no_change_streak"] = int(followup.get("no_change_streak") or 0) + 1
        days = min(interval * 2 ** followup["no_change_streak"], FOLLOWUP_MAX_INTERVAL_DAYS)
    elif result == "blocked":
        followup["blocked_streak"] = int(followup.get("blocked_streak") or 0) + 1
    if result == "done":
        followup["mode"] = "none"
        followup["next_check_at"] = ""
        if item["disposition"]["status"] in OPEN_DISPOSITIONS:
            item["disposition"] = {
                "status": "closed",
                "reason": f"follow-up confirmed the end condition: {followup.get('done_when') or summary}",
                "source": key,
                "decided_at": iso_time(checked),
            }
            item["current_event_time"] = iso_time(checked)
            item["current_event_keys"] = [key]
    elif incoming.get("next_check_at"):
        followup["next_check_at"] = iso_time(parse_time(incoming["next_check_at"], "followup_result.next_check_at"))
    else:
        followup["next_check_at"] = iso_time(cap_by_due(checked + timedelta(days=days), followup, checked))
    item["followup"] = followup


def retire_terminal_item(item: dict[str, Any], when: datetime) -> None:
    """A closed/transferred item has no plan left: park its actions and stop follow-up."""
    if item["disposition"]["status"] not in TERMINAL_DISPOSITIONS:
        return
    if item.get("next_actions"):
        stamp = iso_time(when)
        item.setdefault("retired_next_actions", []).extend({**a, "retired_at": stamp} for a in item["next_actions"])
        item["next_actions"] = []
    followup = item.get("followup")
    if followup and (followup.get("mode", "none") != "none" or followup.get("next_check_at")):
        item["followup"] = {**followup, "mode": "none", "next_check_at": ""}


# ---------------------------------------------------------------------------
# Applying updates


def empty_item(item_id: str, title: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "item_id": item_id,
        "title": title,
        "category": DEFAULT_CATEGORY,
        "purpose": "",
        "scope": "",
        "disposition": {"status": "active", "reason": "", "source": "", "decided_at": ""},
        "external_refs": [],
        "participants": [],
        "facts": [],
        "next_actions": [],
        "gaps": [],
        "events": [],
        "current_event_time": "",
        "current_event_keys": [],
        "revision": 0,
        "updated_at": "",
    }


def item_semantic_hash(item: dict[str, Any]) -> str:
    return stable_hash({k: v for k, v in item.items() if k not in {"revision", "updated_at"}})


ITEM_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")


class ItemsLock:
    """Serialise writers: a scheduled run and a conversation may write at the same time."""

    def __init__(self, data_dir: Path, timeout_seconds: int = 300):
        self.path = data_dir / "state" / "items.lock"
        self.timeout_seconds = timeout_seconds
        self.handle: Any = None

    def __enter__(self) -> "ItemsLock":
        import fcntl
        import time

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(self.path, "a+")
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            try:
                fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except BlockingIOError:
                if time.monotonic() > deadline:
                    self.handle.close()
                    raise LedgerError("items_locked", f"another writer holds {self.path}")
                time.sleep(0.5)

    def __exit__(self, *exc: Any) -> None:
        import fcntl

        fcntl.flock(self.handle, fcntl.LOCK_UN)
        self.handle.close()


def apply_one(data_dir: Path, incoming: Any) -> str | None:
    if not isinstance(incoming, dict):
        raise LedgerError("invalid_update", "each item update must be an object")
    item_id = require_str(incoming, "item_id")
    if not ITEM_ID_PATTERN.match(item_id):
        raise LedgerError("invalid_update", f"item_id {item_id!r} may only use letters, digits, '.', '_' and '-'")
    title = require_str(incoming, "title")
    item_path = data_dir / "items" / f"{item_id}.json"
    item_exists = item_path.exists()
    item = read_json(item_path) if item_exists else empty_item(item_id, title)
    before = item_semantic_hash(item)
    existing_keys = {str(e.get("event_key")) for e in item.get("events", []) if isinstance(e, dict)}

    explicit_current = (
        not item_exists
        or bool(incoming.get("force_current"))
        or bool({"disposition", "purpose", "scope", "category"} & set(incoming))
        or bool(incoming.get("next_actions")) or bool(incoming.get("replace_next_actions"))
        or bool(incoming.get("gaps")) or bool(incoming.get("replace_gaps"))
        or title != item.get("title")  # a rename is a current-state change and needs an authoritative event
    )
    current = explicit_current and can_update_current(item_exists, item, incoming, existing_keys)
    if current:
        item["title"] = title
        for scalar in ("purpose", "scope", "category"):
            if scalar in incoming:
                if not isinstance(incoming[scalar], str):
                    raise LedgerError("invalid_update", f"{scalar} must be a string for {item_id}")
                item[scalar] = incoming[scalar]
        if "disposition" in incoming:
            if not isinstance(incoming["disposition"], dict):
                raise LedgerError("invalid_update", f"disposition must be an object for {item_id}")
            item["disposition"] = {**item["disposition"], **incoming["disposition"]}
        item["current_event_time"] = iso_time(update_effective_time(incoming))
        item["current_event_keys"] = update_event_keys(incoming)

    for key, fields in (("external_refs", ("system", "id")), ("facts", ("key", "as_of"))):
        if not isinstance(incoming.get(key, []), list):
            raise LedgerError("invalid_update", f"{key} must be a list for {item_id}")
        item[key] = list(incoming.get(key, [])) if incoming.get(f"replace_{key}") else merge_unique(item[key], incoming.get(key, []), fields)
    for fact in incoming.get("facts", []):
        for ref in fact.get("evidence", []) if isinstance(fact, dict) else []:
            validate_evidence_ref(ref)
    people = list(incoming.get("participants", []))
    item["participants"] = merge_participants(people if incoming.get("replace_participants") else [*item["participants"], *people])
    if "next_actions" in incoming:
        validate_incoming_next_actions(item_id, incoming["next_actions"])
    if current:
        if incoming.get("replace_next_actions"):
            item["next_actions"] = list(incoming.get("next_actions", []))
        else:
            item["next_actions"] = merge_unique(item["next_actions"], incoming.get("next_actions", []), ("action", "owner", "due"))
        if incoming.get("replace_gaps"):
            item["gaps"] = list(incoming.get("gaps", []))
        else:
            item["gaps"] = merge_unique(item["gaps"], incoming.get("gaps", []), ("gap", "as_of"))
    for event in incoming.get("events", []):
        if not isinstance(event, dict):
            raise LedgerError("invalid_update", f"events must be objects for {item_id}")
        for key in ("event_key", "type", "observed_at", "summary"):
            require_str(event, key)
        if event["event_key"] not in existing_keys:
            item["events"].append(event)
            existing_keys.add(event["event_key"])
    if "followup" in incoming:
        apply_followup_setting(item, incoming["followup"], update_effective_time(incoming) if incoming.get("events") else now_local())
    if "followup_result" in incoming:
        apply_followup_result(item, incoming["followup_result"], existing_keys)
    if item["disposition"]["status"] in TERMINAL_DISPOSITIONS:
        if incoming.get("next_actions") and current:
            raise LedgerError("invalid_update", f"{item_id} is {item['disposition']['status']}; reopen it (active/waiting/observe) before adding next actions")
        if "mode" in (incoming.get("followup") or {}) and incoming["followup"]["mode"] != "none":
            raise LedgerError("invalid_update", f"{item_id} is {item['disposition']['status']}; followup.mode can only be none")
        retire_terminal_item(item, update_effective_time(incoming))
    check_mode_status(item, incoming)
    item["events"].sort(key=lambda e: (str(e.get("observed_at", "")), str(e.get("event_key", ""))))
    validate_item(item)
    if item_semantic_hash(item) == before:
        return None
    item["revision"] = int(item.get("revision") or 0) + 1
    item["updated_at"] = iso_now()
    write_json_atomic(item_path, item)
    return item_id


def apply_updates_command(args: argparse.Namespace) -> dict[str, Any]:
    updates = read_json(args.updates)
    if updates.get("schema_version") != 1:
        raise LedgerError("invalid_update", "updates schema_version must be 1")
    if not isinstance(updates.get("items"), list):
        raise LedgerError("invalid_update", "updates.items must be a list")
    with ItemsLock(args.data_dir):
        changed = [item_id for item_id in (apply_one(args.data_dir, u) for u in updates["items"]) if item_id]
        render_views(args.data_dir)
    return emit({"ok": True, "updated_at": iso_now(), "changed_items": changed, "changed_count": len(changed)})


# ---------------------------------------------------------------------------
# Views


def md_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def evidence_md(refs: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for ref in refs:
        target, note, ref_type = str(ref.get("ref", "")), ref.get("note", ""), ref.get("type", "")
        if target.startswith(("http://", "https://")):
            chunks.append(f"[{md_escape(note or ref_type or 'link')}]({target})")
        else:
            chunks.append(md_escape(f"{ref_type}:{target}" + (f" ({note})" if note else "")))
    return ", ".join(chunks)


def table(lines: list[str], headers: list[str], rows: list[list[Any]], raw: set[int] | frozenset[int] = frozenset()) -> None:
    """Append a Markdown table; columns listed in `raw` already hold Markdown (links) and are not escaped."""
    if not rows:
        lines.append("(none)")
        return
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "---|" * len(headers))
    for row in rows:
        lines.append("| " + " | ".join(str(c) if i in raw else md_escape(c) for i, c in enumerate(row)) + " |")


def render_item_md(item: dict[str, Any]) -> str:
    lines = [
        f"# {item['title']}",
        "",
        f"- Item ID: `{item['item_id']}`",
        f"- Status: `{item['disposition']['status']}`",
        f"- Category: `{item.get('category') or DEFAULT_CATEGORY}`",
        f"- Reason: {item['disposition'].get('reason', '')}",
        f"- Updated: {item.get('updated_at', '')}",
        "",
        "## Purpose", "", item.get("purpose") or "(empty)", "",
        "## Scope", "", item.get("scope") or "(empty)", "",
        "## External Refs", "",
    ]
    table(lines, ["System", "ID", "Note"], [[r.get("system"), r.get("id"), r.get("note")] for r in item["external_refs"]])
    lines += ["", "## Participants", ""]
    table(lines, ["Name", "Role In Item", "Note"], [[p.get("name"), p.get("role_in_item"), p.get("note")] for p in item["participants"]])
    lines += ["", "## Follow-up", ""]
    followup = item.get("followup") or {}
    if followup.get("mode", "none") != "none":
        for key in ("mode", "who", "how", "done_when", "waiting_on", "waiting_since", "due_at", "next_check_at",
                    "last_checked_at", "last_result", "no_change_streak", "blocked_streak", "allow", "chase_draft", "note"):
            if followup.get(key) not in (None, ""):
                lines.append(f"- {key}: {md_escape(followup[key])}")
    else:
        lines.append("(none)")
    lines += ["", "## Facts", ""]
    table(lines, ["Key", "As Of", "Summary", "Evidence"],
          [[f.get("key"), f.get("as_of"), f.get("summary"), evidence_md(f.get("evidence", []))] for f in item["facts"]], raw={3})
    lines += ["", "## Next Actions", ""]
    table(lines, ["Action", "Owner", "Due", "Preconditions"],
          [[a.get("action"), a.get("owner"), a.get("due"), a.get("preconditions")] for a in item["next_actions"]])
    lines += ["", "## Gaps", ""]
    table(lines, ["Gap", "As Of", "Impact"], [[g.get("gap"), g.get("as_of"), g.get("impact")] for g in item["gaps"]])
    lines += ["", "## Events", ""]
    table(lines, ["Observed At", "Type", "Summary", "Evidence"],
          [[e.get("observed_at"), e.get("type"), e.get("summary"), evidence_md(e.get("evidence", []))] for e in item["events"]], raw={3})
    return "\n".join(lines) + "\n"


def item_sort_key(item: dict[str, Any]) -> tuple[int, str]:
    order = {"active": 0, "waiting": 1, "observe": 2, "transferred": 3, "closed": 4}
    return (order.get(item["disposition"]["status"], 9), item.get("title", ""))


def read_items(data_dir: Path) -> list[dict[str, Any]]:
    items = []
    for path in sorted((data_dir / "items").glob("*.json")):
        item = read_json(path)
        validate_item(item)
        items.append(item)
    items.sort(key=item_sort_key)
    return items


def item_is_open(item: dict[str, Any]) -> bool:
    return item["disposition"]["status"] in OPEN_DISPOSITIONS


def render_views(data_dir: Path) -> dict[str, Any]:
    items = read_items(data_dir)
    now = now_local()
    views = data_dir / "views"
    (views / "items").mkdir(parents=True, exist_ok=True)
    wanted = {f"{item['item_id']}.md" for item in items}
    for stale in (views / "items").glob("*.md"):
        if stale.name not in wanted:
            stale.unlink()
    for item in items:
        write_text_atomic(views / "items" / f"{item['item_id']}.md", render_item_md(item))

    lines = ["# Ledger Index", "", f"Generated: {iso_time(now)}", ""]
    by_category: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        by_category.setdefault(str(item.get("category") or DEFAULT_CATEGORY), []).append(item)
    for category in sorted(by_category):
        lines += [f"## {category}", "", "| Status | Item | Next | Updated |", "|---|---|---|---|"]
        for item in by_category[category]:
            next_text = ""
            if item["next_actions"]:
                first = item["next_actions"][0]
                action = str(first.get("action", ""))
                action = action[:INDEX_NEXT_CHARS] + "…" if len(action) > INDEX_NEXT_CHARS else action
                more = f" +{len(item['next_actions']) - 1}" if len(item["next_actions"]) > 1 else ""
                next_text = f"{action} ({first.get('owner', '')}){more}"
            lines.append(f"| {item['disposition']['status']} | [{md_escape(item['title'])}](items/{item['item_id']}.md) | "
                         f"{md_escape(next_text)} | {md_escape(item.get('updated_at', ''))} |")
        lines.append("")
    counts: dict[str, int] = {}
    for item in items:
        counts[item["disposition"]["status"]] = counts.get(item["disposition"]["status"], 0) + 1
    lines += ["## Counts", ""] + [f"- `{status}`: {counts[status]}" for status in sorted(counts)]
    lint = lint_data(items, now)
    lines += ["", f"Ledger lint: {lint['total']} issue(s), see [lint.md](lint.md)."]
    write_text_atomic(views / "index.md", "\n".join(lines) + "\n")
    write_text_atomic(views / "lint.md", render_lint_md(lint))

    today = now.date().isoformat()
    daily = [f"# Changes on {today}", "", f"Generated: {iso_time(now)}", "", "| Item | Observed At | Type | Summary |", "|---|---|---|---|"]
    for item in items:
        for event in item["events"]:
            if str(event.get("observed_at", "")).startswith(today):
                daily.append(f"| [{md_escape(item['title'])}](../items/{item['item_id']}.md) | {md_escape(event.get('observed_at'))} | "
                             f"{md_escape(event.get('type'))} | {md_escape(event.get('summary'))} |")
    write_text_atomic(views / "daily" / f"{today}.md", "\n".join(daily) + "\n")
    people = render_people_views(data_dir, items)
    write_text_atomic(views / "followup.md", render_followup_md(followup_report_data(items, now)))
    return {"ok": True, "item_count": len(items), "people_count": people, "generated_at": iso_time(now)}


# ---------------------------------------------------------------------------
# People


def load_people(data_dir: Path) -> list[dict[str, Any]]:
    people = read_json(data_dir / "config" / "people.json", required=False).get("people")
    return [p for p in people if isinstance(p, dict) and p.get("name")] if isinstance(people, list) else []


def person_slug(name: str) -> str:
    return re.sub(r"[^\w-]+", "_", name).strip("_") or "unknown"


def name_in_owner(name: str, owner: Any) -> bool:
    return name in [p for p in OWNER_SEPARATOR.split(str(owner or "")) if p]


def user_names() -> set[str]:
    configured = str(load_config().get("user_name") or "")
    return SELF_NAMES | ({configured} if configured else set())


def render_people_views(data_dir: Path, items: list[dict[str, Any]]) -> int:
    """Per-person pages derived from items; the only hand-written part is config/people.json."""
    profiles = {str(p["name"]): p for p in load_people(data_dir)}
    me = user_names()
    involvement: dict[str, dict[str, Any]] = {}

    def bucket(name: str) -> dict[str, Any]:
        return involvement.setdefault(name, {"items": {}, "events": []})

    for item in items:
        for person in item["participants"]:
            if person["name"] not in me:
                bucket(person["name"])["items"][item["item_id"]] = {"item": item, "role": person.get("role_in_item", "")}
        for event in item["events"]:
            if event.get("type") == "followup_check":
                continue  # the checking agent is not a person in the user's life
            actor = event.get("actor")
            name = str(actor.get("name") or "") if isinstance(actor, dict) else ""
            if name and name not in me:
                entry = bucket(name)
                entry["items"].setdefault(item["item_id"], {"item": item, "role": ""})
                entry["events"].append((item, event))

    people_dir = data_dir / "views" / "people"
    people_dir.mkdir(parents=True, exist_ok=True)
    for old in people_dir.glob("*.md"):
        old.unlink()
    rows: list[list[Any]] = []
    for name, entry in sorted(involvement.items()):
        profile = profiles.get(name, {})
        last = max((str(e.get("observed_at") or "") for _, e in entry["events"]), default="")
        lines = [f"# {name}", "", f"- Relation: {profile.get('relation') or '(not recorded)'}"]
        if profile.get("notes"):
            lines.append(f"- Notes: {profile['notes']}")
        lines += [f"- Last recorded activity: {last or '(none)'}", "", "## Items", ""]
        they_owe: list[str] = []
        lines += ["| Status | Item | Their Role | Next Action | Next Owner |", "|---|---|---|---|---|"]
        for item_id, info in sorted(entry["items"].items(), key=lambda kv: item_sort_key(kv[1]["item"])):
            item = info["item"]
            first = item["next_actions"][0] if item["next_actions"] else {}
            lines.append(f"| {item['disposition']['status']} | [{md_escape(item['title'])}](../items/{item_id}.md) | "
                         f"{md_escape(info['role'])} | {md_escape(first.get('action'))} | {md_escape(first.get('owner'))} |")
            if item["disposition"]["status"] in TODO_DISPOSITIONS:
                for action in item["next_actions"]:
                    if name_in_owner(name, action.get("owner")):
                        they_owe.append(f"{item['title']}: {action.get('action')}" + (f" (due {action['due']})" if action.get("due") else ""))
                if (item.get("followup") or {}).get("waiting_on") == name:
                    they_owe.append(f"{item['title']}: waiting since {(item['followup'].get('waiting_since') or '?')}")
        lines += ["", "## Waiting On Them", ""] + ([f"- {md_escape(x)}" for x in they_owe] or ["(none)"])
        lines += ["", "## Recent Events", ""]
        recent = sorted(entry["events"], key=lambda pair: str(pair[1].get("observed_at") or ""), reverse=True)[:20]
        table(lines, ["Observed At", "Item", "Type", "Summary"],
              [[e.get("observed_at"), i["title"], e.get("type"), e.get("summary")] for i, e in recent])
        slug = person_slug(name)
        write_text_atomic(people_dir / f"{slug}.md", "\n".join(lines) + "\n")
        open_count = sum(1 for info in entry["items"].values() if info["item"]["disposition"]["status"] in TODO_DISPOSITIONS)
        rows.append([f"[{md_escape(name)}]({slug}.md)", profile.get("relation", ""), len(entry["items"]), open_count, len(they_owe), last])
    index = ["# People", "", "Derived from item participants and event actors; profiles come from config/people.json.", ""]
    table(index, ["Person", "Relation", "Items", "Open", "Waiting On Them", "Last Activity"], rows, raw={0})
    write_text_atomic(people_dir / "index.md", "\n".join(index) + "\n")
    return len(involvement)


# ---------------------------------------------------------------------------
# Follow-up reports


def followup_brief(item: dict[str, Any], now: datetime) -> dict[str, Any]:
    followup = item.get("followup") or {}
    brief: dict[str, Any] = {
        "item_id": item["item_id"],
        "title": item["title"],
        "status": item["disposition"]["status"],
        "category": item.get("category") or DEFAULT_CATEGORY,
        "idle_days": (now - latest_event_time(item)).days,
        "view": f"views/items/{item['item_id']}.md",
        "recent_events": [{"observed_at": e.get("observed_at"), "type": e.get("type"), "summary": e.get("summary")}
                          for e in item["events"][-3:]],
    }
    for key in sorted(FOLLOWUP_SETTABLE_FIELDS | FOLLOWUP_PROGRAM_FIELDS):
        if followup.get(key) not in (None, ""):
            brief[key] = followup[key]
    if followup.get("waiting_since"):
        brief["waiting_days"] = (now - parse_time_or_min(followup["waiting_since"])).days
    return brief


def followup_due_data(items: list[dict[str, Any]], now: datetime, limit: int, modes: list[str]) -> dict[str, Any]:
    due, missing = [], []
    for item in items:
        if not item_is_open(item):
            continue
        followup = item.get("followup")
        if not followup:
            missing.append({"item_id": item["item_id"], "title": item["title"], "status": item["disposition"]["status"],
                            "idle_days": (now - latest_event_time(item)).days})
        elif followup.get("mode") in modes and followup.get("next_check_at") and parse_time_or_min(followup["next_check_at"]) <= now:
            due.append(item)
    urgent_before = now + timedelta(days=2)
    far = datetime.max.replace(tzinfo=timezone.utc)

    def order(item: dict[str, Any]) -> tuple[int, datetime, datetime]:
        followup = item["followup"]
        due_at = parse_time_or_min(followup["due_at"]) if followup.get("due_at") else None
        return (0 if due_at and due_at <= urgent_before else 1, due_at or far, parse_time_or_min(followup["next_check_at"]))

    due.sort(key=order)
    missing.sort(key=lambda entry: -entry["idle_days"])
    return {"ok": True, "now": iso_time(now), "due_total": len(due), "due": [followup_brief(i, now) for i in due[:limit]],
            "missing_followup_total": len(missing), "missing_followup": missing[:limit]}


def followup_report_data(items: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    today = now.date().isoformat()
    checks: list[dict[str, Any]] = []
    counts = {result: 0 for result in sorted(VALID_FOLLOWUP_RESULTS)}
    decide, chase, urgent, escalated, stale_unfollowed = [], [], [], [], []
    open_count = todo_count = stale_count = covered = 0
    for item in items:
        for event in item["events"]:
            if event.get("type") == "followup_check" and str(event.get("observed_at", "")).startswith(today):
                result = str(event.get("followup_result", ""))
                counts[result] = counts.get(result, 0) + 1
                checks.append({"item_id": item["item_id"], "title": item["title"], "result": result, "summary": event.get("summary")})
        if not item_is_open(item):
            continue
        open_count += 1
        todo_count += item["disposition"]["status"] in TODO_DISPOSITIONS
        followup = item.get("followup") or {}
        mode = followup.get("mode", "none")
        idle = (now - latest_event_time(item)).days
        stale_count += idle >= FOLLOWUP_STALE_DAYS
        brief = followup_brief(item, now)
        if mode != "none":
            covered += 1
        elif idle >= FOLLOWUP_STALE_DAYS and not followup and item["disposition"]["status"] in TODO_DISPOSITIONS:
            stale_unfollowed.append(brief)
        if mode == "decide":
            decide.append(brief)
        if mode == "chase" and str(followup.get("last_checked_at", "")).startswith(today) and followup.get("last_result") in {"no_change", "blocked"}:
            chase.append(brief)
        if followup.get("due_at") and parse_time_or_min(followup["due_at"]) <= now + timedelta(days=FOLLOWUP_URGENT_DAYS):
            marker = f"followup-urgent:{item['item_id']}:{followup['due_at']}"
            urgent.append({**brief, "notified": any(e.get("event_key") == marker for e in item["events"]), "notify_event_key": marker})
        if int(followup.get("blocked_streak") or 0) >= FOLLOWUP_ESCALATE_AFTER_BLOCKED:
            escalated.append(brief)
    far = datetime.max.replace(tzinfo=timezone.utc)
    decide.sort(key=lambda b: (parse_time_or_min(b["due_at"]) if b.get("due_at") else far, -b["idle_days"]))
    stale_unfollowed.sort(key=lambda b: -b["idle_days"])
    lint = lint_data(items, now)
    return {
        "ok": True,
        "date": today,
        "now": iso_time(now),
        "metrics": {"open": open_count, "todo": todo_count, "observe": open_count - todo_count, "stale_open": stale_count,
                    "stale_days": FOLLOWUP_STALE_DAYS, "followup_covered": covered, "checks_today": len(checks), "results_today": counts},
        "checks_today": checks,
        "urgent": urgent,
        "decide_total": len(decide),
        "decide": decide,
        "chase_today": chase,
        "escalated": escalated,
        "stale_unfollowed": stale_unfollowed,
        "lint": {"total": lint["total"], "by_rule": lint["by_rule"]},
    }


def render_followup_md(report: dict[str, Any]) -> str:
    m = report["metrics"]
    lines = [
        "# Follow-up", "", f"Generated: {report['now']}", "",
        f"- To-do (active+waiting) {m['todo']}, observing {m['observe']}; with follow-up {m['followup_covered']}; "
        f"idle >= {m['stale_days']} days {m['stale_open']}",
        f"- Ledger lint: {report['lint']['total']} issue(s)" + (" (see lint.md)" if report["lint"]["total"] else ""),
        f"- Checked today {m['checks_today']}: " + ", ".join(f"{k} {v}" for k, v in m["results_today"].items()),
        "",
    ]
    sections = [
        ("Hard deadline near", report["urgent"], ["due_at", "mode", "who", "notified"]),
        (f"Waiting for the user's decision ({report['decide_total']})", report["decide"], ["due_at", "how", "idle_days"]),
        ("Suggested nudges today", report["chase_today"], ["waiting_on", "waiting_days", "chase_draft"]),
        ("Blocked repeatedly", report["escalated"], ["who", "blocked_streak", "how"]),
        ("Checked today", report["checks_today"], ["result", "summary"]),
        ("Idle with no follow-up", report["stale_unfollowed"], ["status", "idle_days"]),
    ]
    for title, rows, cols in sections:
        lines += [f"## {title}", ""]
        table(lines, ["Item", *cols], [[f"[{md_escape(r['title'])}](items/{r['item_id']}.md)", *[r.get(c, "") for c in cols]] for r in rows], raw={0})
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Lint

# rule -> (severity, label). error = the ledger says something false; warn = someone will be misled
# or nobody owns it; info = readability.
LINT_RULES = {
    "terminal_next_actions": ("error", "closed item still has next actions"),
    "terminal_followup": ("error", "closed item is still followed up"),
    "invalid_due": ("error", "due is not an ISO time"),
    "overdue_next_action": ("warn", "next action is past due"),
    "followup_overdue": ("warn", "follow-up check is overdue"),
    "decide_answered": ("warn", "the user decided after the question was set"),
    "mode_status_mismatch": ("warn", "follow-up mode does not match status"),
    "owner": ("warn", "owner is a placeholder"),
    "open_no_followup": ("warn", "open item has no follow-up"),
    "shared_ref": ("warn", "possible duplicate items"),
    "long_title": ("info", "title too long"),
    "long_action": ("info", "next action too long"),
}


def lint_data(items: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    """Consistency report over the whole ledger. Read-only: it never edits an item."""
    issues: list[dict[str, Any]] = []

    def add(item: dict[str, Any], rule: str, detail: str) -> None:
        issues.append({"item_id": item["item_id"], "title": item["title"], "status": item["disposition"]["status"],
                       "rule": rule, "severity": LINT_RULES[rule][0], "detail": detail})

    refs: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in items:
        status = item["disposition"]["status"]
        actions = [a for a in item["next_actions"] if isinstance(a, dict)]
        followup = item.get("followup") or {}
        mode = followup.get("mode", "none")
        if status in TERMINAL_DISPOSITIONS:
            if actions:
                add(item, "terminal_next_actions", f"{len(actions)}: {str(actions[0].get('action', ''))[:40]}")
            if mode != "none":
                add(item, "terminal_followup", f"mode={mode}")
        for action in actions:
            if action.get("due"):
                try:
                    due = parse_time(action["due"], "due")
                except LedgerError:
                    add(item, "invalid_due", str(action["due"]))
                else:
                    if status in TODO_DISPOSITIONS and due < now:
                        add(item, "overdue_next_action", f"due {action['due']}: {str(action.get('action', ''))[:40]}")
            if status in OPEN_DISPOSITIONS:
                problem = owner_problem(action.get("owner"))
                if problem:
                    add(item, "owner", problem)
                if len(str(action.get("action") or "")) > MAX_ACTION_CHARS:
                    add(item, "long_action", f"{len(str(action['action']))} chars")
        if status in OPEN_DISPOSITIONS:
            expected = FOLLOWUP_MODE_STATUS.get(mode)
            if expected and status != expected:
                add(item, "mode_status_mismatch", f"mode={mode} but status={status}; expected {expected}")
            if not followup:
                add(item, "open_no_followup", f"idle {(now - latest_event_time(item)).days} days")
            # Only check/chase are worked by the follow-up job; decide waits for the user and is
            # listed in the report instead, so a past next_check_at there is not a missed run.
            if mode in CHECKED_MODES and followup.get("next_check_at"):
                late = now - parse_time_or_min(followup["next_check_at"])
                if late > timedelta(days=FOLLOWUP_OVERDUE_GRACE_DAYS):
                    add(item, "followup_overdue", f"was due {followup['next_check_at']}, {late.days} days late")
            if mode == "decide" and followup.get("set_at"):
                asked = parse_time_or_min(followup["set_at"])
                answers = [e for e in item["events"] if e.get("type") == "user_decision" and event_effective_time(e) > asked]
                if answers:
                    add(item, "decide_answered", f"asked {followup['set_at']}, then: {str(answers[-1].get('summary', ''))[:40]}")
            for ref in item["external_refs"]:
                if isinstance(ref, dict) and ref.get("id"):
                    refs.setdefault((str(ref.get("system", "")), str(ref["id"])), []).append(item)
            if len(item["title"]) > MAX_TITLE_CHARS:
                add(item, "long_title", f"{len(item['title'])} chars")
    for (system, ref_id), owners in refs.items():
        if len(owners) > 1:
            ids = ", ".join(o["item_id"] for o in owners)
            for owner in owners:
                add(owner, "shared_ref", f"{system} {ref_id} also appears in {ids}")
    order = list(LINT_RULES)
    issues.sort(key=lambda i: (order.index(i["rule"]), i["item_id"]))
    by_rule = {rule: n for rule in order if (n := sum(1 for i in issues if i["rule"] == rule))}
    return {"ok": True, "now": iso_time(now), "total": len(issues), "by_rule": by_rule, "issues": issues}


def render_lint_md(report: dict[str, Any]) -> str:
    lines = ["# Ledger Lint", "", f"Generated: {report['now']}", "",
             f"{report['total']} issue(s). How to fix them: references/write.md, section \"Fixing lint issues\".", ""]
    for rule, count in report["by_rule"].items():
        severity, label = LINT_RULES[rule]
        lines += [f"## {label} ({rule}, {severity}, {count})", ""]
        table(lines, ["Item", "Status", "Detail"],
              [[f"[{md_escape(i['title'])}](items/{i['item_id']}.md)", i["status"], i["detail"]] for i in report["issues"] if i["rule"] == rule],
              raw={0})
        lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Install, scheduled-job bookkeeping and health


def config_path() -> Path:
    return Path(os.environ.get(CONFIG_ENV) or Path.home() / ".config" / "personal-ledger" / "config.json")


def load_config() -> dict[str, Any]:
    return read_json(config_path(), required=False)


def resolve_data_dir(args: argparse.Namespace) -> None:
    if not hasattr(args, "data_dir") or args.command == "init" or args.data_dir is not None:
        return
    configured = os.environ.get(DATA_ENV) or load_config().get("data_dir")
    if not configured:
        raise LedgerError("not_initialized", f"no data dir: run `{SHIM_NAME} init` or pass --data-dir")
    args.data_dir = Path(configured).expanduser()


def init_command(args: argparse.Namespace) -> dict[str, Any]:
    existing = load_config()
    data_dir = Path(args.data_dir or existing.get("data_dir") or Path.home() / ".local" / "share" / "personal-ledger").expanduser().resolve()
    if existing.get("data_dir") and Path(existing["data_dir"]).expanduser().resolve() != data_dir and not args.force:
        raise LedgerError("config_conflict", f"{config_path()} already points to {existing['data_dir']}; pass --force to switch")
    for sub in ("config", "items", "state", "views"):
        (data_dir / sub).mkdir(parents=True, exist_ok=True)
    os.chmod(data_dir, 0o700)
    created = []
    people = data_dir / "config" / "people.json"
    if not people.exists():
        write_json_atomic(people, {"schema_version": 1, "people": []})
        os.chmod(people, 0o600)
        created.append("config/people.json")
    config = {**existing, "data_dir": str(data_dir), "skill_dir": str(SKILL_DIR), "version": VERSION}
    if args.user_name:
        config["user_name"] = args.user_name
    write_json_atomic(config_path(), config)
    os.chmod(config_path(), 0o600)
    shim = None
    if not args.no_shim:
        shim = Path(args.shim_dir).expanduser() / SHIM_NAME
        # a non-default config location must survive in unattended runs that never see this shell's env
        export = f'export {CONFIG_ENV}="{config_path()}"\n' if os.environ.get(CONFIG_ENV) else ""
        write_text_atomic(shim, f'#!/bin/sh\n{export}exec python3 "{Path(__file__).resolve()}" "$@"\n')
        os.chmod(shim, 0o755)
    render_views(data_dir)
    path_dirs = [Path(p).expanduser() for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    return emit({
        "ok": True,
        "version": VERSION,
        "config": str(config_path()),
        "data_dir": str(data_dir),
        "user_name": config.get("user_name", ""),
        "created": created,
        "shim": str(shim) if shim else None,
        "shim_on_path": bool(shim and shim.parent in path_dirs),
        "next": "continue with references/setup.md: schedule the jobs if you can, then run doctor",
    })


def runs_log(data_dir: Path) -> Path:
    return data_dir / "state" / "runs.jsonl"


def append_run(data_dir: Path, record: dict[str, Any]) -> None:
    path = runs_log(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_runs(data_dir: Path) -> list[dict[str, Any]]:
    path = runs_log(data_dir)
    records = []
    for line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def job_status(data_dir: Path, now: datetime) -> dict[str, Any]:
    records = read_runs(data_dir)
    ends = {r["run"]: r for r in records if r.get("event") == "end" and r.get("run")}
    jobs: dict[str, Any] = {}
    for job in JOBS:
        starts = [r for r in records if r.get("job") == job and r.get("event") == "start"]
        finished = [ends[r["run"]] for r in starts if r["run"] in ends]
        ok = [r for r in finished if r.get("status") in {"ok", "skipped"}]
        last_end = ends.get(starts[-1]["run"], {}) if starts else {}
        last_ok = ok[-1]["at"] if ok else ""
        jobs[job] = {
            "runs": len(starts),
            "last_start": starts[-1]["at"] if starts else "",
            "last_status": last_end.get("status", "running") if starts else "",
            "last_note": last_end.get("note", ""),
            "last_ok": last_ok,
            "stale": not last_ok or now - parse_time_or_min(last_ok) > timedelta(hours=JOB_STALE_HOURS[job]),
            "stalled_runs": [r["run"] for r in starts if r["run"] not in ends
                             and now - parse_time_or_min(r["at"]) > timedelta(hours=RUN_STALLED_HOURS)][-3:],
            "today": {s: sum(1 for r in finished if r.get("status") == s and str(r.get("at", "")).startswith(now.date().isoformat()))
                      for s in ("ok", "skipped", "failed", "partial")},
        }
    return jobs


def gate_command(args: argparse.Namespace) -> dict[str, Any]:
    """First step of a scheduled job: record the start and say whether there is anything to do."""
    now = now_arg(args)
    run = f"{args.job}:{now.strftime('%Y%m%dT%H%M%S')}"
    result: dict[str, Any] = {"ok": True, "job": args.job, "run": run, "proceed": True}

    def stop(reason: str) -> dict[str, Any]:
        append_run(args.data_dir, {"run": run, "job": args.job, "event": "end", "at": iso_time(now), "status": "skipped", "note": reason})
        return emit({**result, "proceed": False, "reason": reason})

    append_run(args.data_dir, {"run": run, "job": args.job, "event": "start", "at": iso_time(now), "version": VERSION})
    if args.job == "followup":
        due = followup_due_data(read_items(args.data_dir), now, 8, CHECKED_MODES)
        result.update(due_total=due["due_total"], missing_followup_total=due["missing_followup_total"])
        if not due["due_total"] and not due["missing_followup_total"]:
            return stop("nothing due")
    elif args.job == "digest" and not args.force:
        today = now.date().isoformat()
        done = {r["run"] for r in read_runs(args.data_dir) if r.get("event") == "end" and r.get("status") == "ok"
                and str(r.get("run", "")).startswith("digest:") and str(r.get("at", "")).startswith(today)}
        if done:
            return stop("digest already delivered today")
    return emit(result)


def runlog_command(args: argparse.Namespace) -> dict[str, Any]:
    record = {"run": args.run, "job": args.run.split(":", 1)[0], "event": "end", "at": iso_time(now_arg(args)),
              "status": args.status, "note": args.note or ""}
    append_run(args.data_dir, record)
    return emit({"ok": True, **record})


def status_command(args: argparse.Namespace) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for item in read_items(args.data_dir):
        counts[item["disposition"]["status"]] = counts.get(item["disposition"]["status"], 0) + 1
    return emit({"ok": True, "version": VERSION, "skill_dir": str(SKILL_DIR), "config": str(config_path()),
                 "data_dir": str(args.data_dir), "user_name": load_config().get("user_name", ""), "items": counts,
                 "jobs": job_status(args.data_dir, now_arg(args))})


def doctor_command(args: argparse.Namespace) -> dict[str, Any]:
    now = now_arg(args)
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str, level: str = "error") -> None:
        checks.append({"check": name, "ok": ok, "level": level, "detail": detail})

    add("python", sys.version_info >= (3, 9), sys.version.split()[0])
    add("config", config_path().exists(), str(config_path()))
    data_dir = args.data_dir
    add("data_dir", data_dir.is_dir() and os.access(data_dir, os.W_OK), str(data_dir))
    if data_dir.is_dir():
        try:
            items = read_items(data_dir)
            add("items", True, f"{len(items)} items valid")
        except LedgerError as exc:
            add("items", False, f"{exc.code}: {exc}")
    shim = shutil.which(SHIM_NAME)
    add("shim_on_path", bool(shim), shim or f"{SHIM_NAME} not on PATH; call scripts/ledger.py directly", "warn")
    installed = (SKILL_DIR / "VERSION").read_text(encoding="utf-8").strip() if (SKILL_DIR / "VERSION").exists() else ""
    add("version", installed in ("", VERSION), f"program {VERSION}, skill VERSION {installed or '-'}")
    recorded = load_config().get("version", "")
    add("config_version", recorded in ("", VERSION), f"config written by {recorded or '-'}; rerun init after upgrading", "warn")
    if data_dir.is_dir():
        for job, info in job_status(data_dir, now).items():
            if not info["runs"]:
                add(f"job_{job}", True, "never ran (fine if you run it on request instead of on a schedule)", "info")
            else:
                detail = f"last ok {info['last_ok'] or 'never'}; last {info['last_status']} {info['last_note']}".strip()
                if info["stalled_runs"]:
                    detail += f"; stalled {info['stalled_runs']}"
                add(f"job_{job}", not info["stale"] and not info["stalled_runs"], detail, "warn")
    return emit({"ok": all(c["ok"] for c in checks if c["level"] == "error"), "version": VERSION, "checks": checks})


# ---------------------------------------------------------------------------
# CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=SHIM_NAME, description="Personal ledger: a local record of tracked matters, kept by agents")
    sub = parser.add_subparsers(dest="command", required=True)

    def command(name: str, func: Any, help_text: str, *, data: bool = True, now: bool = False) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_text)
        if data:
            p.add_argument("--data-dir", type=Path, default=None)
        if now:
            p.add_argument("--now", default="")
        p.set_defaults(func=func)
        return p

    p = command("apply-updates", apply_updates_command, "validate and apply an updates JSON file, then render views")
    p.add_argument("--updates", type=Path, required=True)
    command("render", lambda a: emit(render_views(a.data_dir)), "re-render views/ from items/")
    p = command("followup-due", lambda a: emit(followup_due_data(read_items(a.data_dir), now_arg(a), a.limit, a.modes)),
                "open items whose follow-up check is due, plus open items with no follow-up", now=True)
    p.add_argument("--limit", type=int, default=8)
    p.add_argument("--modes", nargs="+", default=CHECKED_MODES, choices=sorted(VALID_FOLLOWUP_MODES))
    command("followup-report", lambda a: emit(followup_report_data(read_items(a.data_dir), now_arg(a))),
            "today's checks, decisions waiting on the user, suggested nudges, deadlines", now=True)
    command("lint", lambda a: emit(lint_data(read_items(a.data_dir), now_arg(a))), "ledger consistency report (read-only)", now=True)
    p = command("gate", gate_command, "first step of a scheduled job: record start, say whether to proceed", now=True)
    p.add_argument("job", choices=JOBS)
    p.add_argument("--force", action="store_true", help="digest: run even if one was already delivered today")
    p = command("runlog", runlog_command, "last step of a scheduled job: record how it ended", now=True)
    p.add_argument("run", help="the `run` value printed by gate")
    p.add_argument("--status", choices=["ok", "partial", "failed"], required=True)
    p.add_argument("--note", default="")
    command("status", status_command, "paths, item counts and job history", now=True)
    command("doctor", doctor_command, "check the install and job health", now=True)
    p = command("init", init_command, f"create config, data dir and a `{SHIM_NAME}` shim (safe to rerun)")
    p.add_argument("--user-name", default="", help="how the user is named in owners, e.g. 'Alex'")
    p.add_argument("--shim-dir", default=str(Path.home() / ".local" / "bin"))
    p.add_argument("--no-shim", action="store_true")
    p.add_argument("--force", action="store_true", help="switch an existing config to another data dir")
    command("version", lambda a: emit({"ok": True, "version": VERSION, "skill_dir": str(SKILL_DIR)}), "print the version", data=False)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        resolve_data_dir(args)
        args.func(args)
    except LedgerError as exc:
        payload: dict[str, Any] = {"ok": False, "error": {"code": exc.code, "message": str(exc), "details": exc.details}}
        if exc.code in {"invalid_update", "invalid_item"}:
            payload["error"]["hint"] = "write rules: references/write.md; follow-up fields: references/follow-up.md. Fix and retry; do not bypass validation."
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
