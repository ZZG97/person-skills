# Follow-up

An open item should not wait until someone mentions it again; each says how it moves
forward. The program computes when to look next; the agent looks and records honestly.

## The `followup` field (written through `apply-updates`)

| field | meaning |
|---|---|
| `mode` | `check` you verify it yourself / `chase` waiting on someone the user must nudge / `decide` waiting for the user's choice / `none` nothing to follow |
| `who` | who looks: you (the agent), or the user for `decide` and `chase` |
| `how` | concretely how to look: which page, message thread, tracking number, what to compare. Written so the next agent can act without guessing |
| `done_when` | an objective end condition one look can confirm, e.g. "tracking page shows delivered" |
| `waiting_on` | required for `chase`: the person waited on |
| `chase_draft` | for `chase`: one sentence the user can send as is |
| `due_at` | only for a hard deadline (ISO time); checks never fall later than it and the digest flags it |
| `interval_days` | optional, 1–7; default 1 for check/decide, 2 for chase |
| `next_check_at` | optional first check time; otherwise computed from the interval |
| `allow` | `read_only` (default) / `needs_approval` (looking requires an action; ask the user first) |
| `note` | anything else |

`check` needs `how` and `done_when`; `chase` needs `waiting_on`. `decide` and `chase` need
status `waiting`. The program maintains `no_change_streak`, `blocked_streak`,
`last_checked_at`, `last_result` and `set_at`; do not write them.

Choosing a mode:

- You can find out by looking (a tracking page, a booking, your own channels) → `check`.
- It depends on another person replying or acting → `chase`. You never send the nudge;
  the digest suggests it to the user.
- The user has to choose (buy or not, which option, keep or cancel) → `decide`.
- Nothing to do but remember, or the user said not to bother → `none` (or move the item
  to `observe` / `closed`).

```json
{"schema_version": 1, "items": [{
  "item_id": "pl-20261006-sofa", "title": "Sofa delivery",
  "followup": {"mode": "check", "who": "agent",
               "how": "Open the order page linked in the item's refs and read the delivery status",
               "done_when": "Order page shows delivered", "due_at": "2026-10-15T18:00:00+08:00"}
}]}
```

## Recording a check: `followup_result`

```json
{"schema_version": 1, "items": [{
  "item_id": "pl-20261006-sofa", "title": "Sofa delivery",
  "followup_result": {"result": "no_change", "summary": "Still 'preparing', last update Oct 4",
                      "checked_at": "2026-10-07T10:30:00+08:00",
                      "evidence": [{"type": "url", "ref": "https://example.com/orders/123", "note": "order page"}]},
  "facts": []
}]}
```

`result` is one of four; the program sets the next check time:

- `progressed`: real movement → check again after the normal interval.
- `no_change`: nothing new → the interval doubles (1 → 2 → 4 → 7 days at most).
- `done`: `done_when` is met → the program closes the item and stops follow-up. Use it
  only when the condition is actually met.
- `blocked`: you could not look (no access, site down) → after 3 in a row the digest
  shows it to the user.

Replaying the same check (same `checked_at`) is recorded once.

## Reading

- `pledger followup-due [--limit 8]`: items whose check/chase is due (nearest deadline
  first) and open items with no follow-up yet. `decide` items are not "due": they wait
  for the user and appear in the report instead.
- `pledger followup-report`: today's checks, decisions waiting on the user, suggested
  nudges, hard deadlines within a day, repeatedly blocked items, idle items with no
  follow-up, lint summary. The same content is rendered to `DATA/views/followup.md`.
