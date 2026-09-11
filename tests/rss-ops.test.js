"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const root = path.resolve(__dirname, "..");
const freshRss = path.join(root, "skills", "rss-ops", "scripts", "freshrss_api.py");
const lookup = path.join(root, "skills", "rss-ops", "scripts", "rss_lookup.py");

function run(script, args) {
  return spawnSync("python3", [script, ...args], { encoding: "utf8" });
}

test("FreshRSS helper exposes the intended operations without reading config", () => {
  const result = run(freshRss, ["--help"]);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /list-feeds/);
  assert.match(result.stdout, /add-feed/);
  assert.match(result.stdout, /remove-feed/);
});

test("lookup helper joins a FreshRSS item with Sage AI metadata read-only", (t) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "rss-ops-test-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const freshDb = path.join(directory, "fresh.sqlite");
  const aiDb = path.join(directory, "ai.sqlite");
  const setup = spawnSync("python3", ["-c", String.raw`
import sqlite3, sys
fresh, ai = sys.argv[1:]
with sqlite3.connect(fresh) as db:
    db.executescript("""
      CREATE TABLE feed (id INTEGER PRIMARY KEY, name TEXT, url TEXT);
      CREATE TABLE entry (id INTEGER PRIMARY KEY, guid TEXT, title TEXT, link TEXT, date INTEGER, is_read INTEGER, is_favorite INTEGER, id_feed INTEGER);
      INSERT INTO feed VALUES (7, 'Example', 'https://example.com/feed');
      INSERT INTO entry VALUES (42, 'guid-42', 'Useful article', 'https://example.com/post/42', 123, 0, 1, 7);
    """)
with sqlite3.connect(ai) as db:
    db.executescript("""
      CREATE TABLE processed_entries (entry_id INTEGER, guid TEXT, link TEXT, priority TEXT, topics_json TEXT, labels_json TEXT, confidence REAL, reason TEXT, fact_or_opinion TEXT, model TEXT, cluster_id TEXT, author_key TEXT, summary TEXT, processed_at TEXT, dry_run INTEGER);
      INSERT INTO processed_entries VALUES (42, 'guid-42', 'https://example.com/post/42', 'high', '["agents"]', '["useful"]', 0.9, 'Relevant', 'fact', 'test-model', NULL, NULL, 'Summary', '2026-09-11', 0);
    """)
`, freshDb, aiDb], { encoding: "utf8" });
  assert.equal(setup.status, 0, setup.stderr);

  const result = run(lookup, [
    "--fragment", "post/42",
    "--freshrss-db", freshDb,
    "--rss-ai-db", aiDb,
    "--json",
  ]);
  assert.equal(result.status, 0, result.stderr);
  const rows = JSON.parse(result.stdout);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].id, 42);
  assert.equal(rows[0].ai.priority, "high");
  assert.deepEqual(rows[0].ai.topics, ["agents"]);
});
