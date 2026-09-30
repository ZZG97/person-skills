# Person Skills

Portable, public Skills for AI coding agents.

## Included Skill

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

## Requirements

- Node.js 18 or newer
- Chrome or Chromium with CDP support
- playwright-cli available on PATH
- Linux for automatic profile creation and cloning; macOS can use a manually
  registered LaunchAgent

## Install

Copy the Skill directory into the shared user-level Skill location:

~~~bash
mkdir -p ~/.agents/skills
cp -R skills/use-agent-chrome ~/.agents/skills/use-agent-chrome
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

## Safety

Keep the registry, Chromium profiles, service definitions, screenshots, and
login state outside this repository. Never expose CDP beyond loopback. A cloned
profile contains the same sensitive browser state as its source at the moment
of cloning.

## Development

~~~bash
npm test
python3 /path/to/quick_validate.py skills/use-agent-chrome
python3 /path/to/skill_repo.py validate .
~~~

## License

MIT
