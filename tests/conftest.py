from __future__ import annotations

import copy
import json
import sys
from datetime import date
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
for path in (
    REPO / "shared",
    REPO / "skills" / "client-intake" / "scripts",
    REPO / "skills" / "document-drafting" / "scripts",
    REPO / "skills" / "filing-prep-checklist" / "scripts",
    REPO / "examples",
    REPO / "scripts",
):
    sys.path.insert(0, str(path))

EXAMPLE_ANSWERS = REPO / "skills" / "client-intake" / "templates" / "intake_answers.example.json"
TODAY = date(2026, 10, 9)


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    """Isolated shared-state directory for every test (never touches the real one)."""
    directory = tmp_path / "state"
    monkeypatch.setenv("CLIENT_SKILLS_HOME", str(directory))
    return directory


@pytest.fixture
def answers():
    return copy.deepcopy(json.loads(EXAMPLE_ANSWERS.read_text(encoding="utf-8")))


@pytest.fixture
def saved_client(state_dir, answers):
    """A validated client record persisted in the isolated store; returns its id."""
    import validate_intake
    from client_state import ClientStateStore

    result = validate_intake.validate(answers, today=TODAY)
    assert result["ok"], result["errors"]
    ClientStateStore(state_dir).upsert_client(result["record"])
    return result["client_id"]
