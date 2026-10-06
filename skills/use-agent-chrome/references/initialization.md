# New-machine initialization

Use this checklist to install the Skill and create browser profiles on a new
machine. The Skill repository is portable. Registries, Chrome profiles, login
state, service definitions, and logs remain machine-local.

## 1. Install prerequisites

Install Node.js 18 or newer and Chrome or Chromium. Install the official
Playwright CLI and verify that it is on PATH:

~~~bash
npm install -g @playwright/cli@latest
playwright-cli --version
~~~

## 2. Install Skill Kit and this repository

Choose local checkout paths, then clone both repositories:

~~~bash
git clone https://github.com/ZZG97/skill-kit.git ~/.codex/skills/skill-kit
git clone https://github.com/ZZG97/person-skills.git ~/workspace/person-skills
~~~

Validate, review, and install the rendered Skill into the intended Agent Home.
Do not edit the installed copy later; update the canonical person-skills checkout
and apply it again.

~~~bash
python3 ~/.codex/skills/skill-kit/scripts/skill_repo.py validate \
  ~/workspace/person-skills
python3 ~/.codex/skills/skill-kit/scripts/skill_repo.py plan \
  ~/workspace/person-skills --target /absolute/agent-home/.agents/skills
python3 ~/.codex/skills/skill-kit/scripts/skill_repo.py apply \
  ~/workspace/person-skills --target /absolute/agent-home/.agents/skills
~~~

## 3. Give each Agent instance its own registry

Use one registry per Agent instance so profile discovery cannot accidentally
cross account boundaries. For example on macOS:

~~~bash
skill_root=/absolute/agent-home/.agents/skills/use-agent-chrome
export AGENT_CHROME_CONFIG="$HOME/Library/Application Support/agent-chrome/registries/my-agent.json"
node "$skill_root/scripts/agent-chrome-profile.js" init
~~~

On Linux, a suitable location is
`$HOME/.config/agent-chrome/registries/<instance>.json`. `init` creates the
registry with mode 0600 and refuses to overwrite an existing one. Never put a registry,
profile, account identifier, cookie, password, or token in Git.

For Sage Agent Host, set the registry path in that instance's environment and
allow the Host to pass it to the ACP Agent:

~~~dotenv
AGENT_CHROME_CONFIG='/absolute/path/to/registries/my-agent.json'
ACP_AGENT_ENV_ALLOWLIST='INITIAL_AGENT_MODE,AGENT_CHROME_CONFIG'
~~~

Restart that Host instance after changing its environment. Do not restart a
different Sage or Sage Agent Host process.

## 4. Create a new empty profile

Locate the installed Skill and review the generated service before applying it:

~~~bash
skill_root=/absolute/agent-home/.agents/skills/use-agent-chrome
node "$skill_root/scripts/agent-chrome-profile.js" add \
  --profile default \
  --label "Default agent browser" \
  --purpose "Persistent browser for this Agent instance" \
  --dry-run
~~~

Rerun without `--dry-run` to create the profile and local service. Add `--start`
to open it immediately. On macOS this creates a per-user LaunchAgent and a
visible Chrome window; on Linux it creates a headless systemd-user service.
Complete login interactively when needed.

Create a separate empty profile and registry for every person. Do not clone one
person's profile merely to save login time. Use `clone` only when the user
explicitly wants the same login state copied.

## 5. Verify attachment

~~~bash
node "$skill_root/scripts/agent-chrome-profile.js" list
node "$skill_root/scripts/agent-chrome-profile.js" status \
  --profile default --json
node "$skill_root/scripts/agent-chrome-profile.js" attach \
  --profile default --session setup_smoke
playwright-cli -s=setup_smoke tab-new https://example.com
playwright-cli -s=setup_smoke snapshot
playwright-cli -s=setup_smoke tab-close
playwright-cli -s=setup_smoke detach
~~~

Confirm that the browser remains online after detaching. For registry schema,
service details, manual registration, and recovery, continue with
[platform-setup.md](platform-setup.md).
