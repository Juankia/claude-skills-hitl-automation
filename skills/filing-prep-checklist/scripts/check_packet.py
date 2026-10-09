#!/usr/bin/env python3
"""Validate a filing packet against a rules file and write a gap report.

Usage:
    python check_packet.py PACKET_DIR [--rules rules.json] [--report-dir DIR]
                                      [--state-dir DIR] [--no-state]

PACKET_DIR must contain a ``manifest.json``::

    {
      "client_id": "brightwater-ceramics-llc-1a2b3c",
      "case": {"case_number": "26-CV-01234", "court": "...", "case_title": "...",
               "filing_type": "motion", "filer_name": "..."},
      "documents": [{"path": "2026-10-09_motion-to-extend.pdf", "type": "motion"}]
    }

This script is read-only with respect to the outside world: it inspects files,
writes ``gap_report.md`` / ``gap_report.json`` and records the result in the
shared client state. It never uploads or submits anything. Submission is a
separate, human-approved step (see ``rpa/`` in the repository).

Exit codes: 0 = no blocking gaps (ready for human review), 2 = blocking gaps,
1 = could not run (bad manifest/rules).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
for _candidate in (HERE, HERE.parents[2] / "shared"):
    if (_candidate / "client_state.py").exists():
        sys.path.insert(0, str(_candidate))
        break

from client_state import ClientStateStore, StateError, utc_now  # noqa: E402

DEFAULT_RULES = SKILL_DIR / "rules" / "default_rules.json"
BLOCKING, WARNING = "blocking", "warning"


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str
    target: str = "packet"


class PacketError(RuntimeError):
    pass


def _get(data: dict[str, Any], dotted: str) -> Any:
    value: Any = data
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


# --- individual checks -----------------------------------------------------

def check_fields(manifest: dict[str, Any], rules: dict[str, Any]) -> list[Finding]:
    findings = []
    for field in rules.get("required_fields", []):
        value = _get(manifest, field)
        if value in (None, "", []):
            findings.append(Finding(BLOCKING, "missing_field", f"Required field '{field}' is empty.", field))
    for field, spec in rules.get("field_patterns", {}).items():
        value = _get(manifest, field)
        if value and not re.fullmatch(spec["pattern"], str(value)):
            findings.append(
                Finding(
                    BLOCKING,
                    "field_format",
                    f"'{field}' value '{value}' does not match the expected format (e.g. {spec.get('example', spec['pattern'])}).",
                    field,
                )
            )
    return findings


def check_required_documents(manifest: dict[str, Any], rules: dict[str, Any]) -> list[Finding]:
    filing_type = _get(manifest, "case.filing_type")
    required = rules.get("required_documents", {})
    if not filing_type:
        return []
    if filing_type not in required:
        return [Finding(WARNING, "unknown_filing_type", f"No document requirements configured for filing type '{filing_type}'.")]
    present = {d.get("type") for d in manifest.get("documents", [])}
    return [
        Finding(BLOCKING, "missing_document", f"Filing type '{filing_type}' requires a '{doc_type}' document.", doc_type)
        for doc_type in required[filing_type]
        if doc_type not in present
    ]


def inspect_pdf(path: Path) -> dict[str, Any]:
    """Return {'valid', 'encrypted', 'pages', 'has_text', 'error'} for a PDF file."""
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    info: dict[str, Any] = {"valid": False, "encrypted": False, "pages": 0, "has_text": False, "error": None}
    try:
        reader = PdfReader(str(path))
        info["encrypted"] = reader.is_encrypted
        if reader.is_encrypted:
            info["valid"] = True
            return info
        info["pages"] = len(reader.pages)
        info["has_text"] = any((page.extract_text() or "").strip() for page in reader.pages[:3])
        info["valid"] = True
    except (PdfReadError, OSError, ValueError) as exc:
        info["error"] = str(exc)
    return info


def check_documents(packet: Path, manifest: dict[str, Any], rules: dict[str, Any]) -> tuple[list[Finding], list[dict[str, Any]]]:
    findings: list[Finding] = []
    inventory: list[dict[str, Any]] = []
    naming = rules.get("file_naming", {})
    allowed_ext = [e.lower() for e in rules.get("allowed_extensions", [".pdf"])]
    max_mb = rules.get("max_file_size_mb")
    max_pages = rules.get("max_pages", {})
    pdf_rules = rules.get("pdf_checks", {})
    seen: set[str] = set()

    for doc in manifest.get("documents", []):
        rel = doc.get("path", "")
        doc_type = doc.get("type", "unknown")
        entry: dict[str, Any] = {"path": rel, "type": doc_type}
        inventory.append(entry)

        if rel in seen:
            findings.append(Finding(BLOCKING, "duplicate_document", "Document listed more than once.", rel))
            continue
        seen.add(rel)

        # Manifest paths are always relative and must stay inside the packet.
        candidate = (packet / rel).resolve()
        if Path(rel).is_absolute() or packet.resolve() not in candidate.parents:
            findings.append(Finding(BLOCKING, "path_outside_packet", "Document path must be relative to the packet.", rel))
            continue
        if not candidate.is_file():
            findings.append(Finding(BLOCKING, "file_not_found", "File listed in manifest does not exist.", rel))
            continue

        name = candidate.name
        if candidate.suffix.lower() not in allowed_ext:
            findings.append(Finding(BLOCKING, "extension", f"Extension '{candidate.suffix}' is not allowed ({', '.join(allowed_ext)}).", rel))
            continue
        if naming.get("pattern") and not re.fullmatch(naming["pattern"], name):
            findings.append(
                Finding(BLOCKING, "file_naming", f"File name does not follow the convention (e.g. {naming.get('example', naming['pattern'])}).", rel)
            )

        size_mb = candidate.stat().st_size / (1024 * 1024)
        entry["size_mb"] = round(size_mb, 3)
        if max_mb is not None and size_mb > max_mb:
            findings.append(Finding(BLOCKING, "file_size", f"File is {size_mb:.1f} MB; limit is {max_mb} MB.", rel))

        pdf = inspect_pdf(candidate)
        entry.update(pages=pdf["pages"], encrypted=pdf["encrypted"], has_text=pdf["has_text"])
        if not pdf["valid"]:
            findings.append(Finding(BLOCKING, "pdf_invalid", f"Not a readable PDF ({pdf['error']}).", rel))
            continue
        if pdf["encrypted"]:
            sev = pdf_rules.get("forbid_encryption")
            if sev:
                findings.append(Finding(sev, "pdf_encrypted", "PDF is password-protected/encrypted.", rel))
            continue
        limit = max_pages.get(doc_type, max_pages.get("default"))
        if limit is not None and pdf["pages"] > limit:
            findings.append(Finding(BLOCKING, "page_limit", f"{pdf['pages']} pages exceeds the {limit}-page limit for '{doc_type}'.", rel))
        sev = pdf_rules.get("require_text_layer")
        if sev and not pdf["has_text"]:
            findings.append(Finding(sev, "pdf_no_text", "No text layer found; the document may be a scan that needs OCR.", rel))

    listed = {Path(d.get("path", "")).name for d in manifest.get("documents", [])}
    for extra in sorted(p.name for p in packet.iterdir() if p.is_file()):
        if extra not in listed and extra not in {"manifest.json", "gap_report.md", "gap_report.json"}:
            findings.append(Finding(WARNING, "unlisted_file", "File is in the packet folder but not in the manifest.", extra))
    return findings, inventory


def check_client_state(manifest: dict[str, Any], rules: dict[str, Any], store: ClientStateStore | None) -> list[Finding]:
    client_id = manifest.get("client_id")
    if store is None or not client_id:
        return []
    try:
        record = store.get_client(client_id)
    except StateError:
        return [Finding(BLOCKING, "unknown_client", f"Client '{client_id}' is not in the shared client state; run client-intake first.", "client_id")]
    findings = []
    checks = rules.get("client_checks", {})
    want_intake = checks.get("require_intake_status")
    intake = record.get("intake", {})
    if want_intake and intake.get("status") != want_intake:
        reasons = "; ".join(intake.get("review_reasons", [])) or "no reason recorded"
        findings.append(Finding(BLOCKING, "intake_not_ready", f"Intake status is '{intake.get('status')}' ({reasons}).", "client_id"))
    want_conflict = checks.get("require_conflict_status")
    conflict = record.get("conflict_check", {}).get("status")
    if want_conflict and conflict != want_conflict:
        findings.append(Finding(BLOCKING, "conflict_not_cleared", f"Conflict check status is '{conflict}'.", "client_id"))
    return findings


# --- report ----------------------------------------------------------------

def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Filing prep gap report: {report['case'].get('case_number') or '(no case number)'}",
        "",
        f"- **Status:** {report['status'].replace('_', ' ')}",
        f"- **Rules:** {report['rules']['name']} (v{report['rules']['version']})",
        f"- **Client:** {report.get('client_id') or '(none)'}",
        f"- **Filing type:** {report['case'].get('filing_type') or '(none)'}",
        f"- **Generated:** {report['generated_at']}",
        "",
        "> This report was generated automatically. It does not file or submit anything.",
        "> A responsible professional must review it and approve any submission.",
        "",
    ]
    for severity, heading in ((BLOCKING, "Blocking gaps"), (WARNING, "Warnings")):
        items = [f for f in report["findings"] if f["severity"] == severity]
        lines.append(f"## {heading} ({len(items)})")
        lines.append("")
        if items:
            lines += [f"- [ ] `{f['target']}`: {f['message']} _({f['code']})_" for f in items]
        else:
            lines.append("- None")
        lines.append("")
    lines += ["## Documents", "", "| File | Type | Pages | Size (MB) | Text layer |", "| --- | --- | --- | --- | --- |"]
    for d in report["documents"]:
        text = "yes" if d.get("has_text") else ("n/a" if "pages" not in d else "no")
        lines.append(f"| {d['path']} | {d['type']} | {d.get('pages', '-')} | {d.get('size_mb', '-')} | {text} |")
    lines += ["", "## Reviewer sign-off", "", "- Reviewed by: ____________________", "- Date: ____________________", ""]
    return "\n".join(lines)


def check_packet(packet: Path, rules_path: Path = DEFAULT_RULES, store: ClientStateStore | None = None) -> dict[str, Any]:
    manifest_path = packet / "manifest.json"
    if not manifest_path.is_file():
        raise PacketError(f"{manifest_path} not found")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        rules = json.loads(rules_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PacketError(f"Invalid JSON: {exc}") from exc

    findings = check_fields(manifest, rules) + check_required_documents(manifest, rules)
    doc_findings, inventory = check_documents(packet, manifest, rules)
    findings += doc_findings + check_client_state(manifest, rules, store)

    blocking = sum(f.severity == BLOCKING for f in findings)
    report = {
        "status": "gaps_found" if blocking else "ready_for_human_review",
        "submitted": False,
        "client_id": manifest.get("client_id"),
        "case": manifest.get("case", {}),
        "rules": {"name": rules.get("name"), "version": rules.get("version"), "path": str(rules_path)},
        "summary": {"blocking": blocking, "warnings": len(findings) - blocking, "documents": len(inventory)},
        "findings": [asdict(f) for f in findings],
        "documents": inventory,
        "generated_at": utc_now(),
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a filing packet and write a gap report (never submits).")
    parser.add_argument("packet", type=Path)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--report-dir", type=Path, help="where to write gap_report.{md,json} (default: packet dir)")
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--no-state", action="store_true", help="skip shared client state checks")
    args = parser.parse_args(argv)

    store = None if args.no_state else ClientStateStore(args.state_dir)
    try:
        report = check_packet(args.packet, args.rules, store)
    except PacketError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1

    report_dir = args.report_dir or args.packet
    report_dir.mkdir(parents=True, exist_ok=True)
    md_path, json_path = report_dir / "gap_report.md", report_dir / "gap_report.json"
    md_path.write_text(render_markdown(report), encoding="utf-8")
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if store is not None and report["client_id"]:
        try:
            store.add_artifact(
                report["client_id"],
                "filing_reports",
                {"path": str(json_path), "status": report["status"], "summary": report["summary"]},
            )
        except StateError:
            pass  # already reported as an 'unknown_client' finding

    print(json.dumps({"ok": True, "status": report["status"], "summary": report["summary"],
                      "report_md": str(md_path), "report_json": str(json_path)}, indent=2))
    return 0 if report["status"] == "ready_for_human_review" else 2


if __name__ == "__main__":
    raise SystemExit(main())
