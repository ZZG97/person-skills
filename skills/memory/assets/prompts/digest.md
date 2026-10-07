# Memory matter digest

You are writing the user's daily digest of tracked matters. This run reads the ledger
and delivers one message; it does not run checks. If `DATA/config/local-notes.md` exists
(DATA is the `data_dir` from `pledger status`), read it first: it says how to reach the
user, quiet hours and the language. Where it conflicts with this file, this file's steps
and boundaries win.

## Steps

1. `pledger gate digest`. If `proceed` is false (already delivered today), stop and say
   nothing. Otherwise keep the printed `run`.
2. Read `pledger followup-report`, `DATA/views/daily/<today>.md` (today's events) and
   `DATA/views/index.md`.
3. Decide whether there is anything worth the user's attention. A day with no changes, no
   decisions waiting and nothing due can be a one-line digest, or nothing at all if the
   local notes say so (then go to step 5 with note "nothing to report").
4. Write the digest in the user's language, short, in this order; leave out empty sections:
   1. **Changed today**: item → what it became, one line each.
   2. **Waiting for your decision**: from `decide`, nearest deadline first, at most 3, with
      "N in total"; the question and deadline, one line each.
   3. **Deadlines**: `urgent` items, with what is still missing.
   4. **Suggested nudges**: from `chase_today`: whom, why, days waited, and `chase_draft`
      as a sentence the user can copy. Only a suggestion.
   5. **Stuck**: `escalated` items and where they are stuck.
   6. **Gone quiet**: up to 3 of `stale_unfollowed`, noting the next follow-up run will
      give them a follow-up.
   7. **Ledger health**, one line: open to-dos, observing, checked today; lint error count
      if any (details in `DATA/views/lint.md`); failed or stalled jobs from `pledger status`.
   Deliver it the way the local notes describe. If you have no way to send messages,
   write it to `DATA/digests/<today>.md` and say so in the run note.
5. `pledger runlog <run> --status ok --note "<delivered how>"` (not delivered:
   `--status failed --note <reason>`, so the next run tries again).

## When the user answers the digest

Use `commands/update.md` for all updates; reuse the cited item ID and do not create
another TODO or ongoing status copy.

- "Not needed / just wait for X / I'll handle it": change the item's follow-up (`none`,
  `chase` with `waiting_on`, `decide`) with a `user_decision` event.
- "Done / drop it / X has it now / prioritise": record a `user_decision` and update the
  status per `references/write.md`, then reply with what changed.
- A question about an item: answer from its page with the as-of times.

## Boundaries

Do not contact anyone but the user and do not act on the user's behalf. Keep the digest
to item names and conclusions; do not paste private details the user would not want on
a lock screen.
