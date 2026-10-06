---
name: personal-ledger
description: A local ledger of the things a person wants kept track of (errands, plans, appointments, things owed or awaited, decisions to make), maintained by the agent from conversation. Records each matter with status, dated facts, next actions and who is waited on, follows up on open items, and produces a daily digest. Use when the user says "remember / keep track of / remind me / I'm waiting on / did X ever happen / what's still open", reports progress or a decision on something tracked, or asks to set up, run or check the scheduled follow-up and digest.
---

# Personal Ledger

A ledger of matters the user wants kept track of. The user tells you; you record it
through the `pledger` program, which owns the files, validation, follow-up scheduling
and rendered views. You do the semantic part: which matter a remark belongs to, what was
decided, what happens next.

`pledger` is the shim created by `init`; without it, run
`python3 <this Skill>/scripts/ledger.py`. `pledger status` prints the data directory.
Below, `DATA` means that directory. If `DATA/config/local-notes.md` exists, read it first:
it holds this machine's habits (how to reach the user, which channels you may read).

## Route

| The user wants | Read |
|---|---|
| what is open, where a matter stands, who owes what | "Reading" below |
| record something new, progress, a decision, a correction | [references/write.md](references/write.md) |
| follow-up fields, recording a check | [references/follow-up.md](references/follow-up.md) |
| set up, schedule, check or repair | [references/setup.md](references/setup.md) |

Scheduled runs read their own prompt: [follow-up](assets/prompts/followup.md),
[daily digest](assets/prompts/digest.md).

## Model in one screen

- **Item**: one matter the user could later ask "how is it going?" about. `category` is a
  free short label (`health`, `home`, `money`, `travel`, ...) used only to group the index.
- **Disposition** `status`: `active` / `waiting` are to-dos; `observe` is watch-only;
  `closed` / `transferred` are finished.
- **Events** say who said what when (`user_decision` is the user deciding, `agent_report`
  is only your claim). **Facts** carry an as-of time and evidence. Keep facts and
  disposition separate.
- **Follow-up** says how the item moves forward: `check` (you verify it), `chase` (waiting
  on someone the user has to nudge), `decide` (the user must choose), `none`.
- `views/` pages are rendered; change items only through `pledger apply-updates`.

## Capturing from conversation

When the user mentions something worth tracking, record it in the same turn; do not wait
for a scheduled run. One remark may update several items. If it is unclear whether the
user wants it tracked, ask once, briefly. Things about a person (relation, preferences)
go to `DATA/config/people.json`, not into an item.

Information may also reach you through your own channels (mail, calendar, messages,
notes) when the user has given you access to them. You decide whether it bears on an
item; record what you use as an `observation` event with evidence pointing at where you
read it. Never widen your access for the ledger's sake.

## Reading

- What is open: `DATA/views/index.md` (active + waiting are to-dos). Do not read `items/`
  wholesale.
- One matter: `DATA/views/items/<item_id>.md` — status and reason, facts (mind the as-of
  time), next actions, follow-up, events, gaps.
- Today's follow-up, decisions waiting on the user, nudges, deadlines:
  `DATA/views/followup.md` or `pledger followup-report`.
- People: `DATA/views/people/index.md` and one page per person.
- Ledger problems: `DATA/views/lint.md`. When an item appears there, check its events
  before acting on its old next action.

Answer from the record and say how old the facts are; do not present a stale fact as
the current state.

## Boundaries

- The ledger is private. Keep it out of every repository, sync or backup service the user
  has not chosen for it, and never quote it to anyone but the user.
- Do not act for the user toward other people (no replies, nudges or purchases) unless
  the user asks for that specific action.
- Never store passwords, tokens, card numbers or identity-document numbers; write
  "stored in <where>" instead.
