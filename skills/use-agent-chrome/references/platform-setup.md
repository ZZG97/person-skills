# Platform setup

Read this file for registry schema, service details, manual registration, or
recovery. For the complete installation sequence, start with
[initialization.md](initialization.md).

## Portable and local boundaries

Share the Skill and its Node script. Keep these items machine-local and
untracked:

- the profile registry;
- Chromium profiles and login state;
- browser binaries and installation paths;
- systemd units or LaunchAgent property lists containing local paths;
- screenshots, traces, logs, and temporary runtime state.

Never place credentials, cookies, access tokens, copied profiles, or real
account identifiers in the Skill repository.

## Requirements

- Node.js 18 or newer;
- playwright-cli on PATH;
- Chrome or Chromium with CDP support;
- one unique user-data directory, loopback CDP port, and local service per
  account.

Use these default registry locations:

- Linux: XDG_CONFIG_HOME/agent-chrome/registry.json, falling back to
  ~/.config/agent-chrome/registry.json;
- macOS: ~/Library/Application Support/agent-chrome/registry.json;
- override: AGENT_CHROME_CONFIG=/absolute/path/registry.json.

## Registry schema

Create an empty registry on a new machine, then add profiles with the helper
(it refuses to overwrite an existing registry):

~~~bash
node /absolute/path/to/use-agent-chrome/scripts/agent-chrome-profile.js init
~~~

Or start from the repository's examples/registry.example.json. The schema is:

~~~json
{
  "version": 1,
  "browsers": {
    "default": {
      "label": "Default agent browser",
      "purpose": "General browsing with persistent login state",
      "backendHost": "127.0.0.1",
      "backendPort": 19222,
      "profile": "/absolute/path/to/an-agent-only-profile",
      "executable": "/absolute/path/to/chromium",
      "service": {
        "manager": "systemd-user",
        "name": "agent-chrome-default.service"
      },
      "account": {
        "site": "example.com",
        "role": "personal",
        "environment": "production"
      },
      "clonedFrom": "another-profile",
      "extension": true
    }
  },
  "extension": {
    "directory": "/absolute/path/to/unpacked-extension",
    "id": "extension-id",
    "popup": "chrome-extension://extension-id/popup.html"
  }
}
~~~

purpose, account, clonedFrom, and the per-profile extension flag are optional
non-secret metadata. Omit the top-level extension object when unused; see
"Registered extension" in SKILL.md. Keep
usernames, email addresses, passwords, cookies, and access tokens out of the
registry. Restrict the registry to the current user.

## Linux service integration

Prefer the bundled helper:

~~~bash
node scripts/agent-chrome-profile.js add \
  --profile account_b \
  --label "Account B" \
  --purpose "Second isolated browser account" \
  --site "example.com" \
  --role "personal" \
  --dry-run
~~~

Review the printed plan, rerun without --dry-run, and optionally add --start.
The helper writes a user-level systemd service, updates the registry atomically,
and creates a new empty profile. It does not enable the service at boot. It
refuses to overwrite an existing unit, reuse a registered port, or adopt a
non-empty unregistered profile directory.

For manual setup, launch every browser with:

- --remote-debugging-address=127.0.0.1
- a unique --remote-debugging-port
- a unique --user-data-dir
- the headless or window flags appropriate to the machine

Do not expose CDP on a LAN address. Do not start two browser processes against
the same user-data directory.

To inherit an existing registered profile's login state, use clone --from
<name>. The helper briefly stops and restarts an online source, excludes
Chromium singleton lock files, and refuses an existing destination. Prefer add
when an empty account is intended.

## macOS service integration

The bundled helper supports `add` and `clone` on macOS. It creates one per-user
LaunchAgent under `~/Library/LaunchAgents` for each profile, stores logs under
`~/Library/Logs/agent-chrome`, and records the service like this:

~~~json
{
  "manager": "launchd",
  "name": "com.agent-chrome.default"
}
~~~

Review `--dry-run` before applying. The helper bootstraps a new property list
with launchctl and uses launchctl kickstart for later starts. It does not start
the browser at login. Common browser executables include:

- /Applications/Google Chrome.app/Contents/MacOS/Google Chrome
- /Applications/Chromium.app/Contents/MacOS/Chromium

Verify the actual browser path instead of assuming a channel.

## Verification

1. List profiles and confirm the intended account container is present.
2. Check its status and start it if necessary.
3. Confirm the endpoint is loopback and /json/version responds.
4. Attach a unique Playwright session.
5. Create a disposable tab, navigate, snapshot, close that tab, and detach.
6. Confirm that the persistent browser remains running after detachment.
