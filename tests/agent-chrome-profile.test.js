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
  assert.doesNotMatch(plan.unit, /load-extension/);
  assert.equal(fs.existsSync(profile), false);
  assert.deepEqual(JSON.parse(fs.readFileSync(config, "utf8")).browsers, {});
});

test("init creates an empty private registry and refuses to overwrite it", (t) => {
  const directory = temporaryDirectory(t);
  const config = path.join(directory, "nested", "registry.json");
  const first = run(["init", "--config", config]);
  assert.equal(first.status, 0, first.stderr);
  assert.deepEqual(JSON.parse(fs.readFileSync(config, "utf8")), { version: 1, browsers: {} });
  assert.equal(fs.statSync(config).mode & 0o777, 0o600);
  const second = run(["init", "--config", config]);
  assert.notEqual(second.status, 0);
  assert.match(second.stderr, /refusing to overwrite/);
});

function writeExtension(directory) {
  const extension = path.join(directory, "extension");
  fs.mkdirSync(extension);
  fs.writeFileSync(path.join(extension, "manifest.json"), JSON.stringify({ manifest_version: 3, name: "test", version: "1" }));
  return extension;
}

function registryWithExtension(directory, extension, browsers = {}) {
  const filename = path.join(directory, "registry.json");
  fs.writeFileSync(filename, JSON.stringify({
    version: 1,
    browsers,
    extension: { directory: extension, id: "abc", popup: "chrome-extension://abc/popup.html" },
  }) + "\n", { mode: 0o600 });
  return filename;
}

async function addPlan(directory, config, extra = []) {
  const port = await freePort();
  return run([
    "add", "--profile", "personal", "--port", String(port),
    "--user-data-dir", path.join(directory, "new-profile"),
    "--executable", process.execPath, "--dry-run", "--config", config, ...extra,
  ]);
}

test("add loads only the registered extension, unless opted out", async (t) => {
  const directory = temporaryDirectory(t);
  const extension = writeExtension(directory);
  const config = registryWithExtension(directory, extension);
  const withExtension = await addPlan(directory, config);
  assert.equal(withExtension.status, 0, withExtension.stderr);
  const plan = JSON.parse(withExtension.stdout);
  assert.equal(plan.registryEntry.extension, true);
  assert.match(plan.unit, new RegExp(`--load-extension=${extension}`));
  assert.match(plan.unit, new RegExp(`--disable-extensions-except=${extension}`));
  const without = await addPlan(directory, config, ["--without-extension"]);
  assert.equal(without.status, 0, without.stderr);
  const bare = JSON.parse(without.stdout);
  assert.equal(bare.registryEntry.extension, false);
  assert.doesNotMatch(bare.unit, /load-extension/);
});

test("add fails when the registered extension directory is missing", async (t) => {
  const directory = temporaryDirectory(t);
  const config = registryWithExtension(directory, path.join(directory, "gone"));
  const result = await addPlan(directory, config);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /registered extension is missing/);
});

test("extension-url prints the registered popup page", (t) => {
  const directory = temporaryDirectory(t);
  const config = registryWithExtension(directory, writeExtension(directory));
  const result = run(["extension-url", "--config", config]);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout.trim(), "chrome-extension://abc/popup.html");
  const none = run(["extension-url", "--config", writeRegistry(directory, {})]);
  assert.notEqual(none.status, 0);
  assert.match(none.stderr, /no extension popup/);
});
