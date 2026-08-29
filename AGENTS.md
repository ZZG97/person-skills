# Skill repository instructions

- Treat this Git repository as the canonical source.
- Read `skill-kit.json` before editing or installing Skills.
- Keep machine-local values in the ignored root `skill-kit.local.json`; never
  add that file to Git.
- Replace machine differences with declared `@@VARIABLE@@` tokens only when the
  difference is truly a value; rewrite semantic workflow differences explicitly.
- Modify `skills/<name>/`, never a generated installation directory.
- Validate and preview changes before applying them locally.
- Do not commit, push, publish, delete, or overwrite without user authorization.
- Never store or render credentials, cookies, access tokens, or private keys.
