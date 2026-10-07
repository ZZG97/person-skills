# Setup, scheduling and repair (for the agent)

Tell the user what each step did.

## Home and existing installation

Resolve the user's Agent Home before choosing data paths. Reuse its memory router,
information architecture and existing reference/journal locations. For a new Home,
agree on the root and create files only when actual information needs a home.
There is no required messaging service, history connector or scheduler.

When replacing personal-ledger, back up both old Skill directories, install `memory`,
then rerun its `scripts/ledger.py init` against the existing config. This refreshes
the `pledger` shim and `skill_dir` without moving or resetting items. Inspect existing
scheduled prompts for old Skill paths and update only the affected references.
Move the retired Skill outside every discovery directory after the new entrypoint
works; leave its data in place. Keep one installed memory-writing Skill.

## 1. Initialise

Requires `python3` 3.9 or newer; nothing else.

```
python3 <this Skill>/scripts/ledger.py init --user-name <name> --data-dir <chosen ledger directory>
```

It creates the data directory (default `~/.local/share/personal-ledger`, mode 700), an
empty `config/people.json`, the config `~/.config/personal-ledger/config.json`, and the
shim `~/.local/bin/pledger`. It is safe to rerun and never overwrites data.

- Another data directory: `--data-dir <path>`. Switching an existing config needs
  `--force`; use it only for a data move the user authorized, after preserving data.
- To back the ledger up with a private repository the user already keeps (for example
  the agent's own home directory), put the data directory inside it and ignore its
  `views/` (rendered) and `state/` (write lock and job log); `items/` and `config/` are
  the data. Never put it in a shared or public repository.
- Another shim directory: `--shim-dir <dir>`. If the output says `shim_on_path=false`,
  ask the user to add it to PATH, or always call the shim by its full path.
- Another config location: set `PLEDGER_CONFIG=<path>` before `init`; the shim then
  carries it, so scheduled runs need no environment setup.

## 2. Local notes

Use already-known user choices; ask only for missing settings needed for the action.
Write the environment's settings to `DATA/config/local-notes.md` (both prompts read
it first):

- Agent Home root, local memory/reference/journal paths and timezone;
- how you reach the user from a scheduled run (a chat message, a notification, an email,
  or only a file they read);
- which of your own channels you may read when checking items, if any;
- quiet hours, and the language for the digest.

These are habits of this machine and agent; keep them out of the Skill files.

## 3. Schedule the jobs (if your environment can)

Most agent environments can run a prompt on a schedule: built-in scheduled tasks,
automations or routines, or a system scheduler (cron, launchd, Task Scheduler) that
starts a headless agent. Use whatever yours offers; this Skill has no scheduler of its
own. Agree on times with the user. Suggested:

| job | suggested time | prompt for the scheduler |
|---|---|---|
| follow-up | once or twice a day | Run memory's matter follow-up: read `<this Skill>/assets/prompts/followup.md` in full and follow it. |
| digest | once a day, evening | Run memory's matter digest: read `<this Skill>/assets/prompts/digest.md` in full and follow it. |

Put only "read the file and follow it" in the scheduler, never a copy of the prompt, so
upgrades take effect without touching the schedule. At run time the agent reads the
prompt and decides for itself what is worth doing and how to reach the user.

Unattended runs need permission to run `pledger` and read/write the data directory, plus
whatever the local notes allow for reaching the user. Do not grant more.

No scheduler? Then the user says "run my ledger follow-up" or "give me today's digest"
and you follow the same files. `gate` and `runlog` behave the same either way.

## 4. Smoke test

1. Record one real item from the conversation and read it back from `views/index.md`.
2. Run the digest prompt once by hand and confirm the user received it.
3. After the first scheduled run, check `pledger status`: each job's `last_status`.
4. `pledger doctor` must report `ok=true`.

## Upgrade

Replace the Skill directory, then `pledger init` (idempotent; refreshes the shim and the
recorded version) and `pledger doctor`. Schedules stay as they are.

## Legacy TODO and ongoing migration

Follow `commands/update.md` before writing. Search existing items; import each distinct
matter once with its original dated evidence and an explicit migration observation.
Keep conditional ideas or user-paused work as `observe`, with follow-up `none` and
the user's restart/trigger condition in the reason. Do not silently activate them.

Read back the imported item before retiring its old status/action copy. Preserve the
old document's useful background and event history as a clearly dated snapshot with
an item-ID pointer. Priority lists become ordering and references. Importing an old
claim is not fresh verification; retain uncertainties and do not mark old work done
unless evidence supports completion. Do not create schedules merely because work
has moved into the ledger.

## Troubleshooting

- `pledger doctor`, then `pledger status`: which job, when, and the note it ended with.
- `stalled_runs` not empty: a job started but never recorded its end (killed, timed out).
  Look at the scheduler's log; shorten the run if needed.
- `items_locked`: another write is in progress; retry in a minute.
- `invalid_item` on read: an item file was edited by hand. Restore it from a backup or
  ask the user before changing it.

## Uninstall

Remove the schedules and the `pledger` shim. Keep the data directory and config unless
the user explicitly asks to delete them.
