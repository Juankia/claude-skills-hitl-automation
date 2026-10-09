---
name: client-intake
description: Runs a structured new-client intake interview for a professional-services firm (law, accounting, advisory), turns the answers into a validated JSON client record, and saves it to the shared client state used by the document-drafting and filing-prep-checklist skills. Use when the user says "new client", "intake", "onboard a client", "open a matter", or gives a client name together with a type of engagement.
---

# Client intake

Collect intake answers conversationally, validate them deterministically with a
script, and persist a normalized client record. **Claude gathers and explains;
the script decides what is valid.** Never invent answers the user did not give.

## Workflow

1. **Interview.** Ask the questions in [references/questionnaire.md](references/questionnaire.md),
   one section at a time. Skip questions already answered in the conversation.
   If the user is unsure, record nothing for that field rather than guessing.
2. **Write the answers file.** Produce a JSON file shaped like
   [templates/intake_answers.example.json](templates/intake_answers.example.json)
   in the working directory (e.g. `intake_answers.json`). Raw values are fine:
   the script trims whitespace, lower-cases e-mails, upper-cases state codes
   and converts US phone numbers to E.164.
3. **Validate (dry run first).**
   ```bash
   python scripts/validate_intake.py intake_answers.json --dry-run
   ```
   The script prints one JSON object: `ok`, `client_id`, `status`
   (`ready` | `needs_review`), `errors[]` (with JSON paths), `warnings[]`,
   `review_reasons[]`.
4. **Fix errors with the user.** For every item in `errors`, ask the user for
   the missing or corrected value. Do not "fix" data on your own except for
   obvious formatting.
5. **Save.** Re-run without `--dry-run`. The record is upserted into the shared
   state file (location printed as `state_file`). The `client_id` is stable, so
   re-running intake for the same client updates the record instead of
   duplicating it.
6. **Report back** in plain language: client id, status, any `review_reasons`
   (conflict check pending/flagged, past deadlines, emergencies) and warnings.
   Suggest the next step: the `document-drafting` skill for the engagement letter.

## Rules

- A record with `status: needs_review` is saved, but downstream skills will
  surface the review reasons. Tell the user who needs to act.
- `consent.privacy_notice_acknowledged` must be `true`. If the client has not
  acknowledged the privacy notice, stop and say so; do not set it yourself.
- Do not paste the full record back into the chat unless asked; summarize.

## Files

| Path | Purpose |
| --- | --- |
| `scripts/validate_intake.py` | normalize + validate + persist (stdlib + `jsonschema`) |
| `schemas/client_record.schema.json` | JSON Schema (draft 2020-12) for the stored record |
| `references/questionnaire.md` | the interview script |
| `templates/intake_answers.example.json` | example answers file |

Shared state location: `CLIENT_SKILLS_HOME` if set, otherwise the OS default
(`%APPDATA%\ClientSkills` on Windows, `~/Library/Application Support/ClientSkills`
on macOS, `~/.local/share/clientskills` on Linux). Pass `--state-dir` to override.
