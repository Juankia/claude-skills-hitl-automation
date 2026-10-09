---
name: filing-prep-checklist
description: Checks a court or agency filing packet (manifest + PDFs) against a configurable rules file - required fields, required documents per filing type, file naming, size and page limits, PDF encryption and text-layer checks, and client intake/conflict status - and produces a gap report for human review. It never files or submits anything. Use when the user says "prepare a filing", "check the packet", "is this ready to file", "filing checklist", or "validate filing requirements".
---

# Filing prep checklist

Turn "is this ready to file?" into a deterministic, auditable checklist. The
script finds the gaps; Claude explains them; **a human decides** whether and
when to file. Submission itself is out of scope for this skill.

## Workflow

1. **Locate the packet.** A packet is a folder with `manifest.json` and the PDFs
   it lists. If there is no manifest yet, help the user build one from
   [templates/manifest.example.json](templates/manifest.example.json); take the
   `client_id` from the shared client state (created by `client-intake`).
2. **Pick the rules.** Default: `rules/default_rules.json` (a fictional demo
   court). If the user names a court/agency with its own rules file, pass it
   with `--rules`. Do not guess court rules; if none exist, say so and offer to
   create a rules file *with* the user from their local rules.
3. **Run the check.**
   ```bash
   python scripts/check_packet.py path/to/packet
   python scripts/check_packet.py path/to/packet --rules rules/my_court.json --report-dir out/
   ```
   Exit code `0` = no blocking gaps, `2` = blocking gaps, `1` = could not run.
4. **Report.** Summarize `gap_report.md` for the user: blocking gaps first, each
   with the concrete fix (rename file X to Y, split document over the page
   limit, OCR the scan, clear the conflict check...). Then warnings.
5. **Stop.** Even when status is `ready_for_human_review`, do not claim the
   packet is "filed" or "approved". Hand off to the responsible professional.
   If they want automation for the portal submission, point them to the
   human-in-the-loop RPA agent in `rpa/`, which requires explicit approval
   before the irreversible click.

## What is checked

| Check | Rule key | Severity |
| --- | --- | --- |
| Required manifest fields present | `required_fields` | blocking |
| Field formats (e.g. case number) | `field_patterns` | blocking |
| Required documents for the filing type | `required_documents` | blocking |
| Allowed extensions, naming convention | `allowed_extensions`, `file_naming` | blocking |
| File size / page limits per document type | `max_file_size_mb`, `max_pages` | blocking |
| Encrypted PDF / missing text layer | `pdf_checks` | configurable |
| Intake status and conflict check in shared state | `client_checks` | blocking |
| Files in the folder that are not in the manifest | - | warning |

## Files

| Path | Purpose |
| --- | --- |
| `scripts/check_packet.py` | runs every check, writes `gap_report.md` + `gap_report.json`, records result in shared state |
| `rules/default_rules.json` | demo rule set, copy and edit per court |
| `templates/manifest.example.json` | example packet manifest |

Requires `pypdf` (`pip install pypdf`).
