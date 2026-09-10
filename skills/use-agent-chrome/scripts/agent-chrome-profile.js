#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

function defaultConfigPath() {
  if (process.env.AGENT_CHROME_CONFIG) return process.env.AGENT_CHROME_CONFIG;
  if (process.platform === "darwin") {
    return path.join(os.homedir(), "Library/Application Support/agent-chrome/registry.json");
  }
  const configRoot = process.env.XDG_CONFIG_HOME || path.join(os.homedir(), ".config");
  return path.join(configRoot, "agent-chrome/registry.json");
}

function parseArgs(argv) {
  const parsed = { _: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) {
      parsed._.push(token);
      continue;
    }
    const equals = token.indexOf("=");
    if (equals >= 0) {
      parsed[token.slice(2, equals)] = token.slice(equals + 1);
      continue;
    }
    const key = token.slice(2);
    const next = argv[index + 1];
    if (next && !next.startsWith("--")) {
      parsed[key] = next;
      index += 1;
    } else {
      parsed[key] = true;
    }
  }
  return parsed;
}

const args = parseArgs(process.argv.slice(2));
const command = args._[0];
const configPath = path.resolve(String(args.config || defaultConfigPath()));

function fail(message, code = 1) {
  process.stderr.write(`${message}\n`);
  process.exit(code);
}

function printHelp() {
  process.stdout.write(`Usage:
  agent-chrome-profile.js list [--json]
  agent-chrome-profile.js status --profile <name> [--json]
  agent-chrome-profile.js endpoint --profile <name>
  agent-chrome-profile.js start --profile <name>
  agent-chrome-profile.js attach --profile <name> --session <name>
  agent-chrome-profile.js add --profile <name> [options]
  agent-chrome-profile.js clone --from <name> --profile <new-name> [options]
  agent-chrome-profile.js describe --profile <name> [options]

Add/clone options:
  --label <label>             Human-readable account label
  --purpose <text>            What this profile should be used for
  --site <site>               Optional account metadata
  --role <role>               Optional account metadata
  --environment <name>        Optional account metadata
  --port <port>               Loopback CDP port (auto-selected by default)
  --user-data-dir <path>      New, dedicated profile directory
  --executable <path>         Chromium executable
  --start                     Start the new profile after registering it
  --dry-run                   Print the planned registry entry and service only

Clone option:
  --from <name>               Registered source profile; login state is copied

Describe options:
  --label <label>             Replace the human-readable label
  --purpose <text>            Replace the purpose shown by list
  --site <site>               Replace site metadata
  --role <role>               Replace role metadata
  --environment <name>        Replace environment metadata

Global option:
  --config <path>             Override the local profile registry
`);
}

function loadRegistry() {
  let registry;
  try {
    registry = JSON.parse(fs.readFileSync(configPath, "utf8"));
  } catch (error) {
    fail(`cannot read profile registry ${configPath}: ${error.message}`);
  }
  if (registry.version !== 1 || !registry.browsers || typeof registry.browsers !== "object") {
    fail(`invalid profile registry: ${configPath}`);
  }
  return registry;
}

function profileName() {
  const name = String(args.profile || "");
  if (!/^[a-zA-Z0-9_-]+$/.test(name)) {
    fail("--profile is required and may contain only letters, numbers, _ and -");
  }
  return name;
}

function getProfile(registry, name) {
  const profile = registry.browsers[name];
  if (!profile) fail(`unknown profile: ${name}`);
  if (!isLoopback(profile.backendHost) || !validPort(profile.backendPort)) {
    fail(`profile ${name} must use a valid loopback CDP endpoint`);
  }
  return profile;
}

function isLoopback(host) {
  return host === "127.0.0.1" || host === "localhost" || host === "::1";
}

function validPort(value) {
  return Number.isInteger(value) && value > 0 && value <= 65535;
}

function endpoint(profile) {
  const host = profile.backendHost === "::1" ? "[::1]" : profile.backendHost;
  return `http://${host}:${profile.backendPort}`;
}

function health(profile, timeout = 1500) {
  return new Promise((resolve) => {
    const request = http.get(
      {
        host: profile.backendHost,
        port: profile.backendPort,
        path: "/json/version",
        timeout,
      },
      (response) => {
        response.resume();
        resolve(response.statusCode === 200);
      }
    );
    request.on("timeout", () => request.destroy());
    request.on("error", () => resolve(false));
  });
}

function run(commandName, commandArgs, options = {}) {
  const result = spawnSync(commandName, commandArgs, {
    encoding: "utf8",
    stdio: options.capture ? "pipe" : "inherit",
  });
  if (result.error) throw new Error(`${commandName} failed: ${result.error.message}`);
  if (result.status !== 0) {
    const detail = options.capture ? String(result.stderr || result.stdout || "").trim() : "";
    throw new Error(`${commandName} exited with status ${result.status}${detail ? `: ${detail}` : ""}`);
  }
  return result;
}

function startService(profile) {
  const service = profile.service;
  if (!service || !service.manager || !service.name) {
    fail("profile has no supported local service; start its browser manually");
  }
  if (service.manager === "systemd-user") {
    run("systemctl", ["--user", "start", service.name]);
    return;
  }
  if (service.manager === "launchd") {
    run("launchctl", ["kickstart", "-k", `gui/${process.getuid()}/${service.name}`]);
    return;
  }
  fail(`unsupported service manager: ${service.manager}`);
}

function stopService(profile) {
  const service = profile.service;
  if (!service || !service.manager || !service.name) {
    fail("profile has no supported local service; stop its browser manually");
  }
  if (service.manager === "systemd-user") {
    run("systemctl", ["--user", "stop", service.name]);
    return;
  }
  if (service.manager === "launchd") {
    run("launchctl", ["kill", "SIGTERM", `gui/${process.getuid()}/${service.name}`]);
    return;
  }
  fail(`unsupported service manager: ${service.manager}`);
}

async function ensureStarted(profile) {
  if (await health(profile)) return;
  startService(profile);
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 250));
    if (await health(profile)) return;
  }
  fail(`profile did not expose CDP at ${endpoint(profile)} within 15 seconds`);
}

async function ensureStopped(profile) {
  if (!(await health(profile))) return;
  stopService(profile);
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 250));
    if (!(await health(profile))) return;
  }
  fail(`profile still exposes CDP at ${endpoint(profile)} after 15 seconds`);
}

function serviceActive(profile) {
  const service = profile.service;
  if (!service || !service.manager || !service.name) return null;
  if (service.manager === "systemd-user") {
    const result = spawnSync("systemctl", ["--user", "is-active", service.name], {
      encoding: "utf8",
      stdio: "pipe",
    });
    return result.status === 0;
  }
  if (service.manager === "launchd") {
    const result = spawnSync("launchctl", ["print", `gui/${process.getuid()}/${service.name}`], {
      encoding: "utf8",
      stdio: "pipe",
    });
    return result.status === 0;
  }
  return null;
}

function compactProfile(name, profile, online) {
  return {
    name,
    label: profile.label || name,
    purpose: profile.purpose || "",
    endpoint: endpoint(profile),
    profile: profile.profile,
    account: profile.account || null,
    clonedFrom: profile.clonedFrom || null,
    service: profile.service || null,
    online,
  };
}

function executableCandidates(template) {
  return [
    args.executable,
    template && template.executable,
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/google-chrome",
  ].filter(Boolean);
}

function chooseExecutable(template) {
  for (const candidate of executableCandidates(template)) {
    const resolved = path.resolve(String(candidate));
    try {
      fs.accessSync(resolved, fs.constants.X_OK);
      return resolved;
    } catch {
      // Try the next known browser location.
    }
  }
  fail("no Chromium executable found; pass --executable /absolute/path");
}

function portFree(port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.unref();
    server.once("error", () => resolve(false));
    server.listen({ host: "127.0.0.1", port }, () => server.close(() => resolve(true)));
  });
}

async function choosePort(registry) {
  const registered = new Set(Object.values(registry.browsers).map((item) => item.backendPort));
  if (args.port !== undefined) {
    const requested = Number(args.port);
    if (!validPort(requested)) fail("--port must be an integer from 1 to 65535");
    if (registered.has(requested)) fail(`CDP port is already registered: ${requested}`);
    if (!(await portFree(requested))) fail(`CDP port is already in use: ${requested}`);
    return requested;
  }
  for (let candidate = 19222; candidate <= 19999; candidate += 1) {
    if (!registered.has(candidate) && (await portFree(candidate))) return candidate;
  }
  fail("no free CDP port found in 19222-19999; pass --port explicitly");
}

function systemdQuote(value) {
  return `"${String(value).replace(/%/g, "%%").replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

function browserArguments(profile, executable, headless) {
  const launchArgs = [
    executable,
    "--remote-debugging-address=127.0.0.1",
    `--remote-debugging-port=${profile.backendPort}`,
    `--user-data-dir=${profile.profile}`,
  ];
  if (headless) launchArgs.push("--headless=new");
  launchArgs.push(
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-dev-shm-usage",
    "--window-size=1440,900",
    "about:blank"
  );
  return launchArgs;
}

function makeUnit(name, profile, executable) {
  const launchArgs = browserArguments(profile, executable, true);
  return `[Unit]
Description=Agent Chrome profile ${name}
After=network.target

[Service]
Type=simple
ExecStart=${launchArgs.map(systemdQuote).join(" ")}
Restart=on-failure
RestartSec=2
KillSignal=SIGTERM

[Install]
WantedBy=default.target
`;
}

function xmlEscape(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function makeLaunchAgent(name, profile, executable, stdoutPath, stderrPath) {
  const serviceName = `com.agent-chrome.${name}`;
  const argumentsXml = browserArguments(profile, executable, false)
    .map((value) => `      <string>${xmlEscape(value)}</string>`)
    .join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${xmlEscape(serviceName)}</string>
  <key>ProgramArguments</key>
  <array>
${argumentsXml}
  </array>
  <key>RunAtLoad</key>
  <false/>
  <key>KeepAlive</key>
  <false/>
  <key>ProcessType</key>
  <string>Interactive</string>
  <key>StandardOutPath</key>
  <string>${xmlEscape(stdoutPath)}</string>
  <key>StandardErrorPath</key>
  <string>${xmlEscape(stderrPath)}</string>
</dict>
</plist>
`;
}

function profileDataRoot() {
  if (process.platform === "darwin") {
    return path.join(os.homedir(), "Library", "Application Support", "agent-chrome", "profiles");
  }
  const dataRoot = process.env.XDG_DATA_HOME || path.join(os.homedir(), ".local", "share");
  return path.join(dataRoot, "agent-chrome", "profiles");
}

function makeServicePlan(name, profile, executable) {
  if (process.platform === "linux") {
    const serviceName = `agent-chrome-${name}.service`;
    return {
      manager: "systemd-user",
      name: serviceName,
      path: path.join(os.homedir(), ".config", "systemd", "user", serviceName),
      definition: makeUnit(name, profile, executable),
    };
  }
  if (process.platform === "darwin") {
    const serviceName = `com.agent-chrome.${name}`;
    const logRoot = path.join(os.homedir(), "Library", "Logs", "agent-chrome");
    return {
      manager: "launchd",
      name: serviceName,
      path: path.join(os.homedir(), "Library", "LaunchAgents", `${serviceName}.plist`),
      definition: makeLaunchAgent(
        name,
        profile,
        executable,
        path.join(logRoot, `${name}.out.log`),
        path.join(logRoot, `${name}.err.log`)
      ),
      logRoot,
    };
  }
  fail(`automatic profile creation is not supported on ${process.platform}`);
}

function installService(plan) {
  fs.mkdirSync(path.dirname(plan.path), { recursive: true, mode: 0o700 });
  if (plan.logRoot) fs.mkdirSync(plan.logRoot, { recursive: true, mode: 0o700 });
  fs.writeFileSync(plan.path, plan.definition, { mode: 0o644, flag: "wx" });
  if (plan.manager === "systemd-user") {
    run("systemctl", ["--user", "daemon-reload"]);
    return;
  }
  run("launchctl", ["bootstrap", `gui/${process.getuid()}`, plan.path], { capture: true });
}

function uninstallService(plan) {
  if (plan.manager === "launchd") {
    spawnSync("launchctl", ["bootout", `gui/${process.getuid()}/${plan.name}`], {
      encoding: "utf8",
      stdio: "pipe",
    });
  }
  fs.rmSync(plan.path, { force: true });
  if (plan.manager === "systemd-user") {
    run("systemctl", ["--user", "daemon-reload"]);
  }
}

function ensureNewProfileDirectory(profileDirectory) {
  if (!fs.existsSync(profileDirectory)) return;
  const stat = fs.statSync(profileDirectory);
  if (!stat.isDirectory()) fail(`profile path exists and is not a directory: ${profileDirectory}`);
  if (fs.readdirSync(profileDirectory).length > 0) {
    fail(`refusing to adopt non-empty unregistered profile directory: ${profileDirectory}`);
  }
}

function atomicWriteJson(filename, value) {
  const temporary = `${filename}.${process.pid}.tmp`;
  fs.mkdirSync(path.dirname(filename), { recursive: true, mode: 0o700 });
  fs.writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 });
  fs.renameSync(temporary, filename);
  fs.chmodSync(filename, 0o600);
}

async function addProfile(registry) {
  const name = profileName();
  if (registry.browsers[name]) fail(`profile already exists: ${name}`);

  const template = registry.browsers.default || Object.values(registry.browsers)[0];
  const browserExecutable = chooseExecutable(template);
  const backendPort = await choosePort(registry);
  const profileDirectory = path.resolve(
    String(args["user-data-dir"] || path.join(profileDataRoot(), name))
  );
  ensureNewProfileDirectory(profileDirectory);
  const profileDirectoryExisted = fs.existsSync(profileDirectory);

  const account = {};
  for (const key of ["site", "role", "environment"]) {
    if (args[key]) account[key] = String(args[key]);
  }
  const newProfile = {
    label: String(args.label || name),
    ...(args.purpose ? { purpose: String(args.purpose) } : {}),
    backendHost: "127.0.0.1",
    backendPort,
    profile: profileDirectory,
    executable: browserExecutable,
    ...(Object.keys(account).length ? { account } : {}),
  };
  const servicePlan = makeServicePlan(name, newProfile, browserExecutable);
  newProfile.service = { manager: servicePlan.manager, name: servicePlan.name };
  if (fs.existsSync(servicePlan.path)) fail(`service definition already exists: ${servicePlan.path}`);

  if (args["dry-run"]) {
    process.stdout.write(`${JSON.stringify({
      registryEntry: newProfile,
      servicePath: servicePlan.path,
      serviceDefinition: servicePlan.definition,
    }, null, 2)}\n`);
    return;
  }

  const originalRegistry = JSON.parse(JSON.stringify(registry));
  let serviceCreated = false;
  try {
    fs.mkdirSync(profileDirectory, { recursive: true, mode: 0o700 });
    installService(servicePlan);
    serviceCreated = true;
    registry.browsers[name] = newProfile;
    atomicWriteJson(configPath, registry);
  } catch (error) {
    if (serviceCreated || fs.existsSync(servicePlan.path)) uninstallService(servicePlan);
    if (!profileDirectoryExisted) fs.rmSync(profileDirectory, { recursive: true, force: true });
    atomicWriteJson(configPath, originalRegistry);
    throw error;
  }
  process.stdout.write(`Added profile ${name}\nCDP: ${endpoint(newProfile)}\nProfile: ${profileDirectory}\n`);
  if (args.start) {
    await ensureStarted(newProfile);
    process.stdout.write("Status: online\n");
  } else {
    process.stdout.write(`Start: node ${process.argv[1]} start --profile ${name}\n`);
  }
}

function shouldCopyProfileEntry(sourceRoot, sourcePath) {
  const relative = path.relative(sourceRoot, sourcePath);
  if (!relative) return true;
  const parts = relative.split(path.sep);
  if (parts.length !== 1) return true;
  return !new Set([
    "DevToolsActivePort",
    "SingletonCookie",
    "SingletonLock",
    "SingletonSocket",
  ]).has(parts[0]);
}

async function cloneProfile(registry) {
  const name = profileName();
  if (registry.browsers[name]) fail(`profile already exists: ${name}`);
  const sourceName = String(args.from || "");
  if (!/^[a-zA-Z0-9_-]+$/.test(sourceName)) {
    fail("--from is required and must name a registered source profile");
  }
  if (sourceName === name) fail("source and destination profiles must have different names");
  const source = getProfile(registry, sourceName);
  const sourceDirectory = path.resolve(String(source.profile || ""));
  if (!fs.statSync(sourceDirectory).isDirectory()) {
    fail(`source profile directory is missing: ${sourceDirectory}`);
  }

  const browserExecutable = chooseExecutable(source);
  const backendPort = await choosePort(registry);
  const profileDirectory = path.resolve(
    String(args["user-data-dir"] || path.join(profileDataRoot(), name))
  );
  if (fs.existsSync(profileDirectory)) {
    fail(`clone destination must not already exist: ${profileDirectory}`);
  }
  if (profileDirectory === sourceDirectory || profileDirectory.startsWith(`${sourceDirectory}${path.sep}`)) {
    fail("clone destination must not be the source profile or a child of it");
  }

  const account = { ...(source.account || {}) };
  for (const key of ["site", "role", "environment"]) {
    if (args[key]) account[key] = String(args[key]);
  }
  const newProfile = {
    label: String(args.label || `${source.label || sourceName} copy`),
    purpose: String(args.purpose || `Copy of ${sourceName}`),
    backendHost: "127.0.0.1",
    backendPort,
    profile: profileDirectory,
    executable: browserExecutable,
    ...(Object.keys(account).length ? { account } : {}),
    clonedFrom: sourceName,
  };
  const servicePlan = makeServicePlan(name, newProfile, browserExecutable);
  newProfile.service = { manager: servicePlan.manager, name: servicePlan.name };
  if (fs.existsSync(servicePlan.path)) fail(`service definition already exists: ${servicePlan.path}`);

  if (args["dry-run"]) {
    process.stdout.write(`${JSON.stringify({
      source: sourceName,
      registryEntry: newProfile,
      servicePath: servicePlan.path,
      serviceDefinition: servicePlan.definition,
    }, null, 2)}\n`);
    return;
  }

  const originalRegistry = JSON.parse(JSON.stringify(registry));
  const sourceWasOnline = await health(source);
  let destinationCreated = false;
  let serviceCreated = false;
  let registryChanged = false;
  let operationError = null;

  try {
    if (sourceWasOnline) {
      process.stdout.write(`Stopping ${sourceName} briefly for a consistent copy...\n`);
      await ensureStopped(source);
    }
    process.stdout.write(`Copying ${sourceDirectory} to ${profileDirectory}...\n`);
    destinationCreated = true;
    fs.cpSync(sourceDirectory, profileDirectory, {
      recursive: true,
      preserveTimestamps: true,
      errorOnExist: true,
      force: false,
      filter: (sourcePath) => shouldCopyProfileEntry(sourceDirectory, sourcePath),
    });
    installService(servicePlan);
    serviceCreated = true;
    registry.browsers[name] = newProfile;
    atomicWriteJson(configPath, registry);
    registryChanged = true;
  } catch (error) {
    operationError = error;
    try {
      if (registryChanged) atomicWriteJson(configPath, originalRegistry);
      if (serviceCreated || fs.existsSync(servicePlan.path)) uninstallService(servicePlan);
      if (destinationCreated) fs.rmSync(profileDirectory, { recursive: true, force: true });
    } catch (rollbackError) {
      operationError = new Error(`${error.message}; rollback also failed: ${rollbackError.message}`);
    }
  } finally {
    if (sourceWasOnline) {
      try {
        await ensureStarted(source);
        process.stdout.write(`${sourceName} restarted.\n`);
      } catch (restartError) {
        operationError = new Error(
          `${operationError ? `${operationError.message}; ` : ""}${sourceName} restart failed: ${restartError.message}`
        );
      }
    }
  }
  if (operationError) throw operationError;

  process.stdout.write(`Cloned ${sourceName} to ${name}\nCDP: ${endpoint(newProfile)}\nProfile: ${profileDirectory}\n`);
  if (args.start) {
    await ensureStarted(newProfile);
    process.stdout.write("Status: online\n");
  } else {
    process.stdout.write(`Start: node ${process.argv[1]} start --profile ${name}\n`);
  }
}

function describeProfile(registry) {
  const name = profileName();
  const profile = getProfile(registry, name);
  let changed = false;
  for (const key of ["label", "purpose"]) {
    if (args[key] !== undefined) {
      const value = String(args[key]).trim();
      if (!value) fail(`--${key} must not be empty`);
      profile[key] = value;
      changed = true;
    }
  }
  const account = { ...(profile.account || {}) };
  for (const key of ["site", "role", "environment"]) {
    if (args[key] !== undefined) {
      const value = String(args[key]).trim();
      if (!value) fail(`--${key} must not be empty`);
      account[key] = value;
      changed = true;
    }
  }
  if (!changed) fail("describe requires --label, --purpose, --site, --role, or --environment");
  if (Object.keys(account).length) profile.account = account;
  atomicWriteJson(configPath, registry);
  process.stdout.write(`${JSON.stringify(compactProfile(name, profile, null), null, 2)}\n`);
}

async function main() {
  if (!command || command === "help" || args.help) {
    printHelp();
    return;
  }
  const registry = loadRegistry();

  if (command === "list") {
    const rows = [];
    for (const [name, profile] of Object.entries(registry.browsers)) {
      rows.push(compactProfile(name, profile, await health(profile)));
    }
    if (args.json) {
      process.stdout.write(`${JSON.stringify(rows, null, 2)}\n`);
      return;
    }
    process.stdout.write("NAME\tSTATUS\tLABEL\tPURPOSE\tENDPOINT\tACCOUNT\n");
    for (const row of rows) {
      const metadata = row.account ? JSON.stringify(row.account) : "-";
      process.stdout.write(
        `${row.name}\t${row.online ? "online" : "offline"}\t${row.label}\t${row.purpose || "-"}\t${row.endpoint}\t${metadata}\n`
      );
    }
    return;
  }

  if (command === "add") {
    await addProfile(registry);
    return;
  }

  if (command === "clone") {
    await cloneProfile(registry);
    return;
  }

  if (command === "describe") {
    describeProfile(registry);
    return;
  }

  const name = profileName();
  const profile = getProfile(registry, name);
  if (command === "endpoint") {
    process.stdout.write(`${endpoint(profile)}\n`);
    return;
  }
  if (command === "status") {
    const online = await health(profile);
    const result = { ...compactProfile(name, profile, online), serviceActive: serviceActive(profile) };
    process.stdout.write(args.json ? `${JSON.stringify(result, null, 2)}\n` : `${online ? "online" : "offline"}\n`);
    return;
  }
  if (command === "start") {
    await ensureStarted(profile);
    process.stdout.write(`${name} is online at ${endpoint(profile)}\n`);
    return;
  }
  if (command === "attach") {
    const session = String(args.session || "");
    if (!/^[a-zA-Z0-9_-]+$/.test(session)) {
      fail("--session is required and may contain only letters, numbers, _ and -");
    }
    await ensureStarted(profile);
    run("playwright-cli", [`-s=${session}`, "attach", `--cdp=${endpoint(profile)}`]);
    return;
  }
  fail(`unknown command: ${command}`);
}

main().catch((error) => fail(error.stack || error.message));
