"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const net = require("node:net");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const repositoryRoot = path.resolve(__dirname, "..");
const script = path.join(
  repositoryRoot,
  "skills",
  "use-agent-chrome",
  "scripts",
  "agent-chrome-profile.js"
);

function run(args) {
  return spawnSync(process.execPath, [script, ...args], {
    encoding: "utf8",
  });
}

function temporaryDirectory(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "agent-chrome-test-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return directory;
}

function writeRegistry(directory, browsers) {
  const filename = path.join(directory, "registry.json");
  fs.writeFileSync(
    filename,
    JSON.stringify({ version: 1, browsers }, null, 2) + "\n",
    { mode: 0o600 }
  );
  return filename;
}

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen({ host: "127.0.0.1", port: 0 }, () => {
      const address = server.address();
      server.close(() => resolve(address.port));
    });
  });
}

test("prints help without requiring a registry", () => {
  const result = run(["--help"]);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /agent-chrome-profile\.js attach/);
});

test("rejects a non-loopback CDP endpoint", (t) => {
  const directory = temporaryDirectory(t);
  const config = writeRegistry(directory, {
    unsafe: {
      backendHost: "0.0.0.0",
      backendPort: 9222,
      profile: path.join(directory, "profile"),
    },
  });
  const result = run(["status", "--profile", "unsafe", "--config", config]);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /loopback CDP endpoint/);
});

test("lists registered profiles as JSON", (t) => {
  const directory = temporaryDirectory(t);
  const config = writeRegistry(directory, {
    default: {
      label: "Default",
      purpose: "General browsing",
      backendHost: "127.0.0.1",
      backendPort: 1,
      profile: path.join(directory, "profile"),
    },
  });
  const result = run(["list", "--json", "--config", config]);
  assert.equal(result.status, 0, result.stderr);
  const rows = JSON.parse(result.stdout);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].name, "default");
  assert.equal(rows[0].online, false);
  assert.equal(rows[0].endpoint, "http://127.0.0.1:1");
});

test("describe updates only non-secret metadata and secures the registry", (t) => {
  const directory = temporaryDirectory(t);
  const config = writeRegistry(directory, {
    default: {
      backendHost: "127.0.0.1",
      backendPort: 1,
      profile: path.join(directory, "profile"),
    },
  });
  const result = run([
    "describe",
    "--profile",
    "default",
    "--label",
    "Personal",
    "--purpose",
    "General browsing",
    "--site",
    "example.com",
    "--role",
    "personal",
    "--config",
    config,
  ]);
  assert.equal(result.status, 0, result.stderr);
  const registry = JSON.parse(fs.readFileSync(config, "utf8"));
  assert.equal(registry.browsers.default.label, "Personal");
  assert.equal(registry.browsers.default.account.site, "example.com");
  assert.equal(fs.statSync(config).mode & 0o777, 0o600);
});

test("add dry-run creates a portable plan without writing profile state", async (t) => {
  const directory = temporaryDirectory(t);
  const config = writeRegistry(directory, {});
  const profile = path.join(directory, "new-profile");
  const port = await freePort();
  const result = run([
    "add",
    "--profile",
    "personal",
    "--label",
    "Personal",
    "--purpose",
    "Persistent personal login",
    "--port",
    String(port),
    "--user-data-dir",
    profile,
    "--executable",
    process.execPath,
    "--dry-run",
    "--config",
    config,
  ]);
  assert.equal(result.status, 0, result.stderr);
  const plan = JSON.parse(result.stdout);
  assert.equal(plan.registryEntry.backendHost, "127.0.0.1");
  assert.equal(plan.registryEntry.backendPort, port);
  assert.equal(plan.registryEntry.profile, profile);
  assert.doesNotMatch(plan.serviceDefinition, /load-extension/);
  if (process.platform === "darwin") {
    assert.equal(plan.registryEntry.service.manager, "launchd");
    assert.match(plan.servicePath, /Library\/LaunchAgents\/com\.agent-chrome\.personal\.plist$/);
    assert.match(plan.serviceDefinition, /<key>ProgramArguments<\/key>/);
  } else {
    assert.equal(plan.registryEntry.service.manager, "systemd-user");
    assert.match(plan.servicePath, /agent-chrome-personal\.service$/);
  }
  assert.equal(fs.existsSync(profile), false);
  assert.deepEqual(JSON.parse(fs.readFileSync(config, "utf8")).browsers, {});
});
