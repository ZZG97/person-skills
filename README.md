# Person Skills

Portable, public Skills for AI coding agents.

## Included Skills

### openclash-ops

Diagnose and safely operate an OpenClash/Mihomo transparent proxy. It separates
LAN, WAN, DNS/fake-IP, capture, rule, policy-group, and outbound-node failures;
uses the controller API without exposing its secret; and changes a selector only
after explicit user authorization.

The controller URL and macOS Keychain labels are rendered by Skill Kit. The API
secret remains in Keychain or a runtime environment variable and is never stored
in this repository or a rendered Skill.

### use-agent-chrome

Use persistent, agent-only Chromium profiles without touching a person's daily
browser. The Skill keeps login state in local browser profiles, exposes Chrome
DevTools Protocol only on loopback, and attaches native Playwright CLI sessions
for short-lived automation tasks.

Highlights:

- durable login state with one isolated profile per account;
- direct Playwright CLI attachment through loopback CDP;
- safe profile discovery, startup, creation, and cloning;
- Linux systemd-user and macOS LaunchAgent automation;
- `init` for a new machine's registry, and one optional registered extension
  loaded into selected profiles (all other extensions stay disabled there);
- no cookies, credentials, browser profiles, or machine paths in Git.

### rss-ops

Operate a local RSS stack without duplicating the agent-facing reading flow.
It manages FreshRSS subscriptions, diagnoses RSSHub routes, and looks up an
exact article across FreshRSS and Sage RSS AI metadata. Daily reading,
classification, and refresh remain the responsibility of the host-provided
`sage-rss` Skill.

Machine paths, usernames, and instance database locations are rendered by
Skill Kit from the ignored `skill-kit.local.json`; credentials and mutable
state stay outside Git.

### memory

A unified workflow for persistent context, journals and tracked matters. It assigns
each fact one authoritative owner: matter state lives in a local ledger, background
and knowledge live in reference documents, and journals record dated history.

Highlights:

- one writing entrypoint that searches existing owners before creating a record;
- preferences, system facts, project context, knowledge, daily and weekly journals;
- one record per matter: status, dated facts with evidence, next actions with
  owners, who is waited on, and a full event history;
- follow-up that does not let things sink: the agent checks what it can, the
  user is told whom to nudge and what to decide, and checks back off when
  nothing changes;
- a daily digest and a lint report that catches stale or contradictory records;
- works with any agent that can run a shell command; scheduling is optional and
  uses whatever the agent's environment provides;
- Python 3.9+ standard library only; data stays in a local directory and enters no
  repository the person has not chosen.

## Requirements

use-agent-chrome:

- Node.js 18 or newer
- Chrome or Chromium with CDP support
- playwright-cli available on PATH
- Linux or macOS for automatic profile creation and cloning

rss-ops:

- Python 3.10 or newer
- a local FreshRSS installation; RSSHub and a Sage RSS AI database are needed
  for their respective workflows

openclash-ops:

- Bash, curl, and jq; dig and nc are recommended diagnostics

memory:

- Python 3.9 or newer

## Install

Copy the Skill directory into the shared user-level Skill location:

~~~bash
mkdir -p ~/.agents/skills
cp -R skills/use-agent-chrome ~/.agents/skills/use-agent-chrome
cp -R skills/memory ~/.agents/skills/memory
~~~

`rss-ops` and `openclash-ops` contain machine-local placeholders; install them
with Skill Kit (`plan`/`apply --skills <name>`) instead of copying.

Agents that read another directory can link to it; for example Claude Code
reads `~/.claude/skills`:

~~~bash
ln -s ../.agents/skills ~/.claude/skills   # only if ~/.claude/skills does not exist yet
~~~

For a repository managed with skill-kit, validate it with:

~~~bash
python3 /path/to/skill_repo.py validate .
~~~

Then follow the
[new-machine initialization guide](skills/use-agent-chrome/references/initialization.md).
The [platform setup guide](skills/use-agent-chrome/references/platform-setup.md)
contains schema and manual recovery details. The example at
[examples/registry.example.json](examples/registry.example.json) contains only
placeholders and is safe to copy.

For RSS operations, follow the
[RSS initialization guide](skills/rss-ops/references/initialization.md). Prefer
Skill Kit installation over manually copying a rendered Skill.

For OpenClash operations, follow the
[OpenClash initialization guide](skills/openclash-ops/references/initialization.md).
Do not expose the controller API to the public Internet.

For memory, ask your agent to set it up using
[the setup guide](skills/memory/references/setup.md). Choose an Agent Home and data
directory, initialise the ledger, and configure scheduled work only if wanted.
The existing `pledger` command, `PLEDGER_CONFIG`, `PLEDGER_DATA_DIR` and ledger data
remain compatible with personal-ledger. When upgrading, migrate TODO/ongoing state
and retire the old writing Skill after verifying the new installation. Skill Kit
does not remove stale installations automatically.

## Safety

Keep the registry, Chromium profiles, service definitions, screenshots, and
login state outside this repository. Never expose CDP beyond loopback. A cloned
profile contains the same sensitive browser state as its source at the moment
of cloning.

Memory and its ledger hold private user and project notes. Keep their data
directory (default `~/.local/share/personal-ledger`) out of any repository and
backup service the person has not chosen.

## Development

~~~bash
npm test
npm run check
python3 /path/to/quick_validate.py skills/use-agent-chrome
python3 /path/to/quick_validate.py skills/rss-ops
python3 /path/to/quick_validate.py skills/openclash-ops
python3 /path/to/quick_validate.py skills/memory
python3 /path/to/skill_repo.py validate .
~~~

## License

MIT
