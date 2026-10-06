# Writing to the ledger

Write only through the program; never edit item JSON by hand:

```
pledger apply-updates --updates <file.json>
```

It validates, merges, re-renders the views and prints the changed items. Put the update
file in a temporary location and delete it afterwards.

## Updates the program rejects

When a write is rejected, fix it as the error says and retry; do not work around the check.

- A next action whose `owner` is empty or a placeholder (`TBD`, `someone`, `unknown`,
  `待定`, ...). Name the person; several owners are fine (`Alex/Sam`). If nobody knows,
  record a gap.
- A `due` that is not an ISO time (`next week`). Write `2026-10-30` or
  `2026-10-30T18:00:00+08:00`; leave it empty when there is no hard deadline.
- An action over 200 characters. Keep the action short and move detail into
  `preconditions` or an event.
- Next actions or a non-`none` follow-up on a closed/transferred item. Reopen it first.
- Follow-up `decide`/`chase` (waiting on someone) while the status is not `waiting`.
  Send `disposition.status=waiting` and an event in the same update.
- An `item_id` with characters other than letters, digits, `.`, `_`, `-`.

The program also: moves remaining next actions to `retired_next_actions` and stops
follow-up when an item is closed or transferred; merges participants by name.

## Current state needs an event

Disposition, title, purpose, scope, category, next actions and gaps describe the current
state. They change only when the same update carries an authoritative event
(`user_decision`, `user_report`, `agent_report`, `observation`, `correction`) that is newer
than the item's latest event. That keeps a replayed or late update from undoing a newer
decision. So:

- Always pair a state change with an event, and use the real current time (run `date`);
  a future timestamp would make every later update look old.
- Write the disposition as `"disposition": {"status", "reason", "decided_at"}`; a
  top-level `"status"` is ignored.
- To replace the plan rather than add to it, set `"replace_next_actions": true`. The same
  flag exists for `facts`, `gaps`, `participants` and `external_refs`; use those only to
  correct a mistake.

## Event types

| type | meaning |
|---|---|
| `user_decision` | the user decided something (close it, drop it, choose B) |
| `user_report` | the user told you about progress or a new fact |
| `agent_report` | you did or verified something; a claim, not an acceptance |
| `observation` | something you read in one of your own channels |
| `gap` | something you could not read or that does not add up |
| `correction` | fixing an earlier wrong record; history stays |
| `notification` | you reminded the user; the event key prevents repeating it |
| `baseline` | the starting record of an item migrated from elsewhere |

`followup_check` events are created by the program from `followup_result`.

Every event has a stable unique `event_key` (`<kind>:<item short name>:<what>:<date>`),
`observed_at`, a short `summary`, optionally `actor: {"name": ...}`, and at least one
evidence ref `{"type", "ref", "note"}`. Useful evidence types: `conversation` (ref = date
and gist of what the user said), `url`, `file` (absolute path), `command`, `note`.

## A new item

Check the index first so you do not create a duplicate. Use `item_id`
`pl-<YYYYMMDD>-<short-name>`, a title of at most 40 characters, a `category`, and an
initial follow-up (see follow-up.md).

```json
{"schema_version": 1, "items": [{
  "item_id": "pl-20261006-passport",
  "title": "Renew passport",
  "category": "admin",
  "purpose": "Passport expires in March; renew before the April trip.",
  "disposition": {"status": "waiting", "reason": "Waiting for the photos", "decided_at": "2026-10-06T10:00:00+08:00"},
  "participants": [{"name": "Photo shop", "role_in_item": "executor"}],
  "next_actions": [{"action": "Submit the application online", "owner": "Alex", "due": "2026-10-20", "preconditions": "photos ready"}],
  "followup": {"mode": "chase", "who": "Alex", "waiting_on": "Photo shop", "chase_draft": "Are my passport photos ready?"},
  "events": [{"event_key": "user:passport:photos-ordered:20261006", "type": "user_report",
              "observed_at": "2026-10-06T10:00:00+08:00", "summary": "Ordered passport photos, ready in 2 days",
              "actor": {"name": "Alex"},
              "evidence": [{"type": "conversation", "ref": "2026-10-06 chat", "note": "user said"}]}]
}]}
```

Participant roles: `requester`, `owner`, `executor`, `reviewer`, `informed` (or empty).

## Progress, decisions, closing

- The user says "done", "drop it" or "Sam is handling it now": write a `user_decision` and
  set the status to `closed` (reason "done" or "dropped") or `transferred`.
- You verified completion yourself: `agent_report` with evidence, status `closed`, reason
  stating the evidence and "closed by the agent, not confirmed by the user". Unsure? Leave
  it open and record a gap or a check.
- A new fact: add it under `facts` with `key`, `as_of`, `summary`, `evidence`.
- Something unreadable or contradictory: add a `gaps` entry and a `gap` event.
- A wrong record: a `correction` event plus the corrected fields.
- A new title: the new `title` plus a `correction` event saying why.

## People

`DATA/config/people.json` is plain configuration you may edit (keep it valid JSON):

```json
{"schema_version": 1, "people": [{"name": "Sam", "relation": "brother", "notes": "prefers calls"}]}
```

Use the same name in participants, owners and `waiting_on` so the people pages line up.
Configure the user's own name with `pledger init --user-name <name>`; it is then
recognised as the user and not listed among other people.

## Fixing lint issues

`views/lint.md` is regenerated on every write (`pledger lint` prints it as JSON). Fix the
items you touch:

- Closed item still has next actions / follow-up: write any update with an event to it.
- Next action past due: replace the plan with `replace_next_actions`, or close the item.
- Follow-up check overdue: run the check (follow-up.md) or change the follow-up.
- The user decided after the question was set: apply the decision, or ask a new question.
- Mode/status mismatch, placeholder owner, bad due: apply the rules above.
- Possible duplicates (same external ref in two open items): keep one, close the other
  with reason "merged into <item_id>".
