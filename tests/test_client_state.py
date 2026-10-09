import json
from pathlib import Path

import pytest

from client_state import SCHEMA_VERSION, ClientStateStore, StateError, default_state_dir


def test_default_dir_per_platform():
    env = {"HOME": "/home/ana"}
    assert default_state_dir("linux", env) == Path("/home/ana/.local/share/clientskills")
    assert default_state_dir("darwin", env) == Path("/home/ana/Library/Application Support/ClientSkills")
    win = default_state_dir("win32", {"USERPROFILE": "C:/Users/ana", "APPDATA": "C:/Users/ana/AppData/Roaming"})
    assert win == Path("C:/Users/ana/AppData/Roaming") / "ClientSkills"


def test_env_override_wins():
    assert default_state_dir("win32", {"CLIENT_SKILLS_HOME": "/tmp/x"}) == Path("/tmp/x")


def test_empty_store_loads_current_schema(state_dir):
    state = ClientStateStore(state_dir).load()
    assert state["schema_version"] == SCHEMA_VERSION
    assert state["clients"] == {}


def test_upsert_preserves_artifacts_and_created_at(state_dir):
    store = ClientStateStore(state_dir)
    record = {"client_id": "acme-abc123", "client": {"legal_name": "Acme"}}
    first = store.upsert_client(record)
    store.add_artifact("acme-abc123", "documents", {"path": "a.docx"})
    second = store.upsert_client(dict(record, client={"legal_name": "Acme Inc"}))
    assert second["created_at"] == first["created_at"]
    assert second["artifacts"]["documents"][0]["path"] == "a.docx"
    assert store.get_client("acme-abc123")["client"]["legal_name"] == "Acme Inc"


def test_v1_file_is_migrated(state_dir):
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text(
        json.dumps({"schema_version": 1, "clients": [{"client_id": "old-000001", "client": {}}]})
    )
    store = ClientStateStore(state_dir)
    client = store.get_client("old-000001")
    assert client["artifacts"] == {"documents": [], "filing_reports": []}


def test_newer_schema_is_refused(state_dir):
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text(json.dumps({"schema_version": 99, "clients": {}}))
    with pytest.raises(StateError, match="v99"):
        ClientStateStore(state_dir).load()


def test_corrupt_file_raises_state_error(state_dir):
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text("{not json")
    with pytest.raises(StateError):
        ClientStateStore(state_dir).load()


def test_save_is_atomic_and_leaves_no_temp_files(state_dir):
    store = ClientStateStore(state_dir)
    store.upsert_client({"client_id": "a-000001"})
    assert sorted(p.name for p in state_dir.iterdir()) == ["state.json"]


def test_unknown_client_lists_known_ids(state_dir):
    store = ClientStateStore(state_dir)
    store.upsert_client({"client_id": "a-000001"})
    with pytest.raises(StateError, match="a-000001"):
        store.get_client("missing")
