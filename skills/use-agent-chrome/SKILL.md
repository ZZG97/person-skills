---
name: use-agent-chrome
description: Select, describe, create, clone, start, and safely attach Playwright CLI to persistent agent-only Chromium profiles. Use for browser automation that needs durable login state, multiple isolated accounts, QR or verification-code login, a registered local browser service, or direct loopback CDP access without touching a person's daily browser.
---

# Use Agent Chrome

Use native Playwright CLI commands for webpage operations. This Skill adds a
small local profile layer that discovers registered accounts, starts the chosen
persistent Chromium, and attaches a named Playwright session to its loopback
Chrome DevTools Protocol endpoint.

Keep machine paths, profiles, login state, and account metadata in the local
registry, never in the portable Skill repository.

## Requirements

Require Node.js 18 or newer and the official `@playwright/cli` package on PATH
as `playwright-cli`. If it is absent, report that fact and ask before installing
it.

Discover the registry in this order:

1. AGENT_CHROME_CONFIG
2. Linux: XDG_CONFIG_HOME/agent-chrome/registry.json, falling back to
   ~/.config/agent-chrome/registry.json
3. macOS: ~/Library/Application Support/agent-chrome/registry.json

On a new machine, or when the registry or browser service is missing, read
[initialization.md](references/initialization.md) completely before changing
the machine. Read [platform-setup.md](references/platform-setup.md) as well when
manual registration, schema details, or recovery is needed.

## Default workflow

1. Locate this Skill's root and list the registered profiles:

   ~~~bash
   skill_root=/absolute/path/to/use-agent-chrome
   node "$skill_root/scripts/agent-chrome-profile.js" list
   ~~~

2. Choose the profile whose purpose and account metadata match the task. Use
   default only when the user has not requested another account.

3. Create a stable, task-specific Playwright session and attach once:

   ~~~bash
   session=browser_<task-id>
   node "$skill_root/scripts/agent-chrome-profile.js" attach \
     --profile default --session "$session"
   ~~~

4. Use native Playwright CLI commands. Create a task-specific tab first and use
   snapshots and element references for interaction:

   ~~~bash
   playwright-cli -s="$session" tab-new https://example.com
   playwright-cli -s="$session" snapshot
   playwright-cli -s="$session" click e12
   playwright-cli -s="$session" fill e19 "text"
   playwright-cli -s="$session" screenshot
   ~~~

5. Verify the URL and title before sensitive interaction. Close only the tab
   created for this task, then detach without stopping Chromium:

   ~~~bash
   playwright-cli -s="$session" tab-close
   playwright-cli -s="$session" detach
   ~~~

Follow the installed playwright-cli Skill for navigation, snapshots, refs,
uploads, tracing, network inspection, and other page operations. Do not invent
a second browser command vocabulary.

## Profile management

Treat one registered profile as one durable account container: one user-data
directory, one loopback CDP port, and one local browser service. A Playwright
session is a short-lived attachment, not an account container.

Inspect or describe profiles:

~~~bash
node "$skill_root/scripts/agent-chrome-profile.js" status \
  --profile default --json
node "$skill_root/scripts/agent-chrome-profile.js" describe \
  --profile default \
  --label "Default profile" \
  --purpose "General browsing with persistent login state"
~~~

On Linux or macOS, create an empty profile with a generated user service. Review
the plan before applying it:

~~~bash
node "$skill_root/scripts/agent-chrome-profile.js" add \
  --profile account_b \
  --label "Account B" \
  --purpose "Shopping test account" \
  --site "example.com" \
  --role "buyer" \
  --dry-run
~~~

When the user explicitly requests the current login state to be copied, clone a
registered profile. Always review a dry run first because the source browser is
briefly stopped for a consistent copy:

~~~bash
node "$skill_root/scripts/agent-chrome-profile.js" clone \
  --from default \
  --profile account_b \
  --label "Account B" \
  --purpose "Second isolated account" \
  --dry-run
~~~

After creating a profile, attach to it and open the product login page. Ask the
user to complete QR, passkey, verification-code, or other human authentication
when required. Verify the resulting account identity before using it.

## Concurrency

Use a unique Playwright session name and task-specific tab. Prefer separate
registered profiles when two agents need browsers at the same time. If they
must share one profile, coordinate explicitly: separate CLI sessions do not
isolate tabs, extension state, or account-wide mutations.

## Safety boundaries

- Attach only to profiles in the local registry; never attach to daily Chrome.
- Accept only loopback CDP endpoints.
- Never inspect cookies, passwords, history, payment data, or unrelated tabs.
- Never commit the registry, profiles, login state, screenshots, or service
  files.
- Do not adopt a non-empty unregistered profile directory.
- Do not reuse one user-data directory from two browser processes.
- Do not submit forms or mutate external data without the confirmation required
  by the active task.
- Never close or kill the persistent browser unless the user explicitly asks.
- Treat a cloned profile as equally sensitive as its source.

## Recovery

- Run list, then status for the selected profile.
- Run start when the profile is offline.
- Verify that the endpoint command returns a loopback URL and that its
  /json/version endpoint responds.
- If the Playwright session is stale, detach that named session and attach it
  again. Do not delete or routinely restart the persistent profile.
