# New-machine initialization

`person-skills` is the canonical source. Agent Homes receive rendered copies;
do not hand-edit those copies.

## Prerequisites

1. Install and initialize FreshRSS, noting its loopback URL, host data directory,
   and local username.
2. Install RSSHub if route-backed sources are needed, keeping it loopback-only.
3. Initialize the Sage Agent Host instance and its `sage-rss` App before setting
   `RSS_AI_DB_PATH`.
4. Create a machine-local Zhihu inventory JSON (an empty JSON array is valid if
   Zhihu is not used) and an empty writable RSS operations state directory.
5. Clone `person-skills` and install Skill Kit.

## Machine-local values

Create ignored `skill-kit.local.json` at the repository root:

```json
{
  "FRESHRSS_BASE_URL": "http://127.0.0.1:1211",
  "FRESHRSS_DATA_DIR": "/absolute/path/to/freshrss/data",
  "FRESHRSS_USER": "local-user",
  "RSSHUB_BASE_URL": "http://127.0.0.1:1200",
  "RSSHUB_DEPLOY_DIR": "/absolute/path/to/rsshub",
  "RSS_AI_DB_PATH": "/absolute/path/to/instance/data/rss-ai.db",
  "ZHIHU_FOLLOWEES_FILE": "/absolute/path/to/zhihu-followees.json",
  "RSS_OPS_STATE_DIR": "/absolute/path/to/rss-ops-state"
}
```

Do not put secrets in this file. Runtime credentials remain in FreshRSS,
RSSHub's ignored configuration, and the isolated browser profile.

## Render and install

From the `person-skills` repository:

```bash
python3 /path/to/skill_repo.py validate .
python3 /path/to/skill_repo.py plan . --target /absolute/path/to/agent-home/.agents/skills
python3 /path/to/skill_repo.py apply . --target /absolute/path/to/agent-home/.agents/skills
```

Then verify:

```bash
python3 /absolute/path/to/agent-home/.agents/skills/rss-ops/scripts/freshrss_api.py check-greader --json
python3 /absolute/path/to/agent-home/.agents/skills/rss-ops/scripts/freshrss_api.py list-feeds --json
```

Install `sage-rss` through Sage Agent Host's App registration separately. It is
not part of this repository.
