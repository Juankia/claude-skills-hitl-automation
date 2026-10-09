import hashlib
import zipfile
from datetime import date
from pathlib import Path

import pytest
from docx import Document

import draft_document as dd
import validate_intake
from client_state import ClientStateStore
from conftest import TODAY

LETTER_DATE = date(2026, 10, 9)


def _text(path: Path) -> str:
    return "\n".join(p.text for p in Document(str(path)).paragraphs)


def test_render_variables_filters_and_conditionals():
    ctx = {"a": {"b": "x"}, "fee": 2500, "kind": "hourly", "items": ["A", "B", "C"], "d": "2026-10-09"}
    tpl = (
        "{{ a.b }} {{ fee | money }} {{ items | join }} {{ d | longdate }}\n"
        '{% if kind == "hourly" %}\nHOURLY\n{% endif %}\n'
        '{% if kind == "flat" %}\nFLAT\n{% endif %}\n'
        "{% if not missing.flag %}\nNEG\n{% endif %}"
    )
    text, missing = dd.render(tpl, ctx)
    assert "x $2,500.00 A, B, and C October 9, 2026" in text
    assert "HOURLY" in text and "FLAT" not in text and "NEG" in text
    assert missing == []


def test_missing_values_become_markers():
    text, missing = dd.render("Hello {{ client.nickname }}", {"client": {}})
    assert "[[MISSING: client.nickname]]" in text
    assert missing == ["client.nickname"]


@pytest.mark.parametrize("tpl", ["{% if x %}\nno end", "{% endif %}", "{% for x in y %}", "{{ x | nope }}"])
def test_template_errors(tpl):
    with pytest.raises(dd.TemplateError):
        dd.render(tpl, {"x": 1})


def test_docx_draft_contents(saved_client, state_dir, tmp_path):
    out = tmp_path / "letter.docx"
    result = dd.draft(saved_client, ClientStateStore(state_dir), out=out, today=LETTER_DATE)
    assert result["status"] == "draft_ready_for_review"
    assert result["missing"] == [] and result["review_markers"] == []
    text = _text(out)
    assert "Brightwater Ceramics LLC" in text
    assert "$275.00 per hour" in text and "$2,500.00" in text
    assert "laws of the State of New Mexico" in text
    assert "flat fee" not in text  # other fee branches are excluded
    assert "Mesa Distribution Partners Inc." in text
    assert "October 9, 2026" in text
    # artifact recorded in shared state
    docs = ClientStateStore(state_dir).get_client(saved_client)["artifacts"]["documents"]
    assert docs[-1]["sha256"] == result["sha256"]


def test_docx_is_byte_for_byte_deterministic(saved_client, state_dir, tmp_path):
    store = ClientStateStore(state_dir)
    a = dd.draft(saved_client, store, out=tmp_path / "a.docx", today=LETTER_DATE)
    b = dd.draft(saved_client, store, out=tmp_path / "b.docx", today=LETTER_DATE)
    assert a["sha256"] == b["sha256"]
    assert hashlib.sha256((tmp_path / "a.docx").read_bytes()).hexdigest() == a["sha256"]
    with zipfile.ZipFile(tmp_path / "a.docx") as zf:
        assert {i.date_time for i in zf.infolist()} == {(1980, 1, 1, 0, 0, 0)}


def test_unknown_jurisdiction_produces_review_markers(state_dir, answers, tmp_path):
    answers["matter"]["jurisdiction"] = "WY"
    result = validate_intake.validate(answers, today=TODAY)
    store = ClientStateStore(state_dir)
    store.upsert_client(result["record"])
    out = dd.draft(result["client_id"], store, fmt="md", out=tmp_path / "l.md", today=LETTER_DATE)
    assert out["status"] == "draft_needs_attention"
    assert any("governing law" in m for m in out["review_markers"])
    assert "[[REVIEW:" in (tmp_path / "l.md").read_text()


def test_contingency_branch_and_needs_review_notes(state_dir, answers, tmp_path):
    answers["engagement"] = {
        "fee_type": "contingency", "contingency_percent": 33, "responsible_professional": "Dana Whitfield",
    }
    answers["conflict_check"] = {"status": "pending"}
    answers["consent"]["electronic_communications"] = False
    result = validate_intake.validate(answers, today=TODAY)
    store = ClientStateStore(state_dir)
    store.upsert_client(result["record"])
    out = dd.draft(result["client_id"], store, fmt="md", out=tmp_path / "l.md", today=LETTER_DATE)
    text = (tmp_path / "l.md").read_text()
    assert "33% of any gross recovery" in text
    assert "not use e-mail" in text
    assert any("Conflict check" in n for n in out["notes"])


def test_cli_unknown_client_returns_error(state_dir, capsys):
    assert dd.main(["--client-id", "nope-000000"]) == 1
    assert "Unknown client_id" in capsys.readouterr().out
