import json
import subprocess
import sys

from conftest import EXAMPLE_ANSWERS, REPO, TODAY

import validate_intake
from client_state import ClientStateStore

SCRIPT = REPO / "skills" / "client-intake" / "scripts" / "validate_intake.py"


def test_example_answers_are_valid_and_normalized(answers):
    result = validate_intake.validate(answers, today=TODAY)
    assert result["ok"], result["errors"]
    record = result["record"]
    assert record["client"]["legal_name"] == "Brightwater Ceramics LLC"
    assert record["client"]["contact"]["email"] == "ops@brightwater-ceramics.example"
    assert record["client"]["contact"]["phone"] == "+15055550142"
    assert record["client"]["address"]["state"] == "NM"
    assert result["status"] == "ready"
    assert result["client_id"].startswith("brightwater-ceramics-llc-")


def test_client_id_is_stable(answers):
    a = validate_intake.validate(answers, today=TODAY)["client_id"]
    answers["matter"]["summary"] += " Updated."
    b = validate_intake.validate(answers, today=TODAY)["client_id"]
    assert a == b


def test_missing_fields_are_reported_with_paths(answers):
    del answers["client"]["contact"]["email"]
    answers["engagement"].pop("retainer_usd")
    result = validate_intake.validate(answers, today=TODAY)
    assert not result["ok"]
    messages = {e["path"]: e["message"] for e in result["errors"]}
    assert "'email' is a required property" in messages["$.client.contact"]
    assert "'retainer_usd' is a required property" in messages["$.engagement"]


def test_fee_type_specific_requirements(answers):
    answers["engagement"] = {"fee_type": "contingency", "responsible_professional": "Dana Whitfield"}
    result = validate_intake.validate(answers, today=TODAY)
    assert any("contingency_percent" in e["message"] for e in result["errors"])


def test_privacy_notice_must_be_acknowledged(answers):
    answers["consent"]["privacy_notice_acknowledged"] = False
    result = validate_intake.validate(answers, today=TODAY)
    assert any(e["path"] == "$.consent.privacy_notice_acknowledged" for e in result["errors"])


def test_invalid_phone_and_state(answers):
    answers["client"]["contact"]["phone"] = "12345"
    answers["matter"]["jurisdiction"] = "ZZ"
    paths = {e["path"] for e in validate_intake.validate(answers, today=TODAY)["errors"]}
    assert {"$.client.contact.phone", "$.matter.jurisdiction"} <= paths


def test_review_reasons_flag_record_but_keep_it_valid(answers):
    answers["conflict_check"] = {"status": "flagged", "notes": "Possible prior adverse representation."}
    answers["matter"]["deadlines"] = [{"label": "Answer due", "date": "2026-10-01"}]
    result = validate_intake.validate(answers, today=TODAY)
    assert result["ok"]
    assert result["status"] == "needs_review"
    assert len(result["review_reasons"]) == 2


def test_soon_deadline_and_cross_state_warnings(answers):
    answers["matter"]["deadlines"] = [{"label": "Signature", "date": "2026-10-15"}]
    answers["matter"]["jurisdiction"] = "TX"
    warnings = validate_intake.validate(answers, today=TODAY)["warnings"]
    assert any("6 day" in w for w in warnings)
    assert any("NM" in w and "TX" in w for w in warnings)


def test_cli_saves_to_shared_state(state_dir):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(EXAMPLE_ANSWERS), "--today", "2026-10-09"],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert out["saved"] is True
    assert ClientStateStore(state_dir).get_client(out["client_id"])["intake"]["status"] == "ready"


def test_cli_dry_run_and_invalid_exit_code(state_dir, tmp_path, answers):
    bad = tmp_path / "bad.json"
    del answers["client"]["legal_name"]
    bad.write_text(json.dumps(answers))
    proc = subprocess.run([sys.executable, str(SCRIPT), str(bad), "--dry-run"], capture_output=True, text=True)
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["saved"] is False
    assert not (state_dir / "state.json").exists()
