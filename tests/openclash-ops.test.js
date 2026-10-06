"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const root = path.resolve(__dirname, "..");
const source = path.join(root, "skills", "openclash-ops", "scripts", "openclash-api.sh");

function renderHelper(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "openclash-ops-test-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const script = path.join(directory, "openclash-api.sh");
  const rendered = fs.readFileSync(source, "utf8")
    .replaceAll("@@OPENCLASH_API_URL@@", "http://192.0.2.1:9090")
    .replaceAll("@@OPENCLASH_KEYCHAIN_SERVICE@@", "test-openclash")
    .replaceAll("@@OPENCLASH_KEYCHAIN_ACCOUNT@@", "router:9090");
  fs.writeFileSync(script, rendered, { mode: 0o700 });
  return script;
}

test("OpenClash helper documents its read and guarded mutation commands", () => {
  const result = spawnSync("bash", [source, "--help"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /snapshot/);
  assert.match(result.stdout, /delay NODE URL \[TIMEOUT_MS\] \[EXPECTED_STATUS\]/);
  assert.match(result.stdout, /select --yes GROUP NODE/);
});

test("strict delay forwards the expected HTTP status", (t) => {
  const script = renderHelper(t);
  const directory = path.dirname(script);
  const mockCurl = path.join(directory, "curl");
  fs.writeFileSync(mockCurl, `#!/usr/bin/env bash
set -eu
args=$(printf '%s\\n' "$@")
case "$args" in
  *"expected=401"*) ;;
  *) echo "missing expected status" >&2; exit 93 ;;
esac
config=$(cat)
case "$config" in
  *"Authorization: Bearer test-secret"*) ;;
  *) echo "missing auth config" >&2; exit 92 ;;
esac
printf '{"delay":123}'
`, { mode: 0o700 });

  const result = spawnSync("bash", [
    script,
    "delay",
    "Node-A",
    "https://api.openai.com/v1/models",
    "7000",
    "401",
  ], {
    encoding: "utf8",
    env: {
      ...process.env,
      OPENCLASH_API_SECRET: "test-secret",
      PATH: `${directory}:${process.env.PATH}`,
    },
  });
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout), { delay: 123 });
});

test("selector mutation is rejected without the explicit guard", (t) => {
  const script = renderHelper(t);
  const result = spawnSync("bash", [script, "select", "ChatGPT", "JP-1"], {
    encoding: "utf8",
    env: { ...process.env, OPENCLASH_API_SECRET: "test-secret" },
  });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /requires --yes/);
});

test("secret is supplied through curl config stdin rather than argv", (t) => {
  const script = renderHelper(t);
  const directory = path.dirname(script);
  const mockCurl = path.join(directory, "curl");
  fs.writeFileSync(mockCurl, `#!/usr/bin/env bash
set -eu
for arg in "$@"; do
  if [ "$arg" = "test-secret" ] || [[ "$arg" == *"test-secret"* ]]; then
    echo "secret appeared in argv" >&2
    exit 91
  fi
done
config=$(cat)
case "$config" in
  *"Authorization: Bearer test-secret"*) ;;
  *) echo "missing auth config" >&2; exit 92 ;;
esac
printf '{"meta":true,"version":"mock-version"}'
`, { mode: 0o700 });

  const result = spawnSync("bash", [script, "version"], {
    encoding: "utf8",
    env: {
      ...process.env,
      OPENCLASH_API_SECRET: "test-secret",
      PATH: `${directory}:${process.env.PATH}`,
    },
  });
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout), { meta: true, version: "mock-version" });
  assert.doesNotMatch(result.stdout + result.stderr, /test-secret/);
});
