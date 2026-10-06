# personal-ledger follow-up run

You are running the personal-ledger follow-up. Purpose: move open items forward instead
of waiting until someone mentions them. Read `references/follow-up.md` of this Skill
first; `pledger` is described in `SKILL.md`. If `DATA/config/local-notes.md` exists (DATA
is the `data_dir` from `pledger status`), read it: it says how to reach the user and
which channels you may read. Where it conflicts with this file, this file's steps and
boundaries win.

## Steps

1. `pledger gate followup`. If `proceed` is false, stop here and say nothing. Otherwise
   keep the printed `run`.
2. `pledger followup-due --limit 8`. For each `due` item, read
   `DATA/views/items/<item_id>.md`, then act on its `how`:
   - `check`: look, read-only, using what you have (the item's links, your own channels
     that the local notes allow). Compare with `done_when`: met → `done`; real movement →
     `progressed`; nothing new → `no_change`; could not look → `blocked`, saying what
     stopped you.
   - `chase`: only see whether `waiting_on` has replied or acted, from the item's latest
     events and any channel you may read. A reply → record it as a fact, `progressed`,
     and change the follow-up to the next sensible mode; none → `no_change`. Send nothing
     to anyone.
   - `how` too vague to act on: rewrite `followup.how/done_when` in the same update, then
     look. Still impossible → `blocked`.
   - `allow=needs_approval`: do not do it; `blocked` with "needs the user's approval: <what>".
   Record each item with `followup_result` (and any new facts/events) via
   `pledger apply-updates`. Keep each item within a few minutes.
3. Missing follow-up: take up to 5 items from `missing_followup` (most idle first) and
   give each a follow-up per `references/follow-up.md`. If there is not enough to write a
   concrete `how`, use `mode: none` and say in `note` what is missing.
4. Reminders: run `pledger followup-report`. For `urgent` items with `notified=false`,
   plus anything you found today that cannot move without the user and will hurt if it
   waits, decide whether the user should hear now or can wait for the digest. If now,
   send one combined message through the way the local notes describe (none described →
   leave it for the digest): what, the deadline, where it is stuck, what the user needs
   to do. After it is delivered, write a `notification` event on each item, using the
   report's `notify_event_key` as `event_key` (for other reminders
   `followup-reminder:<item_id>:<YYYYMMDD>`). Do not remind twice about an unchanged
   situation.
5. `pledger runlog <run> --status ok --note "due N / checked M (results) / follow-up added K / reminded yes|no"`.

## Running

- Finish everything in this one run; background work and "wake me later" are discarded
  when an unattended run ends.
- Step 5 is mandatory. Out of time: record what is done, `--status partial` with "N left".

## Boundaries

- Read-only. Do not buy, book, cancel, reply, approve or change anything on the user's
  behalf; when that is needed, record `blocked` with what the user should approve.
- Apart from step 4, send nothing to anyone.
- Record `done` only when `done_when` is met with evidence; unsure → `progressed` and the
  evidence as a fact.
