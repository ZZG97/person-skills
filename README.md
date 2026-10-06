# Person Skills

Portable, public Skills for AI coding agents.

## Included Skills

### use-agent-chrome

Use persistent, agent-only Chromium profiles without touching a person's daily
browser. The Skill keeps login state in local browser profiles, exposes Chrome
DevTools Protocol only on loopback, and attaches native Playwright CLI sessions
for short-lived automation tasks.

Highlights:

- durable login state with one isolated profile per account;
- direct Playwright CLI attachment through loopback CDP;
- safe profile discovery, startup, creation, and cloning;
- Linux systemd-user automation and documented macOS setup;
- `init` for a new machine's registry, and one optional registered extension
  loaded into selected profiles (all other extensions stay disabled there);
- no cookies, credentials, browser profiles, or machine paths in Git.

### personal-ledger

A local ledger of the things a person wants kept track of — errands, plans,
appointments, things owed or awaited, decisions to make — maintained by the
agent from conversation. Tell the agent; it records the matter and keeps it
moving.

Highlights:

- one record per matter: status, dated facts with evidence, next actions with
  owners, who is waited on, and a full event history;
- follow-up that does not let things sink: the agent checks what it can, the
  user is told whom to nudge and what to decide, and checks back off when
  nothing changes;
- a daily digest and a lint report that catches stale or contradictory records;
- works with any agent that can run a shell command; scheduling is optional and
  uses whatever the agent's environment provides;
- Python 3.9+ standard library only; data stays in a local directory, never in Git.

## Requirements

use-agent-chrome:

- Node.js 18 or newer
- Chrome or Chromium with CDP support
- playwright-cli available on PATH
- Linux for automatic profile creation and cloning; macOS can use a manually
  registered LaunchAgent

personal-ledger:

- Python 3.9 or newer

## Install

Copy the Skill directory into the shared user-level Skill location:

~~~bash
mkdir -p ~/.agents/skills
cp -R skills/use-agent-chrome ~/.agents/skills/use-agent-chrome
cp -R skills/personal-ledger ~/.agents/skills/personal-ledger
~~~

Agents that read another directory can link to it; for example Claude Code
reads `~/.claude/skills`:

~~~bash
ln -s ../.agents/skills ~/.claude/skills   # only if ~/.claude/skills does not exist yet
~~~

For a repository managed with skill-kit, validate it with:

~~~bash
python3 /path/to/skill_repo.py validate .
~~~

Then follow
[the platform setup guide](skills/use-agent-chrome/references/platform-setup.md)
to create the local registry. The example at
[examples/registry.example.json](examples/registry.example.json) contains only
placeholders and is safe to copy.

For personal-ledger, ask your agent to set it up; it follows
[the setup guide](skills/personal-ledger/references/setup.md) (one `init`
command, then optional scheduling).

## Safety

Keep the registry, Chromium profiles, service definitions, screenshots, and
login state outside this repository. Never expose CDP beyond loopback. A cloned
profile contains the same sensitive browser state as its source at the moment
of cloning.

The personal ledger holds private notes about a person's life. Keep its data
directory (default `~/.local/share/personal-ledger`) out of any repository and
backup service the person has not chosen.

## Development

~~~bash
npm test
python3 /path/to/quick_validate.py skills/use-agent-chrome
python3 /path/to/quick_validate.py skills/personal-ledger
python3 /path/to/skill_repo.py validate .
~~~

## License

MIT
