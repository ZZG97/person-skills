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
- Linux systemd-user and macOS LaunchAgent automation;
- no cookies, credentials, browser profiles, or machine paths in Git.

## Requirements

- Node.js 18 or newer
- Chrome or Chromium with CDP support
- playwright-cli available on PATH
- Linux or macOS for automatic profile creation and cloning

## Install

Copy the Skill directory into your agent's Skill location:

~~~bash
cp -R skills/use-agent-chrome ~/.codex/skills/use-agent-chrome
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
