#!/usr/bin/env python3
"""Normalize + validate intake answers and persist them to the shared client state.

Usage:
    python validate_intake.py answers.json            # validate and save
    python validate_intake.py answers.json --dry-run  # validate only
    python validate_intake.py answers.json --today 2026-10-09

Output is a single JSON object on stdout so Claude (or any caller) can parse
it reliably:

    {"ok": true, "client_id": "...", "status": "ready", "errors": [], "warnings": [...]}

Exit codes: 0 = valid (saved unless --dry-run), 1 = validation errors, 2 = usage error.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
# Prefer a vendored copy (installed skill), fall back to the repo's shared/ dir.
for _candidate in (HERE, HERE.parents[2] / "shared"):
    if (_candidate / "client_state.py").exists():
        sys.path.insert(0, str(_candidate))
        break

from client_state import ClientStateStore, utc_now  # noqa: E402

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - surfaced as a friendly error
    sys.stderr.write("Missing dependency: pip install jsonschema\n")
    raise SystemExit(2)

SCHEMA_PATH = HERE.parent / "schemas" / "client_record.schema.json"


# --- normalization ---------------------------------------------------------

def _strip_strings(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()
    if isinstance(value, list):
        return [_strip_strings(v) for v in value]
    if isinstance(value, dict):
        return {k: _strip_strings(v) for k, v in value.items()}
    return value


def normalize_phone(raw: str) -> str:
    """Return a US number in E.164 (+1XXXXXXXXXX); leave unparseable input untouched."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return f"+1{digits}" if len(digits) == 10 else raw


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:32].rstrip("-") or "client"


def make_client_id(record: dict[str, Any]) -> str:
    """Stable id: re-running intake for the same client updates, not duplicates."""
    client = record["client"]
    key = "|".join(
        [
            client.get("legal_name", "").lower(),
            client.get("contact", {}).get("email", "").lower(),
            record.get("matter", {}).get("practice_area", ""),
        ]
    )
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:6]
    return f"{slugify(client.get('legal_name', ''))}-{digest}"


def normalize(answers: dict[str, Any]) -> dict[str, Any]:
    record = _strip_strings(copy.deepcopy(answers))
    client = record.setdefault("client", {})
    contact = client.setdefault("contact", {})
    if "email" in contact:
        contact["email"] = contact["email"].lower()
    if "phone" in contact:
        contact["phone"] = normalize_phone(contact["phone"])
    address = client.setdefault("address", {})
    if "state" in address:
        address["state"] = address["state"].upper()
    matter = record.setdefault("matter", {})
    if "jurisdiction" in matter:
        matter["jurisdiction"] = matter["jurisdiction"].upper()
    record.setdefault("intake", {})
    record.setdefault("conflict_check", {"status": "pending"})
    return record


# --- validation ------------------------------------------------------------

def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _json_path(error) -> str:
    return "$" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in error.absolute_path)


def business_rules(record: dict[str, Any], today: date) -> tuple[list[str], list[str]]:
    """Rules that are awkward in JSON Schema. Returns (review_reasons, warnings)."""
    review: list[str] = []
    warnings: list[str] = []
    matter = record.get("matter", {})
    conflict = record.get("conflict_check", {}).get("status")

    if conflict == "flagged":
        review.append("Conflict check flagged a potential conflict; a supervising professional must clear it.")
    elif conflict == "pending":
        review.append("Conflict check has not been run yet.")

    if matter.get("urgency") == "emergency":
        review.append("Matter marked as emergency; route to the responsible professional today.")

    for deadline in matter.get("deadlines", []):
        try:
            due = date.fromisoformat(deadline["date"])
        except (KeyError, ValueError):
            continue  # schema validation reports the format problem
        days = (due - today).days
        if days < 0:
            review.append(f"Deadline '{deadline['label']}' ({deadline['date']}) is already in the past.")
        elif days <= 14:
            warnings.append(f"Deadline '{deadline['label']}' is in {days} day(s).")

    names = {p.lower() for p in matter.get("opposing_parties", [])}
    if record.get("client", {}).get("legal_name", "").lower() in names:
        review.append("Client name also appears as an opposing party.")

    address_state = record.get("client", {}).get("address", {}).get("state")
    if address_state and matter.get("jurisdiction") and address_state != matter["jurisdiction"]:
        warnings.append(
            f"Client resides in {address_state} but the matter is in {matter['jurisdiction']}; "
            "confirm the professional is authorized to practice there."
        )
    return review, warnings


def validate(answers: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    record = normalize(answers)
    review, warnings = business_rules(record, today)
    record["intake"].update(
        {
            "status": "needs_review" if review else "ready",
            "completed_at": record["intake"].get("completed_at") or utc_now(),
        }
    )
    if review:
        record["intake"]["review_reasons"] = review
    else:
        record["intake"].pop("review_reasons", None)

    if record.get("client", {}).get("legal_name"):
        record["client_id"] = make_client_id(record)

    validator = Draft202012Validator(load_schema())
    errors = [
        {"path": _json_path(e), "message": e.message}
        for e in sorted(validator.iter_errors(record), key=lambda e: list(e.absolute_path))
    ]
    return {
        "ok": not errors,
        "client_id": record.get("client_id"),
        "status": record["intake"]["status"],
        "errors": errors,
        "warnings": warnings,
        "review_reasons": review,
        "record": record,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("answers", type=Path, help="JSON file with the questionnaire answers")
    parser.add_argument("--dry-run", action="store_true", help="validate only, do not write state")
    parser.add_argument("--state-dir", type=Path, help="override the shared state directory")
    parser.add_argument("--today", type=date.fromisoformat, help="reference date (YYYY-MM-DD) for deadline checks")
    args = parser.parse_args(argv)

    try:
        answers = json.loads(args.answers.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "errors": [{"path": "$", "message": str(exc)}]}))
        return 2

    result = validate(answers, today=args.today)
    if result["ok"] and not args.dry_run:
        store = ClientStateStore(args.state_dir)
        store.upsert_client(result["record"])
        result["state_file"] = str(store.path)
    result["saved"] = bool(result["ok"] and not args.dry_run)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
