"""Tests for memory's ledger engine (run: python3 -m unittest discover -s tests)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

LEDGER = Path(__file__).resolve().parents[1] / "skills" / "memory" / "scripts" / "ledger.py"


class LedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.env = {**os.environ, "HOME": str(self.home)}
        self.env.pop("PLEDGER_CONFIG", None)
        self.env.pop("PLEDGER_DATA_DIR", None)
        self.run_ok("init", "--user-name", "Alex", "--no-shim")
        self.data = self.home / ".local" / "share" / "personal-ledger"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(LEDGER), *args], env=self.env, capture_output=True, text=True)

    def run_ok(self, *args: str) -> dict:
        proc = self.run_cli(*args)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def apply(self, *items: dict) -> subprocess.CompletedProcess:
        path = self.home / f"update-{len(list(self.home.glob('update-*')))}.json"
        path.write_text(json.dumps({"schema_version": 1, "items": list(items)}), encoding="utf-8")
        return self.run_cli("apply-updates", "--updates", str(path))

    def apply_ok(self, *items: dict) -> dict:
        proc = self.apply(*items)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def item(self, item_id: str) -> dict:
        return json.loads((self.data / "items" / f"{item_id}.json").read_text(encoding="utf-8"))

    @staticmethod
    def event(key: str, at: str, kind: str = "user_report", summary: str = "said so") -> dict:
        return {"event_key": key, "type": kind, "observed_at": at, "summary": summary,
                "evidence": [{"type": "conversation", "ref": at, "note": ""}]}

    def new_item(self, **extra: object) -> dict:
        base = {"item_id": "pl-test", "title": "Renew passport",
                "disposition": {"status": "active", "reason": "started"},
                "events": [self.event("e1", "2026-10-01T10:00:00+08:00")]}
        return {**base, **extra}

    def test_apply_is_idempotent(self) -> None:
        self.assertEqual(self.apply_ok(self.new_item())["changed_count"], 1)
        self.assertEqual(self.apply_ok(self.new_item())["changed_count"], 0)
        self.assertEqual(self.item("pl-test")["revision"], 1)
        self.assertTrue((self.data / "views" / "items" / "pl-test.md").exists())

    def test_older_event_does_not_override_newer_decision(self) -> None:
        self.apply_ok(self.new_item())
        self.apply_ok({"item_id": "pl-test", "title": "Renew passport",
                       "disposition": {"status": "closed", "reason": "done"},
                       "events": [self.event("e3", "2026-10-03T10:00:00+08:00", "user_decision")]})
        self.apply_ok({"item_id": "pl-test", "title": "Renew passport",
                       "disposition": {"status": "active", "reason": "stale"},
                       "events": [self.event("e2", "2026-10-02T10:00:00+08:00")]})
        item = self.item("pl-test")
        self.assertEqual(item["disposition"]["status"], "closed")
        self.assertEqual(len(item["events"]), 3)  # the older event is still kept as history

    def test_disposition_without_event_is_ignored(self) -> None:
        self.apply_ok(self.new_item())
        self.apply_ok({"item_id": "pl-test", "title": "Renew passport", "disposition": {"status": "closed"}})
        self.assertEqual(self.item("pl-test")["disposition"]["status"], "active")

    def test_placeholder_owner_and_bad_due_are_rejected(self) -> None:
        bad_owner = self.apply(self.new_item(next_actions=[{"action": "call", "owner": "TBD"}]))
        self.assertNotEqual(bad_owner.returncode, 0)
        self.assertIn("placeholder", bad_owner.stderr)
        bad_due = self.apply(self.new_item(next_actions=[{"action": "call", "owner": "Alex", "due": "next week"}]))
        self.assertNotEqual(bad_due.returncode, 0)

    def test_closing_retires_actions_and_followup(self) -> None:
        self.apply_ok(self.new_item(next_actions=[{"action": "call", "owner": "Alex"}],
                                    followup={"mode": "check", "how": "look at the tracking page", "done_when": "status is shipped"}))
        self.apply_ok({"item_id": "pl-test", "title": "Renew passport", "disposition": {"status": "closed", "reason": "done"},
                       "events": [self.event("e2", "2026-10-02T10:00:00+08:00", "user_decision")]})
        item = self.item("pl-test")
        self.assertEqual(item["next_actions"], [])
        self.assertEqual(len(item["retired_next_actions"]), 1)
        self.assertEqual(item["followup"]["mode"], "none")

    def test_chase_requires_waiting_status(self) -> None:
        proc = self.apply(self.new_item(followup={"mode": "chase", "waiting_on": "Sam"}))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("waiting", proc.stderr)

    def test_followup_backoff_and_done(self) -> None:
        self.apply_ok(self.new_item(followup={"mode": "check", "how": "check the tracking page", "done_when": "delivered"}))
        self.apply_ok({"item_id": "pl-test", "title": "Renew passport",
                       "followup_result": {"result": "no_change", "summary": "still in transit", "checked_at": "2026-10-02T10:00:00+08:00"}})
        self.assertTrue(self.item("pl-test")["followup"]["next_check_at"].startswith("2026-10-04"))
        self.apply_ok({"item_id": "pl-test", "title": "Renew passport",
                       "followup_result": {"result": "done", "summary": "delivered", "checked_at": "2026-10-04T10:00:00+08:00"}})
        item = self.item("pl-test")
        self.assertEqual(item["disposition"]["status"], "closed")
        self.assertEqual(item["followup"]["mode"], "none")

    def test_waiting_decision_is_not_reported_as_missed_check(self) -> None:
        self.apply_ok(self.new_item(disposition={"status": "waiting", "reason": "user choosing"},
                                    followup={"mode": "decide", "how": "pick A or B", "next_check_at": "2026-09-01T10:00:00+08:00"}))
        lint = self.run_ok("lint", "--now", "2026-10-06T10:00:00+08:00")
        self.assertNotIn("followup_overdue", lint["by_rule"])
        report = self.run_ok("followup-report", "--now", "2026-10-06T10:00:00+08:00")
        self.assertEqual(report["decide_total"], 1)

    def test_missed_check_is_reported(self) -> None:
        self.apply_ok(self.new_item(followup={"mode": "check", "how": "look", "done_when": "seen",
                                              "next_check_at": "2026-10-01T10:00:00+08:00"}))
        lint = self.run_ok("lint", "--now", "2026-10-06T10:00:00+08:00")
        self.assertEqual(lint["by_rule"].get("followup_overdue"), 1)

    def test_explicitly_disabled_followup_is_not_revived_as_stale_work(self) -> None:
        self.apply_ok(self.new_item(disposition={"status": "observe", "reason": "user paused it"},
                                    followup={"mode": "none", "note": "Resume only when the user asks"}))
        self.apply_ok(self.new_item(item_id="pl-backlog", followup={"mode": "none", "note": "Candidate only"}))
        due = self.run_ok("followup-due", "--now", "2026-10-14T10:00:00+08:00")
        self.assertEqual(due["due_total"], 0)
        self.assertEqual(due["missing_followup_total"], 0)
        report = self.run_ok("followup-report", "--now", "2026-10-14T10:00:00+08:00")
        self.assertEqual(report["stale_unfollowed"], [])
        self.assertEqual(report["metrics"]["observe"], 1)

    def test_gate_followup_and_digest_once_a_day(self) -> None:
        self.assertFalse(self.run_ok("gate", "followup")["proceed"])
        self.apply_ok(self.new_item(followup={"mode": "check", "how": "look", "done_when": "seen",
                                              "next_check_at": "2026-10-01T10:00:00+08:00"}))
        gate = self.run_ok("gate", "followup", "--now", "2026-10-06T10:00:00+08:00")
        self.assertTrue(gate["proceed"])
        self.assertEqual(gate["due_total"], 1)
        digest = self.run_ok("gate", "digest", "--now", "2026-10-06T20:00:00+08:00")
        self.assertTrue(digest["proceed"])
        self.run_ok("runlog", digest["run"], "--status", "ok", "--now", "2026-10-06T20:05:00+08:00")
        self.assertFalse(self.run_ok("gate", "digest", "--now", "2026-10-06T21:00:00+08:00")["proceed"])
        status = self.run_ok("status", "--now", "2026-10-06T21:00:00+08:00")
        self.assertEqual(status["jobs"]["digest"]["last_status"], "skipped")
        self.assertEqual(status["jobs"]["digest"]["today"]["ok"], 1)
        self.assertTrue(self.run_ok("gate", "digest", "--now", "2026-10-07T20:00:00+08:00")["proceed"])

    def test_people_view_lists_who_we_wait_on(self) -> None:
        self.apply_ok(self.new_item(disposition={"status": "waiting", "reason": "photos"},
                                    participants=[{"name": "Photo shop", "role_in_item": "executor"}, {"name": "Alex"}],
                                    followup={"mode": "chase", "waiting_on": "Photo shop"}))
        people = (self.data / "views" / "people" / "index.md").read_text(encoding="utf-8")
        self.assertIn("Photo shop", people)
        self.assertNotIn("[Alex]", people)  # the user is not listed as someone else

    def test_doctor_on_fresh_install(self) -> None:
        doctor = self.run_ok("doctor")
        self.assertTrue(doctor["ok"])

    def test_upgrade_refreshes_shim_without_resetting_records(self) -> None:
        self.apply_ok(self.new_item())
        before = self.item("pl-test")
        config_path = self.home / ".config" / "personal-ledger" / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["skill_dir"] = "/retired/personal-ledger"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        shim_dir = self.home / "bin"
        result = self.run_ok("init", "--shim-dir", str(shim_dir))
        self.assertEqual(Path(result["data_dir"]), self.data.resolve())
        self.assertEqual(self.item("pl-test"), before)
        refreshed = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(refreshed["skill_dir"], str(LEDGER.parent.parent))
        shim = shim_dir / "pledger"
        self.assertIn(str(LEDGER), shim.read_text(encoding="utf-8"))
        proc = subprocess.run([str(shim), "status"], env=self.env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["items"], {"active": 1})

    def test_invalid_item_id_is_rejected(self) -> None:
        proc = self.apply(self.new_item(item_id="../escape"))
        self.assertNotEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
