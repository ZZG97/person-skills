# Update Persistent Information

All conversational writes start here, including changes to a tracked matter.

1. Resolve `HOME_ROOT` and `DATA` as described in `SKILL.md`. Read the Home's
   information architecture and memory router if present, then use the narrowest
   relevant index. Inspect an existing owner before creating a new record.
2. Separate the user's remark into distinct facts and obligations. For each one,
   choose its owner by purpose:

   | Information | Owner |
   |---|---|
   | Identity, enduring preference or user background | The Home's identity/profile files |
   | Matter status, progress, next action, deadline, wait or decision | One ledger item |
   | Machine, service or account facts | The corresponding system document |
   | Project requirements, substantial background or design | The project's repository/workspace or a Home reference document |
   | Durable knowledge or dated research | The Home's knowledge/wiki files |
   | What happened on a date | Journal history, with a link to the current owner |
   | Priority or navigation | An index entry containing the owner reference |

3. For a matter, read `DATA/views/index.md` and search by subject, participant and
   any known item ID or external reference. Read matching item pages, including
   closed items when reopening is plausible. Reuse the existing ID; a new title,
   category or location is not a new matter. Also check any legacy TODO/ongoing
   reference named in the Home's router. Migrate an existing legacy owner before
   updating it; do not leave two live versions. Follow [ledger writes](../references/write.md).
4. For a reference fact, update its existing owner and preserve unrelated content.
   If it also implies an obligation, create/update the distinct item and link the
   two. Put status and next action in the item only. Existing project trackers keep
   their own authority; use a transferred pointer instead of a local status copy.
5. Add navigation only when it helps future recall. Read the current owner on later
   recall, rather than trusting an index label. If always-loaded identity/profile/
   router files changed, run the Home's context renderer when one exists.

Use the original as-of time and evidence for imported facts. Importing a record
does not verify its truth today. Record uncertainty instead of resetting its age.

For forgetting, remove or redact only the information the user asked to forget,
including its index references. Closing a matter preserves its history and is not
the same as deleting it. Resolve the exact scope before an ambiguous deletion.
