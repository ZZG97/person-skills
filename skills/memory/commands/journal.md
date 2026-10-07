# Journal Work

Use the best available conversation/activity evidence. When the user wants a day-level
review across conversations, use an available history Skill or capability. Otherwise
summarize only evidence actually available and explain the scope.

Use the Home's journal location (default `memory/journals/YYYY-MM-DD.md`) and configured
timezone. Preserve existing entries. Record material events, decisions, progress and
lessons; skip greetings and execution noise. Use concise dated entries:

```markdown
- HH:MM `<source-ref>` [Topic / item-id] What happened or was decided.
```

A source reference is optional. Preserve opaque references exactly; never decode,
shorten or substitute session/thread/message IDs for a history-provider reference.

Journals record history. When an event changes a matter or a reference fact, use
[the common update workflow](update.md) for its authoritative owner. An unresolved
question in the journal does not create a second TODO list.
