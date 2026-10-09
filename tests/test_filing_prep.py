import json
from io import BytesIO

import pytest
from pypdf import PdfReader, PdfWriter

import check_packet as cp
from client_state import ClientStateStore
from make_demo_packet import build_packet, make_pdf


def _codes(report):
    return {(f["code"], f["target"]) for f in report["findings"]}


def test_demo_pdf_is_readable():
    reader = PdfReader(BytesIO(make_pdf(["Hello world", ""])))
    assert len(reader.pages) == 2
    assert "Hello world" in reader.pages[0].extract_text()
    assert reader.pages[1].extract_text().strip() == ""


def test_clean_packet_is_ready_for_human_review(saved_client, state_dir, tmp_path):
    packet = build_packet(tmp_path / "packet", saved_client)
    report = cp.check_packet(packet, store=ClientStateStore(state_dir))
    assert report["findings"] == []
    assert report["status"] == "ready_for_human_review"
    assert report["submitted"] is False
    assert [d["pages"] for d in report["documents"]] == [2, 1, 1]


def test_broken_packet_lists_every_gap(saved_client, state_dir, tmp_path):
    packet = build_packet(tmp_path / "packet", saved_client, broken=True)
    report = cp.check_packet(packet, store=ClientStateStore(state_dir))
    codes = _codes(report)
    assert report["status"] == "gaps_found"
    assert ("field_format", "case.case_number") in codes
    assert ("missing_document", "certificate_of_service") in codes
    assert ("file_naming", "Motion FINAL v2.pdf") in codes
    assert ("page_limit", "2026-10-09_proposed-order.pdf") in codes
    assert ("pdf_no_text", "2026-10-09_exhibit-a.pdf") in codes
    severities = {f["code"]: f["severity"] for f in report["findings"]}
    assert severities["pdf_no_text"] == "warning"


def test_encrypted_invalid_missing_and_unlisted_files(tmp_path):
    packet = build_packet(tmp_path / "p", "x-000000")
    writer = PdfWriter(clone_from=BytesIO(make_pdf(["secret"])))
    writer.encrypt("pw")
    with open(packet / "2026-10-09_proposed-order.pdf", "wb") as fh:
        writer.write(fh)
    (packet / "2026-10-09_certificate-of-service.pdf").write_bytes(b"not a pdf")
    (packet / "notes.txt").write_text("scratch")
    manifest = json.loads((packet / "manifest.json").read_text())
    manifest["documents"].append({"path": "2026-10-09_missing.pdf", "type": "exhibit"})
    manifest["documents"].append({"path": "../escape.pdf", "type": "exhibit"})
    (packet / "manifest.json").write_text(json.dumps(manifest))

    report = cp.check_packet(packet, store=None)
    codes = {c for c, _ in _codes(report)}
    assert {"pdf_encrypted", "pdf_invalid", "file_not_found", "path_outside_packet", "unlisted_file"} <= codes


def test_client_state_gates(state_dir, answers, tmp_path):
    import validate_intake
    from conftest import TODAY

    store = ClientStateStore(state_dir)
    unknown = cp.check_packet(build_packet(tmp_path / "a", "ghost-000000"), store=store)
    assert ("unknown_client", "client_id") in _codes(unknown)

    answers["conflict_check"] = {"status": "flagged"}
    result = validate_intake.validate(answers, today=TODAY)
    store.upsert_client(result["record"])
    report = cp.check_packet(build_packet(tmp_path / "b", result["client_id"]), store=store)
    codes = {c for c, _ in _codes(report)}
    assert {"intake_not_ready", "conflict_not_cleared"} <= codes


def test_rules_are_configurable(tmp_path):
    packet = build_packet(tmp_path / "p", "x-000000")
    rules = json.loads(cp.DEFAULT_RULES.read_text())
    rules["max_pages"]["motion"] = 1
    rules["required_fields"].append("case.judge")
    custom = tmp_path / "rules.json"
    custom.write_text(json.dumps(rules))
    codes = _codes(cp.check_packet(packet, custom, store=None))
    assert ("page_limit", "2026-10-09_motion-to-extend.pdf") in codes
    assert ("missing_field", "case.judge") in codes


def test_cli_writes_reports_and_records_state(saved_client, state_dir, tmp_path, capsys):
    packet = build_packet(tmp_path / "packet", saved_client, broken=True)
    assert cp.main([str(packet)]) == 2
    md = (packet / "gap_report.md").read_text()
    assert "Blocking gaps" in md and "does not file or submit anything" in md
    assert json.loads((packet / "gap_report.json").read_text())["submitted"] is False
    reports = ClientStateStore(state_dir).get_client(saved_client)["artifacts"]["filing_reports"]
    assert reports[-1]["status"] == "gaps_found"

    clean = build_packet(tmp_path / "clean", saved_client)
    assert cp.main([str(clean)]) == 0


def test_cli_missing_manifest(tmp_path):
    assert cp.main([str(tmp_path), "--no-state"]) == 1
