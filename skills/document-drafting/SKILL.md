---
name: document-drafting
description: Generates a first-draft engagement letter / service agreement as a deterministic .docx (or Markdown) from a client record saved by the client-intake skill, inserting jurisdiction-specific clauses and flagging anything missing for human review. Use when the user asks to "draft an engagement letter", "prepare the service agreement", "generate the retainer letter", or wants a first draft for a client already taken in.
---

# Document drafting

Produce a **first draft** for a professional to review. Layout and wording come
from a versioned template and a jurisdiction table, not from free-form model
output, so two runs with the same inputs produce the same file.

## Workflow

1. **Identify the client.** If the user did not give a `client_id`, list the
   known clients and ask which one:
   ```bash
   python ../../shared/client_state.py list      # from the repo
   python scripts/client_state.py list           # when installed (vendored copy)
   ```
   If the client does not exist yet, use the `client-intake` skill first.
2. **Render the draft.**
   ```bash
   python scripts/draft_document.py --client-id <id>                # .docx
   python scripts/draft_document.py --client-id <id> --format md    # quick preview
   ```
   Options: `--out PATH`, `--date YYYY-MM-DD`, `--template PATH`,
   `--firm PATH` (firm profile JSON, see `templates/firm_profile.example.json`).
3. **Read the JSON result** and report to the user:
   - `output` path and `status` (`draft_ready_for_review` or `draft_needs_attention`)
   - `missing`: template variables with no value (rendered as highlighted
     `[[MISSING: ...]]` markers in the document)
   - `review_markers`: jurisdiction clauses that are not configured
   - `notes`: intake review reasons carried over (e.g. conflict check pending)
4. **Never** describe the draft as final or send it to the client. Remind the
   user that a licensed professional must review and sign it.

## Customizing

- **Template**: `templates/engagement_letter.md`. Supports `{{ path }}`,
  filters (`money`, `title`, `join`, `longdate`, `upper`) and line-level
  `{% if path %}`, `{% if not path %}`, `{% if path == "value" %}` blocks.
- **Jurisdictions**: `references/jurisdictions.json`, keyed by 2-letter state
  code with a `default` fallback. The bundled clauses are illustrative sample
  language, not legal advice.
- If the user asks for a wording change, edit the template (and say so) rather
  than hand-editing the generated .docx, so the change is repeatable.

## Files

| Path | Purpose |
| --- | --- |
| `scripts/draft_document.py` | render template, build reproducible .docx, record artifact in state |
| `templates/engagement_letter.md` | the letter template |
| `templates/firm_profile.example.json` | firm letterhead data |
| `references/jurisdictions.json` | state-specific clauses |

Requires `python-docx` (`pip install python-docx`) for `.docx` output.
